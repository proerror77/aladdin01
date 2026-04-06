#!/usr/bin/env bash
# tests/test-agent-workflow-contracts.sh — Agent/Skill 编排契约测试

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_FILE="$(mktemp)"
trap 'rm -f "$RESULTS_FILE"' EXIT

pass() { echo "  PASS: $1"; echo "P" >> "$RESULTS_FILE"; }
fail() { echo "  FAIL: $1"; echo "F" >> "$RESULTS_FILE"; }

assert_contains() {
  local desc="$1" pattern="$2" file="$3"
  if rg -q "$pattern" "$file"; then
    pass "$desc"
  else
    fail "$desc"
  fi
}

assert_order() {
  local desc="$1" first="$2" second="$3" file="$4"
  local first_line second_line
  first_line=$(rg -n "$first" "$file" -m 1 | cut -d: -f1 || true)
  second_line=$(rg -n "$second" "$file" -m 1 | cut -d: -f1 || true)
  if [[ -n "$first_line" && -n "$second_line" && "$first_line" -lt "$second_line" ]]; then
    pass "$desc"
  else
    fail "$desc"
  fi
}

echo ""
echo "=== 1. memory-agent 两段检索 ==="
assert_contains "memory-agent 包含实体检索" 'python3 scripts/vectordb-manager.py search-entities' "$ROOT_DIR/.claude/agents/memory-agent.md"
assert_contains "memory-agent 包含状态检索" 'python3 scripts/vectordb-manager.py get-state' "$ROOT_DIR/.claude/agents/memory-agent.md"
assert_contains "memory-agent 包含关系检索" 'python3 scripts/vectordb-manager.py search-relations' "$ROOT_DIR/.claude/agents/memory-agent.md"
assert_contains "memory-agent 包含资产检索" 'python3 scripts/vectordb-manager.py search-assets' "$ROOT_DIR/.claude/agents/memory-agent.md"
assert_order "memory-agent 先规划再取图" 'python3 scripts/vectordb-manager.py search-relations' 'python3 scripts/vectordb-manager.py search-assets' "$ROOT_DIR/.claude/agents/memory-agent.md"

echo ""
echo "=== 2. 在线状态同步 ==="
assert_contains "gen-worker 写入在线状态" 'python3 scripts/vectordb-manager.py upsert-state' "$ROOT_DIR/.claude/agents/gen-worker.md"
assert_contains "qa-agent 写入在线状态" 'python3 scripts/vectordb-manager.py upsert-state' "$ROOT_DIR/.claude/agents/qa-agent.md"
assert_contains "repair-agent 写入在线状态" 'python3 scripts/vectordb-manager.py upsert-state' "$ROOT_DIR/.claude/agents/repair-agent.md"
assert_contains "qa-agent 使用关系检索" 'python3 scripts/vectordb-manager.py search-relations' "$ROOT_DIR/.claude/agents/qa-agent.md"
assert_contains "qa-agent 使用上一镜状态" 'python3 scripts/vectordb-manager.py get-state' "$ROOT_DIR/.claude/agents/qa-agent.md"

echo ""
echo "=== 3. Phase 2.2 编排接线 ==="
assert_contains "start 接入 narrative-review-agent" 'spawn narrative-review-agent' "$ROOT_DIR/.claude/skills/start.md"
assert_contains "batch 接入 narrative-review-agent" 'spawn narrative-review-agent' "$ROOT_DIR/.claude/skills/batch.md"
assert_contains "status 包含 phase2.2" 'phase2\.2' "$ROOT_DIR/.claude/skills/status.md"
assert_order "start 中 Phase 2.2 先于 Phase 2.3" 'Phase 2\.2' 'Phase 2\.3' "$ROOT_DIR/.claude/skills/start.md"
assert_order "batch 中 Phase 2.2 先于 Phase 2.3" 'Phase 2\.2' 'Phase 2\.3' "$ROOT_DIR/.claude/skills/batch.md"

echo ""
echo "=== 4. 分镜导演逻辑 ==="
assert_contains "visual-agent 定义 shot_purpose" 'shot_purpose' "$ROOT_DIR/.claude/agents/visual-agent.md"
assert_contains "visual-agent 定义 transition_from_previous" 'transition_from_previous' "$ROOT_DIR/.claude/agents/visual-agent.md"
assert_contains "visual-agent 定义 dramatic_role" 'dramatic_role' "$ROOT_DIR/.claude/agents/visual-agent.md"
assert_contains "storyboard-agent 使用 dramatic_role" 'dramatic_role' "$ROOT_DIR/.claude/agents/storyboard-agent.md"
assert_contains "narrative-review-agent 检查上一镜叫出下一镜" '上一镜.*下一镜|叫出下一镜|next_hook|transition_from_previous' "$ROOT_DIR/.claude/agents/narrative-review-agent.md"
assert_contains "shot-compiler-agent 写入 emotional_target" 'emotional_target' "$ROOT_DIR/.claude/agents/shot-compiler-agent.md"
assert_contains "shot-compiler-agent 写入 information_delta" 'information_delta' "$ROOT_DIR/.claude/agents/shot-compiler-agent.md"
assert_contains "shot-compiler-agent 写入 next_hook" 'next_hook' "$ROOT_DIR/.claude/agents/shot-compiler-agent.md"

echo ""
echo "=== 5. shot-state 中间层契约 ==="
assert_contains "memory-agent 读取 shot-state" 'shot-state' "$ROOT_DIR/.claude/agents/memory-agent.md"
assert_contains "memory-agent 使用 preferred_view" 'preferred_view|selected_views' "$ROOT_DIR/.claude/agents/memory-agent.md"
assert_contains "shot-compiler-agent 写入 selected_views" 'selected_views' "$ROOT_DIR/.claude/agents/shot-compiler-agent.md"
assert_contains "shot-compiler-agent 写入 continuity_inputs" 'continuity_inputs' "$ROOT_DIR/.claude/agents/shot-compiler-agent.md"
assert_contains "qa-agent 校验 selected_views" 'selected_views|preferred_view' "$ROOT_DIR/.claude/agents/qa-agent.md"

echo ""
echo "=== 6. narrative-review reject 路径 ==="
assert_contains "start 处理 narrative-review reject" 'reject' "$ROOT_DIR/.claude/skills/start.md"
assert_contains "start 有 reject 重试逻辑" 'NARRATIVE_RETRY|NARRATIVE_MAX_RETRIES' "$ROOT_DIR/.claude/skills/start.md"
assert_contains "batch 处理 narrative-review reject" 'reject' "$ROOT_DIR/.claude/skills/batch.md"
assert_contains "batch 有 reject 重试逻辑" 'NARRATIVE_RETRY|NARRATIVE_MAX_RETRIES' "$ROOT_DIR/.claude/skills/batch.md"

echo ""
echo "=== 7. v2.0 触发条件一致性 ==="
assert_contains "start Phase 6 检查 world-model" 'world-model' "$ROOT_DIR/.claude/skills/start.md"
assert_contains "batch Phase 6 检查 world-model" 'world-model' "$ROOT_DIR/.claude/skills/batch.md"

echo ""
echo "=== 8. Phase 3.5 并行化 ==="
assert_contains "start Phase 3.5 并行 spawn" 'wait_all|并行' "$ROOT_DIR/.claude/skills/start.md"
assert_contains "batch Phase 3.5 并行 spawn" 'wait_all|并行' "$ROOT_DIR/.claude/skills/batch.md"

PASS_COUNT=$(grep -c '^P$' "$RESULTS_FILE" 2>/dev/null || true)
FAIL_COUNT=$(grep -c '^F$' "$RESULTS_FILE" 2>/dev/null || true)
TOTAL=$((PASS_COUNT + FAIL_COUNT))

echo ""
echo "══════════════════════════════════════"
echo "  结果：$PASS_COUNT 通过 / $TOTAL 总计"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  echo "  $FAIL_COUNT 个测试失败"
  echo "══════════════════════════════════════"
  exit 1
else
  echo "  全部通过 ✓"
  echo "══════════════════════════════════════"
  exit 0
fi
