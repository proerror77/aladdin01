#!/usr/bin/env bash
# api-caller.sh - 统一 API 调用脚本
# 用法：
#   ./scripts/api-caller.sh seedance create <payload.json>   # 创建视频生成任务
#   ./scripts/api-caller.sh seedance status <task_id>        # 查询任务状态
#   ./scripts/api-caller.sh seedance download <video_url> <output_file>  # 下载视频
#   ./scripts/api-caller.sh image_gen generate <payload.json>
#   ./scripts/api-caller.sh image_gen download <image_url> <output_file>
#   ./scripts/api-caller.sh moderation check-file <text_file>
#   ./scripts/api-caller.sh tuzi chat <payload.json>         # Tuzi LLM（nano-banana-vip 等）
#   ./scripts/api-caller.sh tuzi image <payload.json>        # Tuzi 图像生成（gpt-4o-image）
#   ./scripts/api-caller.sh tuzi models                      # 列出可用模型
#   ./scripts/api-caller.sh dreamina submit <payload.json>   # 提交 dreamina 生成任务
#   ./scripts/api-caller.sh dreamina query <submit_id>       # 查询 dreamina 任务结果
#   ./scripts/api-caller.sh dreamina download <submit_id> <dir>  # 下载 dreamina 结果
#   ./scripts/api-caller.sh dreamina credit                  # 查询 dreamina 余额
#   ./scripts/api-caller.sh dreamina list                    # 查看 dreamina 任务列表
#   ./scripts/api-caller.sh dreamina login-check             # 检查 dreamina 登录状态
#   ./scripts/api-caller.sh env-check  # 检查环境变量
#   ./scripts/api-caller.sh trace-summary <session_dir>  # 生成 LLM 摘要（DEEPSEEK 或 TUZI）
#
# Seedance payload 格式（火山方舟官方规范）：
# {
#   "model": "doubao-seedance-1-5-pro-251215",
#   "content": [
#     { "type": "text", "text": "提示词" },
#     { "type": "image_url", "image_url": { "url": "首帧图片URL" } }  // 图生视频时添加
#   ],
#   "ratio": "16:9",      // 21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16 / adaptive
#   "duration": 5,        // 4~12 秒（Seedance 1.5 pro）
#   "resolution": "1080p", // 480p / 720p / 1080p
#   "generate_audio": true,
#   "watermark": false
# }

set -euo pipefail

# 超时配置（秒）
CONNECT_TIMEOUT=10
SEEDANCE_MAX_TIME=300
IMAGE_GEN_MAX_TIME=60
MODERATION_MAX_TIME=30
DOWNLOAD_MAX_TIME=600  # 下载大文件用更长超时

# 默认输出目录（安全限制）
DEFAULT_OUTPUT_DIR="${DEFAULT_OUTPUT_DIR:-.}"

SERVICE="${1:-}"
ACTION="${2:-}"
INPUT="${3:-}"

if [[ -z "$SERVICE" ]]; then
  echo "Usage: $0 <service> <action> <input>" >&2
  echo "Services: seedance, image_gen, moderation, tuzi, dreamina, env-check, trace-summary" >&2
  exit 1
fi

if [[ "$SERVICE" != "env-check" && -z "$ACTION" ]]; then
  echo "Usage: $0 <service> <action> <input>" >&2
  echo "Services: seedance, image_gen, moderation, tuzi, dreamina, env-check, trace-summary" >&2
  exit 1
fi

# 通用函数：校验 task_id 格式（防止路径遍历）
validate_task_id() {
  local task_id="$1"
  if [[ ! "$task_id" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "ERROR: Invalid task_id format. Only alphanumeric, underscore and hyphen allowed." >&2
    exit 1
  fi
}

# 通用函数：校验输出文件路径（防止路径遍历）
validate_output_path() {
  local output_path="$1"
  local basename

  # 获取文件名（去除路径）
  basename=$(basename "$output_path")

  # 检查是否包含危险的路径遍历
  if [[ "$output_path" == ../* ]] || [[ "$output_path" == */../* ]] || [[ "$output_path" == ".." ]]; then
    echo "ERROR: Path traversal detected in output path" >&2
    exit 1
  fi

  # 如果是绝对路径，检查是否在允许的目录内
  if [[ "$output_path" == /* ]]; then
    echo "ERROR: Absolute paths not allowed. Use relative path: $basename" >&2
    exit 1
  fi

  # 返回安全的文件名
  echo "$basename"
}

# 通用函数：校验 URL 格式（仅允许 HTTPS，防止 SSRF）
validate_url() {
  local url="$1"
  if [[ ! "$url" =~ ^https:// ]]; then
    echo "ERROR: Only HTTPS URLs are allowed" >&2
    exit 1
  fi
  # 可选：检查是否为已知 API 域名（根据实际需求启用）
  # if [[ ! "$url" =~ ^https://(api\.openai\.com|your-api-domain\.com)/ ]]; then
  #   echo "ERROR: URL must be from allowed domains" >&2
  #   exit 1
  # fi
}

# 通用函数：规范化 BASE_URL（移除尾部斜杠）
normalize_base_url() {
  local url="$1"
  echo "${url%/}"
}

# 通用函数：安全的 curl 调用（带超时和错误信息保留）
safe_curl() {
  local max_time="$1"
  shift
  curl -sS --fail-with-body \
    --connect-timeout "$CONNECT_TIMEOUT" \
    --max-time "$max_time" \
    "$@"
}

# 带 429 退避的 curl 封装
safe_curl_with_retry() {
    local max_time="$1"
    local max_retries="${CURL_MAX_RETRIES:-3}"
    shift

    local attempt=1
    while (( attempt <= max_retries )); do
        local tmp_file
        tmp_file=$(mktemp)
        local http_code
        http_code=$(curl -sS -w "%{http_code}" -o "$tmp_file" \
            --connect-timeout "$CONNECT_TIMEOUT" \
            --max-time "$max_time" \
            "$@")
        local body
        body=$(cat "$tmp_file")
        rm -f "$tmp_file"

        if [[ "$http_code" == "429" ]]; then
            local wait=$(( 2 ** attempt + RANDOM % 5 ))
            echo "[WARN] Rate limited (429), waiting ${wait}s (attempt ${attempt}/${max_retries})" >&2
            sleep "$wait"
            (( attempt++ ))
            continue
        fi

        if [[ "$http_code" -ge 200 && "$http_code" -lt 300 ]]; then
            echo "$body"
            return 0
        fi

        # 其他错误：直接返回
        echo "$body" >&2
        return 1
    done

    echo "[ERROR] Max retries (${max_retries}) exceeded after rate limiting" >&2
    return 1
}

# 环境变量检查
if [[ "$SERVICE" == "env-check" ]]; then
  missing=0
  [[ -z "${ARK_API_KEY:-}" ]] && echo "Missing: ARK_API_KEY" >&2 && ((missing++))
  # image_gen：IMAGE_GEN_API_URL 未设时可 fallback 到 tuzi，给出提示而不报错
  if [[ -z "${IMAGE_GEN_API_URL:-}" ]]; then
    if [[ -n "${TUZI_API_KEY:-}" ]]; then
      echo "Info: IMAGE_GEN_API_URL not set, will fallback to tuzi (gpt-4o-image)"
    else
      echo "Missing: IMAGE_GEN_API_URL (or set TUZI_API_KEY as fallback)" >&2
      ((missing++))
    fi
  else
    [[ -z "${IMAGE_GEN_API_KEY:-}" ]] && echo "Missing: IMAGE_GEN_API_KEY" >&2 && ((missing++))
  fi
  [[ -z "${OPENAI_API_KEY:-}" ]] && echo "Optional: OPENAI_API_KEY (enables Moderation API in Phase 1 Layer 3)"
  # tuzi 为可选（若设置则启用 LLM 摘要 / 图像生成 fallback）
  [[ -z "${TUZI_API_KEY:-}" ]] && echo "Optional: TUZI_API_KEY (enables tuzi service + image_gen fallback)"
  # dreamina CLI 检查
  if command -v dreamina &>/dev/null; then
    if dreamina user_credit &>/dev/null 2>&1; then
      echo "Info: dreamina CLI installed and logged in"
    else
      echo "Warning: dreamina CLI installed but not logged in (run: dreamina login)" >&2
    fi
  else
    echo "Optional: dreamina CLI not installed (run: curl -fsSL https://jimeng.jianying.com/cli | bash)"
  fi
  # v2.0 模式依赖检查
  echo ""
  echo "=== v2.0 模式依赖（可选，仅 img2video 模式需要）==="
  if python3 -c "import lancedb" 2>/dev/null; then
    echo "✅ lancedb 已安装"
  else
    echo "⚠️  lancedb 未安装（v2.0 向量数据库必需）"
    echo "   安装：pip install lancedb pyarrow"
  fi

  if python3 -c "from sentence_transformers import SentenceTransformer" 2>/dev/null; then
    echo "✅ sentence-transformers 已安装"
  else
    echo "⚠️  sentence-transformers 未安装（v2.0 语义搜索必需）"
    echo "   安装：pip install sentence-transformers"
  fi

  if [[ $missing -eq 0 ]]; then
    echo ""
    echo "All required environment variables are set."
    exit 0
  else
    echo ""
    echo "$missing environment variable(s) missing." >&2
    exit 1
  fi
fi

# 加载 API 端点配置（从环境变量）
case "$SERVICE" in
  seedance)
    # 火山方舟官方 API，Base URL 固定
    BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
    API_KEY="${ARK_API_KEY:-}"
    if [[ -z "$API_KEY" ]]; then
      echo "ERROR: ARK_API_KEY must be set" >&2
      exit 1
    fi

    case "$ACTION" in
      create)
        if [[ ! -f "$INPUT" ]]; then
          echo "ERROR: Payload file not found: $INPUT" >&2
          exit 1
        fi
        safe_curl_with_retry "$SEEDANCE_MAX_TIME" -X POST "${BASE_URL}/contents/generations/tasks" \
          -H "Authorization: Bearer ${API_KEY}" \
          -H "Content-Type: application/json" \
          -d @"${INPUT}"
        ;;
      status)
        validate_task_id "$INPUT"
        safe_curl "$SEEDANCE_MAX_TIME" "${BASE_URL}/contents/generations/tasks/${INPUT}" \
          -H "Authorization: Bearer ${API_KEY}"
        ;;
      download)
        # 官方 API 视频直接从 content.video_url 下载，INPUT 为视频 URL
        VIDEO_URL="$INPUT"
        OUTPUT_FILE="${4:-video.mp4}"
        if [[ -z "$VIDEO_URL" ]]; then
          echo "ERROR: Video URL required" >&2
          exit 1
        fi
        validate_url "$VIDEO_URL"
        SAFE_OUTPUT=$(validate_output_path "$OUTPUT_FILE")
        safe_curl "$DOWNLOAD_MAX_TIME" "$VIDEO_URL" \
          -o "${SAFE_OUTPUT}"
        if [[ ! -s "$SAFE_OUTPUT" ]]; then
          echo "ERROR: Downloaded file is empty or download failed" >&2
          rm -f "$SAFE_OUTPUT"
          exit 1
        fi
        echo "Downloaded to ${SAFE_OUTPUT}"
        ;;
      *)
        echo "ERROR: Unknown seedance action: ${ACTION}" >&2
        echo "Valid actions: create, status, download" >&2
        exit 1
        ;;
    esac
    ;;

  image_gen)
    BASE_URL="${IMAGE_GEN_API_URL:-}"
    API_KEY="${IMAGE_GEN_API_KEY:-}"
    # 若 IMAGE_GEN_API_URL 未配置，自动 fallback 到 tuzi
    if [[ -z "$BASE_URL" ]]; then
      if [[ -z "${TUZI_API_KEY:-}" ]]; then
        echo "ERROR: IMAGE_GEN_API_URL and IMAGE_GEN_API_KEY must be set (or set TUZI_API_KEY as fallback)" >&2
        exit 1
      fi
      BASE_URL="https://api.tu-zi.com"
      API_KEY="${TUZI_API_KEY}"
      echo "Info: IMAGE_GEN_API_URL not set, using tuzi fallback (nano-banana-vip)" >&2
    elif [[ -z "$API_KEY" ]]; then
      echo "ERROR: IMAGE_GEN_API_KEY must be set" >&2
      exit 1
    fi
    # 规范化 BASE_URL
    BASE_URL=$(normalize_base_url "$BASE_URL")
    BASE_URL="${BASE_URL%/v1}"  # 去掉尾部 /v1，避免与 endpoint 路径重复

    case "$ACTION" in
      generate)
        if [[ ! -f "$INPUT" ]]; then
          echo "ERROR: Payload file not found: $INPUT" >&2
          exit 1
        fi
        safe_curl "$IMAGE_GEN_MAX_TIME" -X POST "${BASE_URL}/v1/images/generations" \
          -H "Authorization: Bearer ${API_KEY}" \
          -H "Content-Type: application/json" \
          -d @"${INPUT}"
        ;;
      download)
        # 从 URL 下载图片
        IMAGE_URL="$INPUT"
        OUTPUT_FILE="${4:-image.png}"
        if [[ -z "$IMAGE_URL" ]]; then
          echo "ERROR: Image URL required" >&2
          exit 1
        fi
        # 校验 URL 格式（仅允许 HTTPS）
        validate_url "$IMAGE_URL"
        # 校验并获取安全的输出路径
        SAFE_OUTPUT=$(validate_output_path "$OUTPUT_FILE")

        safe_curl "$DOWNLOAD_MAX_TIME" "$IMAGE_URL" \
          -H "Authorization: Bearer ${API_KEY}" \
          -o "${SAFE_OUTPUT}"
        if [[ ! -s "$SAFE_OUTPUT" ]]; then
          echo "ERROR: Downloaded file is empty or download failed" >&2
          rm -f "$SAFE_OUTPUT"
          exit 1
        fi
        echo "Downloaded to ${SAFE_OUTPUT}"
        ;;
      *)
        echo "ERROR: Unknown image_gen action: ${ACTION}" >&2
        echo "Valid actions: generate, download" >&2
        exit 1
        ;;
    esac
    ;;

  moderation)
    API_KEY="${OPENAI_API_KEY:-}"
    if [[ -z "$API_KEY" ]]; then
      echo "ERROR: OPENAI_API_KEY must be set" >&2
      exit 1
    fi
    case "$ACTION" in
      check-file)
        # 从文件读取文本（使用环境变量传递文件名，避免代码注入）
        if [[ -z "$INPUT" || ! -f "$INPUT" ]]; then
          echo "ERROR: Text file not found: $INPUT" >&2
          exit 1
        fi
        # 使用环境变量安全传递文件名到 Python
        export MODERATION_INPUT_FILE="$INPUT"
        PAYLOAD=$(python3 -c '
import json
import os
filename = os.environ.get("MODERATION_INPUT_FILE")
with open(filename, "r", encoding="utf-8") as f:
    text = f.read()
payload = {"input": text}
print(json.dumps(payload))
')
        safe_curl "$MODERATION_MAX_TIME" -X POST "https://api.openai.com/v1/moderations" \
          -H "Authorization: Bearer ${API_KEY}" \
          -H "Content-Type: application/json" \
          -d "${PAYLOAD}"
        ;;
      check)
        # 兼容旧调用方式（使用 sys.argv 安全传递）
        if [[ -z "$INPUT" ]]; then
          echo "ERROR: Text input required" >&2
          exit 1
        fi
        PAYLOAD=$(python3 -c '
import json
import sys
text = sys.argv[1]
payload = {"input": text}
print(json.dumps(payload))
' "$INPUT")
        safe_curl "$MODERATION_MAX_TIME" -X POST "https://api.openai.com/v1/moderations" \
          -H "Authorization: Bearer ${API_KEY}" \
          -H "Content-Type: application/json" \
          -d "${PAYLOAD}"
        ;;
      *)
        echo "ERROR: Unknown moderation action: ${ACTION}" >&2
        echo "Valid actions: check-file, check" >&2
        exit 1
        ;;
    esac
    ;;

  tuzi)
    # Tuzi OpenAI-compatible proxy（nano-banana-vip / gpt-4o-image 等）
    API_KEY="${TUZI_API_KEY:-}"
    if [[ -z "$API_KEY" ]]; then
      echo "ERROR: TUZI_API_KEY must be set" >&2
      exit 1
    fi
    TUZI_BASE="https://api.tu-zi.com/v1"

    case "$ACTION" in
      chat)
        # 通用对话：INPUT 为 payload JSON 文件
        # payload 格式：{"model": "nano-banana-vip", "messages": [...], "max_tokens": N}
        if [[ ! -f "$INPUT" ]]; then
          echo "ERROR: Payload file not found: $INPUT" >&2
          exit 1
        fi
        safe_curl "120" -X POST "${TUZI_BASE}/chat/completions" \
          -H "Authorization: Bearer ${API_KEY}" \
          -H "Content-Type: application/json" \
          -d @"${INPUT}"
        ;;
      image)
        # 图像生成：INPUT 为 payload JSON 文件
        # payload 格式：{"model": "gpt-4o-image", "prompt": "...", "n": 1, "size": "1024x1024"}
        if [[ ! -f "$INPUT" ]]; then
          echo "ERROR: Payload file not found: $INPUT" >&2
          exit 1
        fi
        safe_curl "120" -X POST "${TUZI_BASE}/images/generations" \
          -H "Authorization: Bearer ${API_KEY}" \
          -H "Content-Type: application/json" \
          -d @"${INPUT}"
        ;;
      models)
        # 列出可用模型
        safe_curl "30" "${TUZI_BASE}/models" \
          -H "Authorization: Bearer ${API_KEY}"
        ;;
      *)
        echo "ERROR: Unknown tuzi action: ${ACTION}" >&2
        echo "Valid actions: chat, image, models" >&2
        exit 1
        ;;
    esac
    ;;

  jimeng-web)
    echo "ERROR: jimeng-web backend has been removed. Use 'dreamina' backend instead." >&2
    echo "Install: curl -fsSL https://jimeng.jianying.com/cli | bash" >&2
    echo "Login: dreamina login" >&2
    exit 1
    ;;

  dreamina)
    # 即梦官方 CLI（Dreamina CLI）
    # 支持 text2video, image2video, multimodal2video, multiframe2video, frames2video
    # 支持 text2image, image2image, image_upscale
    # 需要先登录：dreamina login

    if ! command -v dreamina &>/dev/null; then
      echo "ERROR: dreamina CLI not found. Install: curl -fsSL https://jimeng.jianying.com/cli | bash" >&2
      exit 1
    fi

    case "$ACTION" in
      submit)
        # JSON payload → CLI flags 转换
        if [[ ! -f "$INPUT" ]]; then
          echo "ERROR: Payload file not found: $INPUT" >&2
          exit 1
        fi

        # 读取 command 字段
        COMMAND=$(jq -r '.command // empty' "$INPUT")
        if [[ -z "$COMMAND" ]]; then
          echo "ERROR: Missing 'command' field in payload" >&2
          exit 1
        fi

        # 构建 CLI flags
        FLAGS=()

        # 通用参数
        PROMPT=$(jq -r '.prompt // empty' "$INPUT")
        [[ -n "$PROMPT" ]] && FLAGS+=(--prompt="$PROMPT")

        DURATION=$(jq -r '.duration // empty' "$INPUT")
        [[ -n "$DURATION" ]] && FLAGS+=(--duration="$DURATION")

        RATIO=$(jq -r '.ratio // empty' "$INPUT")
        [[ -n "$RATIO" ]] && FLAGS+=(--ratio="$RATIO")

        VIDEO_RESOLUTION=$(jq -r '.video_resolution // empty' "$INPUT")
        [[ -n "$VIDEO_RESOLUTION" ]] && FLAGS+=(--video_resolution="$VIDEO_RESOLUTION")

        MODEL_VERSION=$(jq -r '.model_version // empty' "$INPUT")
        [[ -n "$MODEL_VERSION" ]] && FLAGS+=(--model_version="$MODEL_VERSION")

        RESOLUTION_TYPE=$(jq -r '.resolution_type // empty' "$INPUT")
        [[ -n "$RESOLUTION_TYPE" ]] && FLAGS+=(--resolution_type="$RESOLUTION_TYPE")

        POLL=$(jq -r '.poll // empty' "$INPUT")
        [[ -n "$POLL" ]] && FLAGS+=(--poll="$POLL")

        # 命令特定参数
        case "$COMMAND" in
          text2video)
            # 无额外参数
            ;;
          image2video)
            IMAGE=$(jq -r '.image // empty' "$INPUT")
            if [[ -z "$IMAGE" ]]; then
              echo "ERROR: image2video requires 'image' field" >&2
              exit 1
            fi
            FLAGS+=(--image="$IMAGE")
            ;;
          multimodal2video)
            # 图片数组
            IMAGES_JSON=$(jq -r '.images // []' "$INPUT")
            if [[ "$IMAGES_JSON" != "[]" ]]; then
              while IFS= read -r img; do
                FLAGS+=(--image="$img")
              done < <(echo "$IMAGES_JSON" | jq -r '.[]')
            fi
            # 视频数组
            VIDEOS_JSON=$(jq -r '.videos // []' "$INPUT")
            if [[ "$VIDEOS_JSON" != "[]" ]]; then
              while IFS= read -r vid; do
                FLAGS+=(--video="$vid")
              done < <(echo "$VIDEOS_JSON" | jq -r '.[]')
            fi
            # 音频数组
            AUDIOS_JSON=$(jq -r '.audios // []' "$INPUT")
            if [[ "$AUDIOS_JSON" != "[]" ]]; then
              while IFS= read -r aud; do
                FLAGS+=(--audio="$aud")
              done < <(echo "$AUDIOS_JSON" | jq -r '.[]')
            fi
            ;;
          multiframe2video)
            # images 数组（逗号分隔）
            IMAGES_CSV=$(jq -r '.images // [] | join(",")' "$INPUT")
            if [[ -z "$IMAGES_CSV" ]]; then
              echo "ERROR: multiframe2video requires 'images' array" >&2
              exit 1
            fi
            FLAGS+=(--images="$IMAGES_CSV")
            # transition_prompts 数组
            TRANSITION_PROMPTS=$(jq -r '.transition_prompts // []' "$INPUT")
            if [[ "$TRANSITION_PROMPTS" != "[]" ]]; then
              while IFS= read -r tp; do
                FLAGS+=(--transition-prompt="$tp")
              done < <(echo "$TRANSITION_PROMPTS" | jq -r '.[]')
            fi
            # transition_durations 数组
            TRANSITION_DURATIONS=$(jq -r '.transition_durations // []' "$INPUT")
            if [[ "$TRANSITION_DURATIONS" != "[]" ]]; then
              while IFS= read -r td; do
                FLAGS+=(--transition-duration="$td")
              done < <(echo "$TRANSITION_DURATIONS" | jq -r '.[]')
            fi
            ;;
          frames2video)
            FIRST=$(jq -r '.first // empty' "$INPUT")
            LAST=$(jq -r '.last // empty' "$INPUT")
            if [[ -z "$FIRST" || -z "$LAST" ]]; then
              echo "ERROR: frames2video requires 'first' and 'last' fields" >&2
              exit 1
            fi
            FLAGS+=(--first="$FIRST" --last="$LAST")
            ;;
          text2image)
            # 无额外参数
            ;;
          image2image)
            # images 数组（逗号分隔）
            IMAGES_CSV=$(jq -r '.images // [] | join(",")' "$INPUT")
            if [[ -z "$IMAGES_CSV" ]]; then
              echo "ERROR: image2image requires 'images' array" >&2
              exit 1
            fi
            FLAGS+=(--images="$IMAGES_CSV")
            ;;
          image_upscale)
            IMAGE=$(jq -r '.image // empty' "$INPUT")
            if [[ -z "$IMAGE" ]]; then
              echo "ERROR: image_upscale requires 'image' field" >&2
              exit 1
            fi
            FLAGS+=(--image="$IMAGE")
            ;;
          *)
            echo "ERROR: Unknown dreamina command: $COMMAND" >&2
            exit 1
            ;;
        esac

        # 执行 dreamina CLI
        dreamina "$COMMAND" "${FLAGS[@]}"
        ;;

      query)
        # 查询任务结果
        SUBMIT_ID="$INPUT"
        if [[ -z "$SUBMIT_ID" ]]; then
          echo "ERROR: query requires submit_id" >&2
          exit 1
        fi
        dreamina query_result --submit_id="$SUBMIT_ID"
        ;;

      download)
        # 下载结果
        SUBMIT_ID="$INPUT"
        DOWNLOAD_DIR="${4:-.}"
        if [[ -z "$SUBMIT_ID" ]]; then
          echo "ERROR: download requires submit_id" >&2
          exit 1
        fi
        dreamina query_result --submit_id="$SUBMIT_ID" --download_dir="$DOWNLOAD_DIR"
        ;;

      credit)
        # 查询余额
        dreamina user_credit
        ;;

      list)
        # 查看任务列表
        shift 2  # 跳过 service 和 action
        dreamina list_task "$@"
        ;;

      login-check)
        # 检查登录状态（通过 user_credit）
        if dreamina user_credit &>/dev/null; then
          echo '{"logged_in": true}'
        else
          echo '{"logged_in": false}'
        fi
        ;;

      *)
        echo "ERROR: Unknown dreamina action: ${ACTION}" >&2
        echo "Valid actions: submit, query, download, credit, list, login-check" >&2
        exit 1
        ;;
    esac
    ;;

  trace-summary)
    # LLM 摘要生成（需要 DEEPSEEK_API_KEY）
    SESSION_DIR="${ACTION}"  # 第二个参数是 session 目录路径
    if [[ -z "$SESSION_DIR" ]]; then
      echo "ERROR: 用法: $0 trace-summary <session_dir>" >&2
      exit 1
    fi
    if [[ ! -d "$SESSION_DIR" ]]; then
      echo "ERROR: Session 目录不存在: $SESSION_DIR" >&2
      exit 1
    fi

    # 读取摘要模型配置（优先 DEEPSEEK，fallback 到 tuzi）
    if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
      TRACE_API_URL="${DEEPSEEK_API_URL:-https://api.deepseek.com/v1/chat/completions}"
      TRACE_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"
      TRACE_API_KEY="${DEEPSEEK_API_KEY}"
    elif [[ -n "${TUZI_API_KEY:-}" ]]; then
      TRACE_API_URL="https://api.tu-zi.com/v1/chat/completions"
      TRACE_MODEL="nano-banana-vip"
      TRACE_API_KEY="${TUZI_API_KEY}"
      echo "Info: DEEPSEEK_API_KEY not set, using tuzi (nano-banana-vip) for trace summary" >&2
    else
      echo "ERROR: DEEPSEEK_API_KEY 或 TUZI_API_KEY 未设置，请设置其中一个后重试。" >&2
      exit 1
    fi

    # 收集所有 trace 事件
    TRACE_CONTENT=""
    for f in "$SESSION_DIR"/*.jsonl; do
      [[ -f "$f" ]] || continue
      FNAME="$(basename "$f")"
      TRACE_CONTENT+="=== $FNAME ===\n"
      TRACE_CONTENT+="$(cat "$f")\n\n"
    done

    if [[ -z "$TRACE_CONTENT" ]]; then
      echo "ERROR: Session 目录中没有 trace 文件" >&2
      exit 1
    fi

    # 构建摘要 prompt
    SUMMARY_PROMPT="你是一个 AI 短剧生产系统的可观测性分析师。请分析以下 agent trace 日志，生成结构化摘要报告。

报告格式：
# Session 摘要: {session_id}

## 路径标签
每集的 phase 链路 + 关键指标

## 关键决策点
影响最终结果的 agent 决策（编号列表）

## 异常标记
失败、高重试、改写等异常（用 emoji 标记严重程度）

## 质量评估
成功率、重试率、合规覆盖率等指标

## 优化建议
基于异常模式的改进方向

以下是 trace 日志：

$TRACE_CONTENT"

    # 写入临时 payload
    PAYLOAD_FILE="/tmp/trace_summary_payload.json"
    jq -cn \
      --arg model "$TRACE_MODEL" \
      --arg content "$SUMMARY_PROMPT" \
      '{
        model: $model,
        messages: [{role: "user", content: $content}],
        max_tokens: 2000,
        temperature: 0.3
      }' > "$PAYLOAD_FILE"

    # 调用 API
    RESPONSE=$(curl -sS --fail-with-body \
      --connect-timeout "$CONNECT_TIMEOUT" \
      --max-time 120 \
      -H "Authorization: Bearer $TRACE_API_KEY" \
      -H "Content-Type: application/json" \
      -d @"$PAYLOAD_FILE" \
      "$TRACE_API_URL")

    # 提取摘要内容并写入 summary.md
    SUMMARY=$(echo "$RESPONSE" | jq -r '.choices[0].message.content // empty')
    if [[ -z "$SUMMARY" ]]; then
      echo "ERROR: LLM 摘要生成失败，响应: $RESPONSE" >&2
      exit 1
    fi

    echo "$SUMMARY" > "$SESSION_DIR/summary.md"
    echo "摘要已生成: $SESSION_DIR/summary.md"
    rm -f "$PAYLOAD_FILE"
    ;;

  *)
    echo "ERROR: Unknown service: ${SERVICE}" >&2
    echo "Valid services: seedance, image_gen, moderation, tuzi, dreamina, env-check, trace-summary" >&2
    exit 1
    ;;
esac