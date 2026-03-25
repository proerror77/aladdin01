#!/usr/bin/env bash
# api-caller.sh - 统一 API 调用脚本
# 用法：
#   ./scripts/api-caller.sh seedance create <payload.json>   # 创建视频生成任务
#   ./scripts/api-caller.sh seedance status <task_id>        # 查询任务状态
#   ./scripts/api-caller.sh seedance download <video_url> <output_file>  # 下载视频
#   ./scripts/api-caller.sh image_gen generate <payload.json>
#   ./scripts/api-caller.sh image_gen download <image_url> <output_file>
#   ./scripts/api-caller.sh moderation check-file <text_file>
#   ./scripts/api-caller.sh env-check  # 检查环境变量
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
  echo "Services: seedance, image_gen, moderation, env-check" >&2
  exit 1
fi

if [[ "$SERVICE" != "env-check" && -z "$ACTION" ]]; then
  echo "Usage: $0 <service> <action> <input>" >&2
  echo "Services: seedance, image_gen, moderation, env-check" >&2
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

# 环境变量检查
if [[ "$SERVICE" == "env-check" ]]; then
  missing=0
  [[ -z "${ARK_API_KEY:-}" ]] && echo "Missing: ARK_API_KEY" >&2 && ((missing++))
  [[ -z "${IMAGE_GEN_API_URL:-}" ]] && echo "Missing: IMAGE_GEN_API_URL" >&2 && ((missing++))
  [[ -z "${IMAGE_GEN_API_KEY:-}" ]] && echo "Missing: IMAGE_GEN_API_KEY" >&2 && ((missing++))
  [[ -z "${OPENAI_API_KEY:-}" ]] && echo "Missing: OPENAI_API_KEY" >&2 && ((missing++))
  if [[ $missing -eq 0 ]]; then
    echo "All environment variables are set."
    exit 0
  else
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
        safe_curl "$SEEDANCE_MAX_TIME" -X POST "${BASE_URL}/contents/generations/tasks" \
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
    if [[ -z "$BASE_URL" || -z "$API_KEY" ]]; then
      echo "ERROR: IMAGE_GEN_API_URL and IMAGE_GEN_API_KEY must be set" >&2
      exit 1
    fi
    # 规范化 BASE_URL
    BASE_URL=$(normalize_base_url "$BASE_URL")

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

  *)
    echo "ERROR: Unknown service: ${SERVICE}" >&2
    echo "Valid services: seedance, image_gen, moderation, env-check" >&2
    exit 1
    ;;
esac