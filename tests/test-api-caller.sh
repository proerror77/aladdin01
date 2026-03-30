#!/usr/bin/env bash
# tests/test-api-caller.sh — api-caller.sh 单元测试
# 用法：bash tests/test-api-caller.sh
# 不调用任何外部 API，纯本地逻辑验证

SCRIPT="./scripts/api-caller.sh"
RESULTS_FILE=$(mktemp)
trap 'rm -f "$RESULTS_FILE"' EXIT

# ── 测试工具 ──────────────────────────────────────────────────────────────────

pass() { echo "  PASS: $1"; echo "P" >> "$RESULTS_FILE"; }
fail() { echo "  FAIL: $1"; echo "F" >> "$RESULTS_FILE"; }

# 断言退出码
assert_exit() {
  local desc="$1" expected="$2"
  shift 2
  local actual
  set +e; "$@" >/dev/null 2>&1; actual=$?; set -e
  if [[ "$actual" -eq "$expected" ]]; then pass "$desc"; else fail "$desc (expected exit $expected, got $actual)"; fi
}

# 断言输出包含某字符串
assert_contains() {
  local desc="$1" pattern="$2"
  shift 2
  local output
  set +e; output=$("$@" 2>&1); set -e
  if echo "$output" | grep -q "$pattern"; then pass "$desc"; else fail "$desc (pattern '$pattern' not found)"; fi
}

# ── 1. 参数校验 ───────────────────────────────────────────────────────────────

echo ""
echo "=== 1. 参数校验 ==="

assert_exit "无参数 → exit 1" 1 bash "$SCRIPT"
assert_exit "只有 service 无 action → exit 1" 1 bash "$SCRIPT" seedance
assert_contains "无参数输出 Usage" "Usage" bash "$SCRIPT"

# ── 2. env-check ──────────────────────────────────────────────────────────────

echo ""
echo "=== 2. env-check ==="

run_env_check_missing() {
  local output code
  set +e
  output=$(env -i HOME="$HOME" PATH="$PATH" bash "$SCRIPT" env-check 2>&1)
  code=$?
  set -e
  if echo "$output" | grep -q "Missing: ARK_API_KEY"; then pass "缺少 ARK_API_KEY 时报错"; else fail "缺少 ARK_API_KEY 时未报错 ($output)"; fi
  if [[ $code -ne 0 ]]; then pass "缺少必要变量时 exit 非 0"; else fail "缺少必要变量时 exit 0"; fi
}
run_env_check_missing

run_env_check_full() {
  local output code
  set +e
  output=$(ARK_API_KEY="test-key" IMAGE_GEN_API_URL="https://example.com" IMAGE_GEN_API_KEY="test-img-key" bash "$SCRIPT" env-check 2>&1)
  code=$?
  set -e
  if [[ $code -eq 0 ]]; then pass "必要变量齐全时 exit 0"; else fail "必要变量齐全时 exit 非 0 ($output)"; fi
}
run_env_check_full

run_env_check_tuzi() {
  local output code
  set +e
  output=$(ARK_API_KEY="test-key" TUZI_API_KEY="tuzi-key" bash "$SCRIPT" env-check 2>&1)
  code=$?
  set -e
  if [[ $code -eq 0 ]]; then pass "TUZI_API_KEY 可作为 IMAGE_GEN fallback"; else fail "TUZI_API_KEY fallback 未生效 ($output)"; fi
}
run_env_check_tuzi

# ── 3. task_id 格式校验 ───────────────────────────────────────────────────────

echo ""
echo "=== 3. task_id 格式校验 ==="

run_taskid_traversal() {
  local output
  set +e; output=$(ARK_API_KEY="test-key" bash "$SCRIPT" seedance status "../../../etc/passwd" 2>&1); set -e
  if echo "$output" | grep -q "Invalid task_id"; then pass "路径遍历 task_id 被拒绝"; else fail "路径遍历 task_id 未被拒绝 ($output)"; fi
}
run_taskid_traversal

run_taskid_valid() {
  local output
  set +e; output=$(ARK_API_KEY="test-key" bash "$SCRIPT" seedance status "task-abc123_XYZ" 2>&1); set -e
  if ! echo "$output" | grep -q "Invalid task_id"; then pass "合法 task_id 通过格式校验"; else fail "合法 task_id 被错误拒绝"; fi
}
run_taskid_valid

# ── 4. 输出路径安全校验 ───────────────────────────────────────────────────────

echo ""
echo "=== 4. 输出路径安全校验 ==="

run_path_traversal() {
  local output
  set +e; output=$(ARK_API_KEY="test-key" bash "$SCRIPT" seedance download "https://example.com/v.mp4" "../../../tmp/evil.mp4" 2>&1); set -e
  if echo "$output" | grep -qE "Path traversal|Absolute paths"; then pass "路径遍历输出路径被拒绝"; else fail "路径遍历输出路径未被拒绝 ($output)"; fi
}
run_path_traversal

run_path_absolute() {
  local output
  set +e; output=$(ARK_API_KEY="test-key" bash "$SCRIPT" seedance download "https://example.com/v.mp4" "/tmp/evil.mp4" 2>&1); set -e
  if echo "$output" | grep -q "Absolute paths not allowed"; then pass "绝对路径输出被拒绝"; else fail "绝对路径输出未被拒绝 ($output)"; fi
}
run_path_absolute

# ── 5. URL 安全校验 ───────────────────────────────────────────────────────────

echo ""
echo "=== 5. URL 安全校验 ==="

run_url_http() {
  local output
  set +e; output=$(ARK_API_KEY="test-key" bash "$SCRIPT" seedance download "http://example.com/v.mp4" "output.mp4" 2>&1); set -e
  if echo "$output" | grep -q "Only HTTPS URLs"; then pass "HTTP URL 被拒绝（仅允许 HTTPS）"; else fail "HTTP URL 未被拒绝 ($output)"; fi
}
run_url_http

# ── 6. payload 文件存在性校验 ─────────────────────────────────────────────────

echo ""
echo "=== 6. payload 文件校验 ==="

run_payload_missing() {
  local output
  set +e; output=$(ARK_API_KEY="test-key" bash "$SCRIPT" seedance create "/nonexistent/payload.json" 2>&1); set -e
  if echo "$output" | grep -q "not found"; then pass "不存在的 payload 文件被拒绝"; else fail "不存在的 payload 文件未被拒绝 ($output)"; fi
}
run_payload_missing

# ── 结果汇总 ──────────────────────────────────────────────────────────────────

PASS=$(grep -c "^P$" "$RESULTS_FILE" 2>/dev/null) || PASS=0
FAIL=$(grep -c "^F$" "$RESULTS_FILE" 2>/dev/null) || FAIL=0
TOTAL=$((PASS + FAIL))

echo ""
echo "══════════════════════════════════════"
echo "  结果：$PASS 通过 / $TOTAL 总计"
if [[ $FAIL -gt 0 ]]; then
  echo "  $FAIL 个测试失败"
  echo "══════════════════════════════════════"
  exit 1
else
  echo "  全部通过 ✓"
  echo "══════════════════════════════════════"
  exit 0
fi
