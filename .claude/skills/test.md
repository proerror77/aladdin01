# ~test — 配置验证 + Dry-run 模式

不调用任何外部 API，验证项目配置和状态文件的完整性。在正式运行 `~start` / `~batch` 前用来排查配置错误。

## 使用方式

```
~test                    # 运行全部检查
~test --config           # 只检查配置文件
~test --state            # 只检查状态文件
~test --env              # 只检查环境变量
```

## 检查项目

### 环境变量检查（--env）

运行 `./scripts/api-caller.sh env-check`，输出缺失的必要变量和可选变量状态。

### 配置文件检查（--config）

1. **YAML 格式合法性**：验证以下文件可被 `python3 -c "import yaml; yaml.safe_load(...)"` 解析：
   - `config/compliance/blocklist.yaml`
   - `config/compliance/policy-rules.yaml`
   - `config/compliance/rewrite-patterns.yaml`
   - `config/scoring/auto-gate-rules.yaml`
   - `config/platforms/seedance-v2.yaml`
   - `config/api-endpoints.yaml`

2. **平台配置完整性**：检查 `config/platforms/seedance-v2.yaml` 包含必要字段：
   - `generation_backend`（值为 `api` 或 `browser`）
   - `model`
   - `max_retries`

3. **合规配置完整性**：运行 `bash tests/test-compliance.sh`（如果存在）

### 状态文件检查（--state）

1. **state/ 目录存在**：`state/` 目录存在且可写
2. **进度文件格式**：对每个 `state/*-phase*.json` 文件，验证：
   - 是合法 JSON
   - 包含 `status` 字段
   - `status` 值为 `pending` / `in_progress` / `completed` / `failed` 之一
3. **孤立状态文件**：检测 `state/` 中有状态文件但 `script/` 中没有对应剧本的情况（提示而不报错）
4. **design-lock.json**：如果存在，验证是合法 JSON

### 测试套件（全量）

如果 `tests/` 目录存在，运行所有 `tests/test-*.sh`：
```bash
for f in tests/test-*.sh; do
  bash "$f" || echo "FAILED: $f"
done
```

## 输出格式

```
=== 环境变量 ===
  ✓ ARK_API_KEY 已设置
  ✓ TUZI_API_KEY 已设置（IMAGE_GEN fallback）
  ⚠ OPENAI_API_KEY 未设置（可选，Moderation API）

=== 配置文件 ===
  ✓ config/compliance/blocklist.yaml 格式合法
  ✓ config/platforms/seedance-v2.yaml 字段完整
  ✓ 合规测试套件：21/21 通过

=== 状态文件 ===
  ✓ state/ 目录可写
  ✓ 3 个状态文件格式合法
  ⚠ 孤立状态文件：state/ep99-phase1.json（script/ep99.md 不存在）

=== 测试套件 ===
  ✓ tests/test-api-caller.sh：13/13 通过
  ✓ tests/test-compliance.sh：21/21 通过

══════════════════════════════════════
  全部检查通过，可以运行 ~start / ~batch
══════════════════════════════════════
```

如有失败项，输出具体错误并以 exit 1 退出。

## 实现步骤

执行以下步骤（根据参数决定跳过哪些）：

**Step 1：环境变量**
```bash
./scripts/api-caller.sh env-check
```

**Step 2：配置文件 YAML 合法性**
```bash
for f in config/compliance/blocklist.yaml config/compliance/policy-rules.yaml \
          config/compliance/rewrite-patterns.yaml config/scoring/auto-gate-rules.yaml \
          config/platforms/seedance-v2.yaml config/api-endpoints.yaml; do
  [ -f "$f" ] && python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "✓ $f" || echo "✗ $f"
done
```

**Step 3：平台配置字段检查**
```bash
python3 - <<'EOF'
import yaml
data = yaml.safe_load(open("config/platforms/seedance-v2.yaml"))
required = ["generation_backend", "model", "max_retries"]
for field in required:
    if field not in data:
        print(f"✗ 缺少字段: {field}")
    else:
        print(f"✓ {field} = {data[field]}")
EOF
```

**Step 4：状态文件检查**
```bash
import json, os, glob
for f in glob.glob("state/*-phase*.json") + glob.glob("state/*-shot-*.json"):
    try:
        data = json.load(open(f))
        status = data.get("status", "MISSING")
        valid_statuses = {"pending", "in_progress", "completed", "failed"}
        if status not in valid_statuses:
            print(f"✗ {f}: status='{status}' 不合法")
        else:
            print(f"✓ {f}: status={status}")
    except json.JSONDecodeError as e:
        print(f"✗ {f}: JSON 解析失败 ({e})")
```

**Step 5：运行测试套件**
```bash
for f in tests/test-*.sh; do
  [ -f "$f" ] && bash "$f"
done
```
