# 测试指南

## 测试套件

| 文件 | 类型 | 说明 |
|------|------|------|
| `test-api-caller.sh` | Shell 单元测试 | api-caller.sh 参数校验、路径安全 |
| `test-agent-workflow-contracts.sh` | Shell 契约测试 | memory-agent 两段检索、在线 state 同步、Phase 2.2 接线 |
| `test-compliance.sh` | 配置验证 | 合规配置 YAML 格式和结构 |
| `test-review-server.sh` | Shell 集成测试 | pending trigger 重试与状态持久化 |
| `test-vectordb-manager.sh` | Shell 集成测试 | relation 检索、skill 实体检索、state 幂等写入 |
| `test-workflow-sync.sh` | Shell 集成测试 | fallback storyboard、shot packet、phase 状态同步 |
| `api-caller.bats` | BATS 测试 | api-caller.sh 功能测试 |
| `concat-episode.bats` | BATS 测试 | 视频拼接功能测试 |

## 运行测试

### 全部运行

```bash
# Shell 测试（无需外部 API）
bash tests/test-api-caller.sh
bash tests/test-agent-workflow-contracts.sh
bash tests/test-compliance.sh
bash tests/test-review-server.sh
bash tests/test-vectordb-manager.sh
bash tests/test-workflow-sync.sh

# BATS 测试（需安装 bats）
bats tests/api-caller.bats
bats tests/concat-episode.bats
```

### 单独运行

```bash
bash tests/test-api-caller.sh    # api-caller 参数校验
bash tests/test-agent-workflow-contracts.sh  # Agent/Skill 编排契约
bash tests/test-compliance.sh    # 合规配置验证
bash tests/test-review-server.sh # review-server 重试与状态
bash tests/test-vectordb-manager.sh          # VectorDB 行为
```

## 测试说明

### test-api-caller.sh

纯本地逻辑验证，不调用任何外部 API。覆盖：

- 参数校验（无参数、缺 action、无效 service）
- task\_id 格式校验（防路径遍历）
- 输出文件路径安全校验
- 环境变量检查逻辑

### test-compliance.sh

验证合规配置文件的完整性和正确性：

- YAML 格式合法性（blocklist、rewrite-patterns、policy-rules、auto-gate-rules）
- blocklist.yaml 结构校验（必须有 categories、每个 category 有 keywords）
- rewrite-patterns.yaml 结构校验
- auto-gate-rules.yaml 阈值逻辑校验

**前置条件**：`python3` + `pyyaml`

### BATS 测试

使用 [BATS](https://github.com/bats-core/bats-core) 测试框架。

安装：
```bash
brew install bats-core
```

## CI 集成

PR 提交后，GitHub Actions 自动运行：

- `shellcheck` — Shell 脚本静态分析
- `validate-yaml` — YAML 配置格式校验
- `secret-scan` — API Key 泄露检测

详见 `.github/workflows/`。

## 不在 CI 中的测试

以下需人工验证（涉及付费 API 或人工操作）：

- 实际视频生成（Seedance API 调用）
- 图像生成（Nanobanana / Tuzi API 调用）
- Phase 3/4 人工确认流程
- 飞书通知发送
- 跨集角色资产一致性

## 编写新测试

### Shell 测试模板

```bash
#!/usr/bin/env bash
# tests/test-xxx.sh — 描述

RESULTS_FILE=$(mktemp)
trap 'rm -f "$RESULTS_FILE"' EXIT

pass() { echo "  PASS: $1"; echo "P" >> "$RESULTS_FILE"; }
fail() { echo "  FAIL: $1"; echo "F" >> "$RESULTS_FILE"; }

echo "=== 测试名称 ==="
# ... 测试逻辑 ...

# 汇总
TOTAL=$(wc -c < "$RESULTS_FILE" | tr -d ' ')
PASSED=$(grep -c P "$RESULTS_FILE" || true)
FAILED=$(grep -c F "$RESULTS_FILE" || true)
echo ""
echo "总计: $TOTAL  通过: $PASSED  失败: $FAILED"
[[ "$FAILED" -eq 0 ]]
```
