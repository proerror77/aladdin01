#!/usr/bin/env bash
# jimeng-web.sh — 通过 Actionbook CLI + CDP 操作即梦 Web UI 生成视频
#
# 用法：
#   ./scripts/jimeng-web.sh setup                    # 首次登录（手动）
#   ./scripts/jimeng-web.sh submit <payload.json>    # 提交视频生成任务
#   ./scripts/jimeng-web.sh download <output.mp4>    # 下载最新生成的视频
#
# Payload JSON 格式：
# {
#   "image_paths": ["/abs/path/to/img1.jpg"],
#   "audio_paths": ["/abs/path/to/audio1.mp3"],
#   "script_text": "镜头描述文本\n无字幕，无水印",
#   "video_duration": "12s",
#   "aspect_ratio": "9:16"
# }
#
# 依赖：actionbook CLI (>= 0.6.0), jq, python3, pip: websockets
#
# 实测验证的操作方式（2026-03-26）：
#   - 下拉选择：eval + JS click combobox[role=combobox] → option[role=option]
#   - 文本输入：actionbook browser type/fill + CSS 'textarea.lv-textarea'
#   - 文件上传：CDP DOM.setFileInputFiles via Python websockets
#   - 页面导航：actionbook browser goto（不是 open，避免多 tab）

set -euo pipefail

# ============================================================
# 配置
# ============================================================
PROFILE="${JIMENG_PROFILE:-jimeng}"
CDP_PORT="${JIMENG_CDP_PORT:-9224}"
JIMENG_VIDEO_URL="https://jimeng.jianying.com/ai-tool/home?type=video"
JIMENG_ASSET_URL="https://jimeng.jianying.com/ai-tool/asset"
STEALTH="${JIMENG_STEALTH:-true}"
WAIT_BETWEEN="${JIMENG_WAIT_BETWEEN:-30}"
DOWNLOAD_POLL_INTERVAL="${JIMENG_DOWNLOAD_POLL_INTERVAL:-30}"
DOWNLOAD_MAX_WAIT="${JIMENG_DOWNLOAD_MAX_WAIT:-600}"

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
  actionbook browser "$@" "${AB_ARGS[@]}" 2>/dev/null
}

ab_eval() {
  actionbook browser eval "$1" "${AB_ARGS[@]}" 2>/dev/null
}

wait_seconds() {
  local secs="$1"
  log "等待 ${secs}s..."
  sleep "$secs"
}

# 获取即梦页面的 CDP WebSocket URL
_get_jimeng_ws_url() {
  actionbook browser status -P "$PROFILE" 2>/dev/null \
    | grep -oE '[A-F0-9]{32}' | head -1 | while read -r page_id; do
      echo "ws://127.0.0.1:${CDP_PORT}/devtools/page/${page_id}"
    done
}

# 通过 CDP WebSocket 执行操作（Python helper）
_cdp_run() {
  local py_code="$1"
  python3 -c "
import json, asyncio, websockets, sys

CDP_PORT = ${CDP_PORT}

async def get_jimeng_page_ws():
    import subprocess
    r = subprocess.run(['actionbook', 'browser', 'status', '-P', '${PROFILE}'],
                       capture_output=True, text=True)
    import re
    pages = re.findall(r'([A-F0-9]{32})', r.stdout)
    for pid in pages:
        ws = f'ws://127.0.0.1:{CDP_PORT}/devtools/page/{pid}'
        try:
            async with websockets.connect(ws, max_size=10*1024*1024, open_timeout=3) as test:
                await test.send(json.dumps({'id':0,'method':'Runtime.evaluate','params':{'expression':'document.title'}}))
                resp = json.loads(await test.recv())
                title = resp.get('result',{}).get('result',{}).get('value','')
                if '即梦' in title or 'jimeng' in title.lower():
                    return ws
        except:
            continue
    return pages[0] if pages else None

async def main():
    ws_url = await get_jimeng_page_ws()
    if not ws_url:
        print('ERROR: no jimeng page found', file=sys.stderr)
        sys.exit(1)
    async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:
${py_code}

asyncio.run(main())
" 2>&1
}

# ============================================================
# setup — 首次登录
# ============================================================
cmd_setup() {
  log "启动浏览器，请手动登录即梦..."
  ab_browser open "https://jimeng.jianying.com" || true
  log "浏览器已打开。请在浏览器中完成登录。"
  log "登录完成后运行: actionbook browser close -P $PROFILE"
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

  local -a image_paths=()
  local -a audio_paths=()
  while IFS= read -r p; do [[ -n "$p" ]] && image_paths+=("$p"); done < <(jq -r '.image_paths[]?' "$payload")
  while IFS= read -r p; do [[ -n "$p" ]] && audio_paths+=("$p"); done < <(jq -r '.audio_paths[]?' "$payload")

  # 校验文件
  for img in "${image_paths[@]}"; do
    [[ ! -f "$img" ]] && { err "图片不存在: $img"; exit 1; }
  done
  for aud in "${audio_paths[@]}"; do
    [[ ! -f "$aud" ]] && { err "音频不存在: $aud"; exit 1; }
  done

  log "提交任务: ${#image_paths[@]} 图, ${#audio_paths[@]} 音频, 时长=$duration, 比例=$ratio"

  # --- 1. 导航到即梦视频生成页 ---
  log "导航到即梦..."
  ab_browser goto "$JIMENG_VIDEO_URL"
  wait_seconds 4

  # --- 2. 配置：参考模式 → 全能参考 ---
  log "设置参考模式: 全能参考"
  _select_combobox 2 "全能参考"

  # --- 3. 配置：模型 → Seedance 2.0 ---
  log "设置模型: Seedance 2.0"
  _select_combobox 1 "全能王者"

  # --- 4. 配置：时长 ---
  log "设置时长: $duration"
  _select_combobox 3 "$duration"

  # --- 5. 上传图片 ---
  if [[ ${#image_paths[@]} -gt 0 ]]; then
    log "上传 ${#image_paths[@]} 张图片..."
    _upload_files_cdp "${image_paths[@]}"
    wait_seconds 3
  fi

  # --- 6. 上传音频 ---
  if [[ ${#audio_paths[@]} -gt 0 ]]; then
    log "上传 ${#audio_paths[@]} 个音频..."
    _upload_files_cdp "${audio_paths[@]}"
    wait_seconds 3
  fi

  # --- 7. 配置比例（上传后，因为上传可能改变比例） ---
  log "设置比例: $ratio"
  _select_ratio "$ratio"

  # --- 8. 输入脚本 ---
  # 全能参考模式用 ProseMirror (.tiptap)，首尾帧模式用 textarea
  log "输入脚本..."
  ab_browser fill '.tiptap.ProseMirror' "$script_text" 2>/dev/null || \
    ab_browser fill 'textarea.lv-textarea' "$script_text" 2>/dev/null || \
    { err "找不到输入框"; exit 1; }
  wait_seconds 1

  # --- 9. 提交（Enter + 确认弹窗） ---
  log "提交生成..."
  ab_browser press "Enter"
  wait_seconds 2
  # 点击确认弹窗
  ab_eval '(() => {
    const btns = document.querySelectorAll("button");
    for (const b of btns) {
      if (b.textContent.trim() === "确认") { b.click(); return "confirmed"; }
    }
    return "no-confirm-dialog";
  })()'
  wait_seconds 1

  log "任务已提交"
  echo '{"status":"submitted"}'
}

# ============================================================
# download — 下载最新生成的视频
# ============================================================
cmd_download() {
  local output_file="${1:-video.mp4}"
  log "下载视频到: $output_file"

  # 导航到资产页
  ab_browser goto "$JIMENG_ASSET_URL"
  wait_seconds 3

  # 切换到视频标签
  log "切换到视频标签..."
  ab_eval '(() => {
    const items = document.querySelectorAll("[role=menuitem], [role=tab], span");
    for (const el of items) {
      if (el.textContent.trim() === "视频") { el.click(); return "clicked-video-tab"; }
    }
    return "video-tab-not-found";
  })()'
  wait_seconds 3

  # 点击批量操作
  log "开启批量操作..."
  ab_eval '(() => {
    const spans = document.querySelectorAll("span, div");
    for (const el of spans) {
      if (el.textContent.trim() === "批量操作" && el.offsetParent) { el.click(); return "batch-mode"; }
    }
    return "no-batch-btn";
  })()'
  wait_seconds 1

  # 选择第一个视频
  log "选择最新视频..."
  ab_eval '(() => {
    const videos = document.querySelectorAll("video");
    if (videos.length > 0) { videos[0].click(); return "selected-" + videos.length; }
    return "no-videos";
  })()'
  wait_seconds 1

  # 点击下载
  log "点击下载..."
  ab_eval '(() => {
    const btns = document.querySelectorAll("button");
    for (const b of btns) {
      if (b.textContent.includes("下载")) { b.click(); return "downloading"; }
    }
    return "no-download-btn";
  })()'
  wait_seconds 10

  log "下载请求已发送，检查浏览器下载目录"
  echo "{\"status\":\"download_requested\",\"output\":\"$output_file\"}"
}

# ============================================================
# 内部函数：通过 JS 选择 combobox 选项
# combobox_index: 0=功能, 1=模型, 2=参考模式, 3=时长
# match_text: 选项中包含的文本（用 includes 匹配）
# ============================================================
_select_combobox() {
  local idx="$1"
  local match_text="$2"

  # 点击 combobox 打开下拉
  ab_eval "(()=>{
    const cb = document.querySelectorAll('[role=combobox]')[${idx}];
    if (!cb) return 'combobox-${idx}-not-found';
    cb.click();
    return 'opened-combobox-${idx}: ' + cb.textContent.trim().substring(0,30);
  })()"
  sleep 1

  # 从下拉中选择匹配的选项
  ab_eval "(()=>{
    const opts = document.querySelectorAll('[role=option]');
    for (const o of opts) {
      if (o.textContent.includes('${match_text}')) { o.click(); return 'selected: ${match_text}'; }
    }
    return 'option-not-found: ${match_text}';
  })()"
  sleep 1

  # 验证
  local current
  current=$(ab_eval "(()=>{ return document.querySelectorAll('[role=combobox]')[${idx}]?.textContent?.trim()?.substring(0,30) || 'N/A'; })()" 2>/dev/null || echo "N/A")
  log "  当前值: $current"
}

# ============================================================
# 内部函数：选择比例（比例是 button 不是 combobox）
# ============================================================
_select_ratio() {
  local target="$1"
  ab_eval "(()=>{
    const btns = document.querySelectorAll('button');
    for (const b of btns) {
      const t = b.textContent.trim();
      if (['21:9','16:9','4:3','1:1','3:4','9:16'].includes(t) && t !== '${target}') {
        b.click(); return 'opened-ratio-from: ' + t;
      }
    }
    return 'ratio-btn-not-found';
  })()"
  sleep 1
  ab_eval "(()=>{
    const items = document.querySelectorAll('[role=option], [role=menuitem], li, span');
    for (const el of items) {
      if (el.textContent.trim() === '${target}') { el.click(); return 'selected-ratio: ${target}'; }
    }
    return 'ratio-option-not-found';
  })()"
  sleep 1
}

# ============================================================
# 内部函数：通过 CDP WebSocket 上传文件
# ============================================================
_upload_files_cdp() {
  local -a files=("$@")

  # 构建 Python 文件路径列表
  local py_files=""
  for f in "${files[@]}"; do
    local abs_path
    abs_path="$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
    [[ -n "$py_files" ]] && py_files="$py_files, "
    py_files="${py_files}\"${abs_path}\""
  done

  _cdp_run "
        files = [${py_files}]
        # Enable DOM
        await ws.send(json.dumps({'id':1,'method':'DOM.enable'}))
        await ws.recv()
        # Get document
        await ws.send(json.dumps({'id':2,'method':'DOM.getDocument','params':{'depth':-1}}))
        r = json.loads(await ws.recv())
        root = r['result']['root']['nodeId']
        # Find file input
        await ws.send(json.dumps({'id':3,'method':'DOM.querySelector','params':{'nodeId':root,'selector':'input[type=file]'}}))
        r = json.loads(await ws.recv())
        node_id = r['result']['nodeId']
        if node_id == 0:
            print('ERROR: no file input found')
            sys.exit(1)
        # Set files
        await ws.send(json.dumps({'id':4,'method':'DOM.setFileInputFiles','params':{'nodeId':node_id,'files':files}}))
        r = json.loads(await ws.recv())
        if 'error' in r:
            print(f'ERROR: {r[\"error\"]}')
            sys.exit(1)
        print(f'uploaded {len(files)} file(s)')
"
}

# ============================================================
# 主入口
# ============================================================
case "$COMMAND" in
  setup)    cmd_setup ;;
  submit)   cmd_submit "$@" ;;
  download) cmd_download "$@" ;;
  *)
    echo "Usage: $0 {setup|submit|download} [args...]" >&2
    echo "  setup                    首次登录即梦" >&2
    echo "  submit <payload.json>    提交视频生成任务" >&2
    echo "  download <output.mp4>    下载最新生成的视频" >&2
    exit 1
    ;;
esac
