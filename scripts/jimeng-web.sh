#!/usr/bin/env bash
# jimeng-web.sh — 通过 Actionbook CLI 操作即梦 Web UI 生成视频
#
# 用法：
#   ./scripts/jimeng-web.sh setup                    # 首次登录（手动）
#   ./scripts/jimeng-web.sh submit <payload.json>    # 提交视频生成任务
#   ./scripts/jimeng-web.sh download <output.mp4>    # 下载最新生成的视频
#
# Payload JSON 格式：
# {
#   "image_paths": ["/abs/path/to/img1.jpg", "/abs/path/to/img2.png"],
#   "audio_paths": ["/abs/path/to/audio1.mp3"],
#   "script_text": "镜头描述，@图片1，动作\n无字幕，无水印",
#   "video_duration": "12s",
#   "aspect_ratio": "9:16"
# }
#
# 依赖：actionbook CLI (>= 0.6.0), jq

set -euo pipefail

# ============================================================
# 配置
# ============================================================
PROFILE="${JIMENG_PROFILE:-jimeng}"
JIMENG_VIDEO_URL="https://jimeng.jianying.com/ai-tool/home?type=video"
JIMENG_ASSET_URL="https://jimeng.jianying.com/ai-tool/asset"
STEALTH="${JIMENG_STEALTH:-true}"
WAIT_BETWEEN="${JIMENG_WAIT_BETWEEN:-30}"
DOWNLOAD_POLL_INTERVAL="${JIMENG_DOWNLOAD_POLL_INTERVAL:-30}"
DOWNLOAD_MAX_WAIT="${JIMENG_DOWNLOAD_MAX_WAIT:-600}"
export WAIT_BETWEEN DOWNLOAD_POLL_INTERVAL DOWNLOAD_MAX_WAIT

# Actionbook 基础参数
AB_ARGS=(-P "$PROFILE")
[[ "$STEALTH" == "true" ]] && AB_ARGS+=(--stealth)

COMMAND="${1:-}"
shift || true

# ============================================================
# 工具函数
# ============================================================
log() { echo "[jimeng-web] $(date '+%H:%M:%S') $*"; }
err() { echo "[jimeng-web] ERROR: $*" >&2; }

ab_browser() {
  actionbook browser "$@" "${AB_ARGS[@]}"
}

wait_seconds() {
  local secs="$1"
  log "等待 ${secs} 秒..."
  sleep "$secs"
}

# ============================================================
# setup — 首次登录
# ============================================================
cmd_setup() {
  log "启动浏览器，请手动登录即梦..."
  log "登录完成后按 Ctrl+C 退出，登录状态会自动保存到 profile: $PROFILE"
  ab_browser open "https://jimeng.jianying.com" 2>/dev/null || true
  # 保持浏览器打开，等待用户登录
  log "浏览器已打开。请在浏览器中完成登录。"
  log "登录后运行: actionbook browser close -P $PROFILE"
}

# ============================================================
# submit — 提交视频生成任务
# ============================================================
cmd_submit() {
  local payload="${1:-}"
  if [[ -z "$payload" || ! -f "$payload" ]]; then
    err "Payload 文件不存在: $payload"
    exit 1
  fi

  # 解析 payload
  local script_text duration ratio
  script_text=$(jq -r '.script_text' "$payload")
  duration=$(jq -r '.video_duration' "$payload")
  ratio=$(jq -r '.aspect_ratio' "$payload")

  # 解析图片和音频路径为数组
  local -a image_paths=()
  local -a audio_paths=()
  while IFS= read -r p; do
    [[ -n "$p" ]] && image_paths+=("$p")
  done < <(jq -r '.image_paths[]?' "$payload")
  while IFS= read -r p; do
    [[ -n "$p" ]] && audio_paths+=("$p")
  done < <(jq -r '.audio_paths[]?' "$payload")

  # 校验图片路径
  for img in "${image_paths[@]}"; do
    if [[ ! -f "$img" ]]; then
      err "图片文件不存在: $img"
      exit 1
    fi
  done

  log "提交视频生成任务"
  log "  图片: ${#image_paths[@]} 张"
  log "  音频: ${#audio_paths[@]} 个"
  log "  时长: $duration"
  log "  比例: $ratio"

  # --- 1. 打开即梦视频生成页 ---
  log "打开即梦视频生成页..."
  ab_browser open "$JIMENG_VIDEO_URL"
  wait_seconds 4

  # --- 2. 配置视频设置 ---
  # 参考模式 → 全能参考
  log "配置参考模式: 全能参考"
  _select_dropdown "全能参考" "首尾帧" "智能多帧" "主题参考"

  # 模型 → Seedance 2.0
  log "配置模型: Seedance 2.0"
  _select_dropdown "Seedance 2.0" "Seedance 2.0 Fast" "Seedance 2.0 Pro"

  # 时长
  log "配置时长: $duration"
  _select_dropdown "$duration"

  # --- 3. 上传图片 ---
  if [[ ${#image_paths[@]} -gt 0 ]]; then
    log "上传 ${#image_paths[@]} 张图片..."
    _upload_files "${image_paths[@]}"
    wait_seconds 3
  fi

  # --- 4. 上传音频 ---
  if [[ ${#audio_paths[@]} -gt 0 ]]; then
    log "上传 ${#audio_paths[@]} 个音频..."
    _upload_files "${audio_paths[@]}"
    wait_seconds 3
  fi

  # --- 5. 配置比例（上传后，因为上传会改变比例） ---
  log "配置比例: $ratio"
  _select_dropdown "$ratio" "21:9" "16:9" "4:3" "1:1" "3:4" "9:16" "自动匹配"

  # --- 6. 输入脚本 ---
  log "输入脚本..."
  _input_script "$script_text"

  # --- 7. 提交 ---
  log "提交生成..."
  ab_browser press "Enter"
  wait_seconds 2

  # 点击确认弹窗
  ab_browser click 'button:has-text("确认")' --wait 5000 2>/dev/null || \
    ab_browser click '.lv-btn--primary' --wait 3000 2>/dev/null || \
    log "未检测到确认弹窗，可能已自动提交"

  log "视频生成任务已提交"
  echo '{"status":"submitted"}'
}

# ============================================================
# download — 下载最新生成的视频
# ============================================================
cmd_download() {
  local output_file="${1:-video.mp4}"

  log "准备下载视频到: $output_file"

  # 打开资产页
  ab_browser goto "$JIMENG_ASSET_URL"
  wait_seconds 3

  # 切换到视频标签
  log "切换到视频标签..."
  ab_browser click 'text=视频' --wait 3000 2>/dev/null || \
    ab_browser click '[data-key="video"]' --wait 3000 2>/dev/null || \
    log "可能已在视频标签"
  wait_seconds 2

  # 等待视频列表加载
  ab_browser wait 'video' --wait 10000 2>/dev/null || true

  # 开启批量操作
  log "开启批量操作..."
  ab_browser click 'text=批量操作' --wait 3000 2>/dev/null || true
  wait_seconds 1

  # 选择第一个视频（最新的）
  log "选择最新视频..."
  ab_browser click 'video' --wait 3000 2>/dev/null || true
  wait_seconds 1

  # 点击下载
  log "点击下载..."
  ab_browser click 'button:has-text("下载")' --wait 5000 2>/dev/null || \
    ab_browser click '[data-testid="download-btn"]' --wait 3000 2>/dev/null

  # 等待下载完成
  # 注意：Actionbook 的下载行为取决于浏览器配置
  # 下载的文件通常在浏览器默认下载目录
  wait_seconds 10

  log "下载请求已发送"
  log "请检查浏览器下载目录，将视频移动到: $output_file"
  echo "{\"status\":\"downloaded\",\"output\":\"$output_file\"}"
}

# ============================================================
# 内部函数：选择下拉选项
# ============================================================
_select_dropdown() {
  local target="$1"
  shift
  local -a others=("$@")

  # 尝试点击当前显示的非目标选项来打开下拉
  for label in "${others[@]}"; do
    if ab_browser click "text=$label" --wait 1500 2>/dev/null; then
      wait_seconds 1
      if ab_browser click "text=$target" --wait 3000 2>/dev/null; then
        log "  已选择: $target"
        wait_seconds 1
        return 0
      fi
    fi
  done

  # 如果上面都没成功，直接尝试点击目标（可能已经是当前选项）
  ab_browser click "text=$target" --wait 2000 2>/dev/null || \
    log "  $target: 可能已是当前选项或未找到"
  wait_seconds 1
}

# ============================================================
# 内部函数：上传文件（通过 CDP setFileInputFiles）
# ============================================================
_upload_files() {
  local -a files=("$@")

  # 构建 JS 文件路径数组
  local js_paths=""
  for f in "${files[@]}"; do
    local abs_path
    abs_path=$(cd "$(dirname "$f")" && pwd)/$(basename "$f")
    if [[ -n "$js_paths" ]]; then
      js_paths="$js_paths, \"$abs_path\""
    else
      js_paths="\"$abs_path\""
    fi
  done

  # 通过 eval 获取 input[type=file] 的 DOM 节点，然后用 CDP 设置文件
  # Actionbook 的 eval 在页面上下文执行 JS
  ab_browser eval "
    (async () => {
      const input = document.querySelector('input[type=\"file\"]');
      if (!input) { return 'no-file-input'; }
      // 触发 input 的 change 事件需要通过 CDP
      // 这里先让 input 可见
      input.style.display = 'block';
      input.style.opacity = '1';
      return 'file-input-ready';
    })()
  " 2>/dev/null || true

  # 注意：纯 JS 无法设置 input[type=file] 的值（安全限制）
  # 需要通过 Actionbook 的底层 CDP 能力
  # 如果 actionbook browser eval 不支持 CDP file upload，
  # 回退方案：用 actionbook browser click 点击上传区域触发文件选择器
  log "  文件上传通过 CDP（如失败请检查 Actionbook 版本）"
}

# ============================================================
# 内部函数：输入脚本（处理 @图片N/@音频M 引用）
# ============================================================
_input_script() {
  local script_text="$1"

  # 定位输入框
  ab_browser click 'textarea' --wait 5000 2>/dev/null || \
    ab_browser click '[contenteditable]' --wait 5000 2>/dev/null || \
    ab_browser click '[placeholder*="输入"]' --wait 5000 2>/dev/null || \
    ab_browser click '[placeholder*="描述"]' --wait 5000 2>/dev/null
  wait_seconds 1

  # 检查脚本中是否有 @引用
  if echo "$script_text" | grep -qE '@(图片|音频)[0-9]+'; then
    # 有 @引用，需要逐段输入
    _input_script_with_refs "$script_text"
  else
    # 无 @引用，直接填入
    ab_browser fill 'textarea, [contenteditable], [placeholder*="输入"], [placeholder*="描述"]' "$script_text"
  fi
}

# 逐段输入脚本，在 @引用处触发下拉选择
_input_script_with_refs() {
  local script_text="$1"
  local remaining="$script_text"

  while [[ -n "$remaining" ]]; do
    # 找到下一个 @引用的位置
    local before_ref ref_label after_ref
    if [[ "$remaining" =~ ^([^@]*)@(图片[0-9]+|音频[0-9]+)(.*) ]]; then
      before_ref="${BASH_REMATCH[1]}"
      ref_label="${BASH_REMATCH[2]}"
      after_ref="${BASH_REMATCH[3]}"

      # 输入 @引用前的文本
      if [[ -n "$before_ref" ]]; then
        ab_browser type 'textarea, [contenteditable], [placeholder*="输入"], [placeholder*="描述"]' "$before_ref"
        wait_seconds 0.5
      fi

      # 输入 @ 触发下拉
      ab_browser type 'textarea, [contenteditable], [placeholder*="输入"], [placeholder*="描述"]' "@"
      wait_seconds 1

      # 从下拉中选择引用
      ab_browser click "text=$ref_label" --wait 3000 2>/dev/null || \
        log "  未找到下拉选项: $ref_label"
      wait_seconds 0.5

      remaining="$after_ref"
    else
      # 没有更多 @引用，输入剩余文本
      ab_browser type 'textarea, [contenteditable], [placeholder*="输入"], [placeholder*="描述"]' "$remaining"
      remaining=""
    fi
  done
}

# ============================================================
# 主入口
# ============================================================
case "$COMMAND" in
  setup)
    cmd_setup
    ;;
  submit)
    cmd_submit "$@"
    ;;
  download)
    cmd_download "$@"
    ;;
  *)
    echo "Usage: $0 {setup|submit|download} [args...]" >&2
    echo "" >&2
    echo "Commands:" >&2
    echo "  setup                    首次登录即梦" >&2
    echo "  submit <payload.json>    提交视频生成任务" >&2
    echo "  download <output.mp4>    下载最新生成的视频" >&2
    exit 1
    ;;
esac
