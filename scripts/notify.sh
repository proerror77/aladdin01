#!/usr/bin/env bash
# notify.sh — 飞书通知发送脚本
#
# 用法:
#   ./scripts/notify.sh review <review-state-file>     # 发送审核卡片（根据 type 自动选模板）
#   ./scripts/notify.sh alert <project> <title> <detail> [trace_url]  # 发送告警卡片
#
# 环境变量:
#   LARK_APP_ID       — 飞书应用 App ID（必需）
#   LARK_APP_SECRET   — 飞书应用 App Secret（必需）
#   REVIEW_SERVER_URL — Review Server 地址（默认 http://localhost:8080）
#
# 依赖:
#   - lark-cli（飞书 CLI 工具）
#   - jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LARK_CONFIG="$PROJECT_ROOT/config/lark/lark-config.yaml"
REVIEW_SERVER_URL="${REVIEW_SERVER_URL:-http://localhost:8080}"

# --- 参数校验 ---

if [[ $# -lt 1 ]]; then
  echo "用法:" >&2
  echo "  $0 review <review-state-file>" >&2
  echo "  $0 alert <project> <title> <detail> [trace_url]" >&2
  exit 1
fi

COMMAND="$1"
shift

# --- 检查依赖 ---

if ! command -v jq &>/dev/null; then
  echo "ERROR: 需要 jq（brew install jq）" >&2
  exit 1
fi

# --- 读取配置 ---

# 从 YAML 中提取 chat_id（简单方式，不依赖 python yaml）
get_yaml_value() {
  local file="$1" key="$2"
  grep "^${key}:" "$file" 2>/dev/null | sed 's/^[^:]*: *//' | sed 's/"//g' | sed "s/'//g" | head -1
}

CHAT_ID="$(get_yaml_value "$LARK_CONFIG" "chat_id")"
if [[ -z "$CHAT_ID" ]]; then
  echo "ERROR: config/lark/lark-config.yaml 中 chat_id 未配置" >&2
  exit 1
fi

# --- 审核通知 ---

send_review() {
  local review_file="$1"

  if [[ ! -f "$review_file" ]]; then
    echo "ERROR: Review state 文件不存在: $review_file" >&2
    exit 1
  fi

  local review_id project stage checkpoint type iteration summary files review_url
  review_id="$(jq -r '.id' "$review_file")"
  project="$(jq -r '.project' "$review_file")"
  stage="$(jq -r '.stage' "$review_file")"
  checkpoint="$(jq -r '.checkpoint' "$review_file")"
  type="$(jq -r '.type' "$review_file")"
  iteration="$(jq -r '.iteration' "$review_file")"
  summary="$(jq -r '.content.summary' "$review_file")"
  files="$(jq -r '.content.files | join("\n")' "$review_file")"
  review_url="${REVIEW_SERVER_URL}/review/${review_id}"

  local title
  title="$(jq -r '.content.title' "$review_file")"

  # 更新 review state 的 review_url
  jq --arg url "$review_url" '.review_url = $url' "$review_file" > "${review_file}.tmp" \
    && mv "${review_file}.tmp" "$review_file"

  local created_at
  created_at="$(date -u +"%Y-%m-%d %H:%M UTC")"

  if [[ "$type" == "text" ]]; then
    # 文字类：发送带按钮的卡片
    local card_json
    card_json=$(jq -n \
      --arg title "$title" \
      --arg project "$project" \
      --arg stage "$stage" \
      --arg checkpoint "$checkpoint" \
      --arg iteration "$iteration" \
      --arg summary "$summary" \
      --arg files "$files" \
      --arg review_id "$review_id" \
      --arg webhook_url "${REVIEW_SERVER_URL}/webhook/lark" \
      --arg created_at "$created_at" \
      '{
        "msg_type": "interactive",
        "card": {
          "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": ("🎬 [" + $project + "] " + $title)}
          },
          "elements": [
            {
              "tag": "div",
              "fields": [
                {"is_short": true, "text": {"tag": "lark_md", "content": ("**项目**\n" + $project)}},
                {"is_short": true, "text": {"tag": "lark_md", "content": ("**迭代轮次**\n第 " + $iteration + " 轮")}}
              ]
            },
            {"tag": "div", "text": {"tag": "lark_md", "content": ("📄 **摘要**\n" + $summary)}},
            {"tag": "div", "text": {"tag": "lark_md", "content": ("📁 **文件**\n" + $files)}},
            {"tag": "hr"},
            {
              "tag": "action",
              "actions": [
                {
                  "tag": "button",
                  "text": {"tag": "plain_text", "content": "✅ 通过"},
                  "type": "primary",
                  "value": {"action": "approve", "review_id": $review_id}
                },
                {
                  "tag": "button",
                  "text": {"tag": "plain_text", "content": "🔄 重做"},
                  "type": "default",
                  "value": {"action": "redo", "review_id": $review_id}
                },
                {
                  "tag": "button",
                  "text": {"tag": "plain_text", "content": "❌ 终止"},
                  "type": "danger",
                  "value": {"action": "terminate", "review_id": $review_id}
                }
              ]
            }
          ]
        }
      }')

    echo "$card_json" > "/tmp/lark_card_${review_id}.json"
    echo "发送文字审核卡片: $review_id → $CHAT_ID"

    # 通过 lark-cli 发送（如果可用），否则 fallback 到 curl webhook
    if command -v lark-cli &>/dev/null; then
      lark-cli im +send --chat-id "$CHAT_ID" --msg-type interactive --content "@/tmp/lark_card_${review_id}.json"
    else
      echo "WARNING: lark-cli 不可用，卡片 JSON 已保存到 /tmp/lark_card_${review_id}.json" >&2
      echo "请手动发送或配置 lark-cli" >&2
    fi

  elif [[ "$type" == "visual" || "$type" == "video" ]]; then
    # 视觉/视频类：发送带 Web 链接的卡片
    local thumbnail_count
    thumbnail_count="$(jq -r '.assets | length' "$review_file")"

    local card_json
    card_json=$(jq -n \
      --arg title "$title" \
      --arg project "$project" \
      --arg iteration "$iteration" \
      --arg summary "$summary" \
      --arg review_url "$review_url" \
      --arg thumbnail_count "$thumbnail_count" \
      '{
        "msg_type": "interactive",
        "card": {
          "header": {
            "template": "purple",
            "title": {"tag": "plain_text", "content": ("🎨 [" + $project + "] " + $title)}
          },
          "elements": [
            {
              "tag": "div",
              "fields": [
                {"is_short": true, "text": {"tag": "lark_md", "content": ("**项目**\n" + $project)}},
                {"is_short": true, "text": {"tag": "lark_md", "content": ("**迭代**\n第 " + $iteration + " 轮")}}
              ]
            },
            {"tag": "div", "text": {"tag": "lark_md", "content": ("📄 " + $summary + "\n🖼️ 共 " + $thumbnail_count + " 个资源待审核")}},
            {"tag": "hr"},
            {
              "tag": "action",
              "actions": [
                {
                  "tag": "button",
                  "text": {"tag": "plain_text", "content": "🔍 在浏览器中审核"},
                  "type": "primary",
                  "url": $review_url
                }
              ]
            },
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "视觉内容请在 Web 页面审核"}]}
          ]
        }
      }')

    echo "$card_json" > "/tmp/lark_card_${review_id}.json"
    echo "发送视觉审核卡片: $review_id → $CHAT_ID (Web: $review_url)"

    if command -v lark-cli &>/dev/null; then
      lark-cli im +send --chat-id "$CHAT_ID" --msg-type interactive --content "@/tmp/lark_card_${review_id}.json"
    else
      echo "WARNING: lark-cli 不可用，卡片 JSON 已保存到 /tmp/lark_card_${review_id}.json" >&2
    fi
  fi

  rm -f "/tmp/lark_card_${review_id}.json"
  echo "通知已发送: $review_id"
}

# --- 告警通知 ---

send_alert() {
  local project="$1"
  local title="$2"
  local detail="$3"
  local trace_url="${4:-}"

  local card_json
  card_json=$(jq -n \
    --arg title "$title" \
    --arg project "$project" \
    --arg detail "$detail" \
    --arg trace_url "$trace_url" \
    '{
      "msg_type": "interactive",
      "card": {
        "header": {
          "template": "red",
          "title": {"tag": "plain_text", "content": ("⚠️ [" + $project + "] " + $title)}
        },
        "elements": [
          {"tag": "div", "text": {"tag": "lark_md", "content": $detail}},
          {"tag": "hr"},
          (if $trace_url != "" then
            {"tag": "action", "actions": [{"tag": "button", "text": {"tag": "plain_text", "content": "🔍 查看 Trace"}, "type": "default", "url": $trace_url}]}
          else
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "无 Trace 链接"}]}
          end)
        ]
      }
    }')

  local alert_id
  alert_id="alert-$(date +%Y%m%d-%H%M%S)"
  echo "$card_json" > "/tmp/lark_${alert_id}.json"
  echo "发送告警: $project — $title"

  if command -v lark-cli &>/dev/null; then
    lark-cli im +send --chat-id "$CHAT_ID" --msg-type interactive --content "@/tmp/lark_${alert_id}.json"
  else
    echo "WARNING: lark-cli 不可用，告警 JSON 已保存到 /tmp/lark_${alert_id}.json" >&2
  fi

  rm -f "/tmp/lark_${alert_id}.json"
}

# --- 主入口 ---

case "$COMMAND" in
  review)
    [[ $# -lt 1 ]] && { echo "用法: $0 review <review-state-file>" >&2; exit 1; }
    send_review "$1"
    ;;
  alert)
    [[ $# -lt 3 ]] && { echo "用法: $0 alert <project> <title> <detail> [trace_url]" >&2; exit 1; }
    send_alert "$1" "$2" "$3" "${4:-}"
    ;;
  *)
    echo "ERROR: 未知命令: $COMMAND" >&2
    echo "可用命令: review, alert" >&2
    exit 1
    ;;
esac
