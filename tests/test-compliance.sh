#!/usr/bin/env bash
# tests/test-compliance.sh — 合规层配置验证测试
# 用法：bash tests/test-compliance.sh
# 验证 blocklist.yaml、rewrite-patterns.yaml、auto-gate-rules.yaml 的格式与逻辑

RESULTS_FILE=$(mktemp)
trap 'rm -f "$RESULTS_FILE"' EXIT

pass() { echo "  PASS: $1"; echo "P" >> "$RESULTS_FILE"; }
fail() { echo "  FAIL: $1"; echo "F" >> "$RESULTS_FILE"; }

# ── 前置条件：python3 + pyyaml ────────────────────────────────────────────────

if ! python3 -c "import yaml" 2>/dev/null; then
  echo "ERROR: pyyaml 未安装。运行：pip3 install pyyaml" >&2
  exit 1
fi

# ── 1. YAML 格式合法性 ────────────────────────────────────────────────────────

echo ""
echo "=== 1. YAML 格式合法性 ==="

for f in \
  config/compliance/blocklist.yaml \
  config/compliance/rewrite-patterns.yaml \
  config/compliance/policy-rules.yaml \
  config/scoring/auto-gate-rules.yaml; do
  if [[ ! -f "$f" ]]; then
    fail "$f 文件不存在"
    continue
  fi
  set +e
  python3 -c "import yaml,sys; yaml.safe_load(open('$f'))" 2>/dev/null
  code=$?
  set -e
  if [[ $code -eq 0 ]]; then pass "$f YAML 格式合法"; else fail "$f YAML 格式错误"; fi
done

# ── 2. blocklist.yaml 结构校验 ────────────────────────────────────────────────

echo ""
echo "=== 2. blocklist.yaml 结构校验 ==="

python3 - <<'PYEOF'
import yaml, sys

data = yaml.safe_load(open("config/compliance/blocklist.yaml"))
errors = []

# 必须有 version 字段
if "version" not in data:
    errors.append("缺少 version 字段")

# 每个分类必须有 keywords 和 patterns
required_categories = ["violence", "sexual", "abuse", "illegal", "political"]
for cat in required_categories:
    if cat not in data:
        errors.append(f"缺少分类: {cat}")
        continue
    entry = data[cat]
    if "keywords" not in entry:
        errors.append(f"{cat} 缺少 keywords 字段")
    elif not isinstance(entry["keywords"], list):
        errors.append(f"{cat}.keywords 不是列表")
    elif len(entry["keywords"]) == 0:
        errors.append(f"{cat}.keywords 为空列表")
    if "patterns" not in entry:
        errors.append(f"{cat} 缺少 patterns 字段")
    elif not isinstance(entry["patterns"], list):
        errors.append(f"{cat}.patterns 不是列表")

if errors:
    for e in errors:
        print(f"  FAIL: {e}")
        open("/tmp/compliance_results", "a").write("F\n")
else:
    print("  PASS: blocklist.yaml 结构完整（5 个分类，keywords+patterns 齐全）")
    open("/tmp/compliance_results", "a").write("P\n")
PYEOF

# 把 python 结果合并到 RESULTS_FILE
cat /tmp/compliance_results >> "$RESULTS_FILE" 2>/dev/null || true
rm -f /tmp/compliance_results

# ── 3. blocklist.yaml 关键词非空校验 ─────────────────────────────────────────

echo ""
echo "=== 3. blocklist.yaml 关键词内容校验 ==="

python3 - <<'PYEOF'
import yaml

data = yaml.safe_load(open("config/compliance/blocklist.yaml"))
results = []

for cat, entry in data.items():
    if cat == "version":
        continue
    if not isinstance(entry, dict):
        continue
    keywords = entry.get("keywords", [])
    for kw in keywords:
        if not isinstance(kw, str) or len(kw.strip()) == 0:
            results.append(("F", f"{cat} 包含空关键词"))
            break
    else:
        results.append(("P", f"{cat} 关键词格式正常（{len(keywords)} 个）"))

for status, msg in results:
    print(f"  {'PASS' if status == 'P' else 'FAIL'}: {msg}")
    open("/tmp/compliance_results", "a").write(status + "\n")
PYEOF

cat /tmp/compliance_results >> "$RESULTS_FILE" 2>/dev/null || true
rm -f /tmp/compliance_results

# ── 4. auto-gate-rules.yaml 权重合计校验 ─────────────────────────────────────

echo ""
echo "=== 4. auto-gate-rules.yaml 权重合计校验 ==="

python3 - <<'PYEOF'
import yaml

data = yaml.safe_load(open("config/scoring/auto-gate-rules.yaml"))
results = []

def check_weights(section_path, dimensions):
    total = sum(d.get("weight", 0) for d in dimensions)
    # 允许浮点误差
    if abs(total - 1.0) < 0.001:
        results.append(("P", f"{section_path} 权重合计 = {total:.2f} ✓"))
    else:
        results.append(("F", f"{section_path} 权重合计 = {total:.2f}（应为 1.0）"))

# text_scoring
for key, val in data.get("text_scoring", {}).items():
    dims = val.get("dimensions", [])
    if dims:
        check_weights(f"text_scoring.{key}", dims)

# prompt_scoring
for key, val in data.get("prompt_scoring", {}).items():
    dims = val.get("dimensions", [])
    if dims:
        check_weights(f"prompt_scoring.{key}", dims)

# visual_scoring
for key, val in data.get("visual_scoring", {}).items():
    dims = val.get("dimensions", [])
    if dims:
        check_weights(f"visual_scoring.{key}", dims)

# 阈值合理性
defaults = data.get("defaults", {})
approve = defaults.get("auto_approve_threshold", 0)
reject = defaults.get("auto_reject_threshold", 0)
if approve > reject:
    results.append(("P", f"阈值合理：auto_approve({approve}) > auto_reject({reject})"))
else:
    results.append(("F", f"阈值异常：auto_approve({approve}) <= auto_reject({reject})"))

for status, msg in results:
    print(f"  {'PASS' if status == 'P' else 'FAIL'}: {msg}")
    open("/tmp/compliance_results", "a").write(status + "\n")
PYEOF

cat /tmp/compliance_results >> "$RESULTS_FILE" 2>/dev/null || true
rm -f /tmp/compliance_results

# ── 5. rewrite-patterns.yaml 结构校验 ────────────────────────────────────────

echo ""
echo "=== 5. rewrite-patterns.yaml 结构校验 ==="

python3 - <<'PYEOF'
import yaml

data = yaml.safe_load(open("config/compliance/rewrite-patterns.yaml"))
results = []

# 必须有 principles 和 llm_rewrite_prompt
if "principles" in data and isinstance(data["principles"], list) and len(data["principles"]) > 0:
    results.append(("P", f"principles 字段存在（{len(data['principles'])} 条原则）"))
else:
    results.append(("F", "principles 字段缺失或为空"))

if "llm_rewrite_prompt" in data and isinstance(data["llm_rewrite_prompt"], str):
    prompt = data["llm_rewrite_prompt"]
    if "{original_prompt}" in prompt and "{rejection_reason}" in prompt:
        results.append(("P", "llm_rewrite_prompt 包含必要占位符"))
    else:
        results.append(("F", "llm_rewrite_prompt 缺少 {original_prompt} 或 {rejection_reason}"))
else:
    results.append(("F", "llm_rewrite_prompt 字段缺失"))

# 改写模式列表格式
for key in ["violence_rewrites", "sexual_rewrites", "conflict_rewrites"]:
    if key in data:
        items = data[key]
        if isinstance(items, list):
            valid = all("pattern" in i and "rewrite" in i for i in items)
            if valid:
                results.append(("P", f"{key} 格式正常（{len(items)} 条）"))
            else:
                results.append(("F", f"{key} 某条目缺少 pattern 或 rewrite 字段"))

for status, msg in results:
    print(f"  {'PASS' if status == 'P' else 'FAIL'}: {msg}")
    open("/tmp/compliance_results", "a").write(status + "\n")
PYEOF

cat /tmp/compliance_results >> "$RESULTS_FILE" 2>/dev/null || true
rm -f /tmp/compliance_results

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
