#!/usr/bin/env bash
# signal.sh — Agent 完成信号写入辅助脚本
# 用法: ./scripts/signal.sh <project> <session-id> <agent-name> <ep> [status] [json-extra]
#
# 示例:
#   ./scripts/signal.sh qyccan batch-20260329 comply-agent ep01
#   ./scripts/signal.sh qyccan batch-20260329 gen-worker ep01 completed '{"shot_id":"ep01-shot-03"}'
#   ./scripts/signal.sh qyccan batch-20260329 repair-agent ep01 failed '{"reason":"max_attempts"}'
#
# 行为:
#   1. 自动创建 projects/{project}/state/signals/ 目录
#   2. 写入信号文件：{session-id}-{agent-name}-{ep}.done
#   3. team-lead 可 watch signals/ 目录，无需轮询 phase 状态文件
#   4. 并行安全（每个 agent 写独立文件）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- 参数校验 ---

if [[ $# -lt 4 ]]; then
  echo "用法: $0 <project> <session-id> <agent-name> <ep> [status] [json-extra]" >&2
  echo "" >&2
  echo "参数:" >&2
  echo "  project      项目名（如 qyccan）" >&2
  echo "  session-id   Session 标识（如 batch-20260329-143000）" >&2
  echo "  agent-name   Agent 名称（如 comply-agent, gen-worker）" >&2
  echo "  ep           剧本 ID（如 ep01）" >&2
  echo "  status       可选，完成状态（默认 completed）" >&2
  echo "  json-extra   可选，JSON 格式的附加信息（如 '{\"shot_id\":\"ep01-shot-03\"}'）" >&2
  exit 1
fi

PROJECT="$1"
SESSION_ID="$2"
AGENT_NAME="$3"
EP="$4"
STATUS="${5:-completed}"
EXTRA="${6:-}"

# 格式校验
for var in PROJECT SESSION_ID AGENT_NAME EP STATUS; do
  val="${!var}"
  if [[ ! "$val" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "错误: $var 只能包含字母、数字、连字符、下划线: $val" >&2
    exit 1
  fi
done

if ! command -v jq &>/dev/null; then
  echo "错误: 需要 jq（brew install jq）" >&2
  exit 1
fi

# --- 创建目录 ---

SIGNALS_DIR="$PROJECT_ROOT/projects/${PROJECT}/state/signals"
mkdir -p "$SIGNALS_DIR"

# --- 生成时间戳 ---

TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# --- 写入信号文件 ---

SIGNAL_FILE="$SIGNALS_DIR/${SESSION_ID}-${AGENT_NAME}-${EP}.done"

BASE_JSON=$(jq -cn \
  --arg agent "$AGENT_NAME" \
  --arg ep "$EP" \
  --arg session "$SESSION_ID" \
  --arg status "$STATUS" \
  --arg ts "$TS" \
  '{agent: $agent, ep: $ep, session: $session, status: $status, ts: $ts}')

if [[ -n "$EXTRA" ]]; then
  if ! echo "$EXTRA" | jq empty 2>/dev/null; then
    echo "错误: json-extra 不是合法 JSON: $EXTRA" >&2
    exit 1
  fi
  echo "$BASE_JSON" | jq -c ". + $EXTRA" > "$SIGNAL_FILE"
else
  echo "$BASE_JSON" > "$SIGNAL_FILE"
fi

echo "✓ 信号已写入: $SIGNAL_FILE"
