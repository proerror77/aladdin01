#!/usr/bin/env bash
# trace.sh — Agent Trace Log 写入辅助脚本
# 用法: ./scripts/trace.sh <session-id> <trace-file> <step> [json-detail]
#
# 示例:
#   ./scripts/trace.sh batch-20260329-143000 session session_start '{"type":"batch","episodes":["ep01"]}'
#   ./scripts/trace.sh batch-20260329-143000 ep01-phase1-trace read_input '{"input":"script/ep01.md","size":1234}'
#
# 行为:
#   1. 自动创建 state/traces/{session-id}/ 目录
#   2. 自动添加 ts 字段（ISO8601 UTC）
#   3. Append 一行 JSON 到 state/traces/{session-id}/{trace-file}.jsonl
#   4. 并行安全（每个 agent 写独立文件，无共享写入）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRACES_DIR="$PROJECT_ROOT/state/traces"

# --- 参数校验 ---

if [[ $# -lt 3 ]]; then
  echo "用法: $0 <session-id> <trace-file> <step> [json-detail]" >&2
  echo "" >&2
  echo "参数:" >&2
  echo "  session-id   Session 标识（如 batch-20260329-143000）" >&2
  echo "  trace-file   Trace 文件名，不含扩展名（如 session, ep01-phase1-trace）" >&2
  echo "  step         步骤名称（如 read_input, api_submit, spawn）" >&2
  echo "  json-detail  可选，JSON 格式的详情（如 '{\"input\":\"file.md\"}'）" >&2
  exit 1
fi

SESSION_ID="$1"
TRACE_FILE="$2"
STEP="$3"
DETAIL="${4:-}"

# 校验 session-id 格式（字母数字和连字符）
if [[ ! "$SESSION_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "错误: session-id 只能包含字母、数字、连字符、下划线: $SESSION_ID" >&2
  exit 1
fi

# 校验 trace-file 格式
if [[ ! "$TRACE_FILE" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "错误: trace-file 只能包含字母、数字、连字符、下划线: $TRACE_FILE" >&2
  exit 1
fi

# 校验 step 格式
if [[ ! "$STEP" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "错误: step 只能包含字母、数字、连字符、下划线: $STEP" >&2
  exit 1
fi

# --- 检查 jq ---

if ! command -v jq &>/dev/null; then
  echo "错误: 需要 jq（brew install jq）" >&2
  exit 1
fi

# --- 创建目录 ---

SESSION_DIR="$TRACES_DIR/$SESSION_ID"
mkdir -p "$SESSION_DIR"

# --- 生成时间戳 ---

TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# --- 构建 JSON 行 ---

OUTPUT_FILE="$SESSION_DIR/${TRACE_FILE}.jsonl"

if [[ -n "$DETAIL" ]]; then
  # 校验 detail 是合法 JSON
  if ! echo "$DETAIL" | jq empty 2>/dev/null; then
    echo "错误: json-detail 不是合法 JSON: $DETAIL" >&2
    exit 1
  fi
  # 合并 ts + step + detail 字段
  echo "$DETAIL" | jq -c --arg ts "$TS" --arg step "$STEP" \
    '{ts: $ts, step: $step} + .' >> "$OUTPUT_FILE"
else
  # 只有 ts + step
  jq -cn --arg ts "$TS" --arg step "$STEP" \
    '{ts: $ts, step: $step}' >> "$OUTPUT_FILE"
fi
