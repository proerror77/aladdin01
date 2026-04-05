# 贡献指南

## 分支策略（GitHub Flow）

```
main           # 唯一长期分支，始终可部署
feature/*      # 新功能
fix/*          # 修复
```

- `main` 禁止直接 push（初始化 commit 除外）
- 分支从最新 `main` 切出，合并后立即删除
- PR 需 CI 全绿，使用 squash merge

### 分支命名

```
feature/add-comply-agent
feature/voice-config-yaml
fix/gen-worker-retry-logic
```

## 开发流程

### 1. 创建 Worktree

```bash
git checkout main && git pull origin main
git worktree add .worktrees/your-feature -b feature/your-feature
cd .worktrees/your-feature
```

### 2. 开发 + Atomic Commits

每个 commit 只做一件事，能独立 revert。

```bash
git add <specific-files>
git commit -m "feat(scope): 描述"
```

**粒度参考：**

| 场景 | 拆分 |
|------|------|
| 新增 agent + 更新 CLAUDE.md | 2 个 commit |
| 修复 retry 逻辑 + 顺手改注释 | 2 个 commit |
| 同一 agent 的多处 bug fix | 1 个 commit |

### 3. 推送并开 PR

```bash
git push origin feature/your-feature
gh pr create --title "feat(scope): 描述" --body "## 改动内容\n\n## 测试方式"
```

### 4. PR Checklist

- [ ] CI 全绿（lint、shellcheck、secret-scan）
- [ ] commit message 符合规范，无 WIP/update
- [ ] 不含 `.mp4`、API Key、`state/*.json`
- [ ] CLAUDE.md 如有架构变更已同步更新

### 5. 合并 + 清理

```bash
cd /path/to/aladdin01
git checkout main && git pull origin main
git worktree remove .worktrees/your-feature
git branch -d feature/your-feature
git fetch --prune
```

## Commit Message 规范

格式：`type(scope): 描述`

| type | 用途 |
|------|------|
| `feat` | 新 agent、新 phase、新功能 |
| `fix` | bug 修复 |
| `config` | 配置文件改动 |
| `docs` | 文档更新 |
| `refactor` | 重构，不改行为 |
| `ci` | GitHub Actions、CI 脚本 |
| `test` | 测试相关 |

**禁止**：`fix stuff`、`WIP`、`update`、一个 commit 跨多个不相关 scope。

## 本地预检

推送前建议运行：

```bash
# Shell 语法检查
shellcheck scripts/api-caller.sh

# YAML 格式校验
python3 -m yamllint config/

# 合规配置完整性
./scripts/api-caller.sh env-check

# 测试
bash tests/test-api-caller.sh
bash tests/test-compliance.sh
```

## CI/CD

PR 提交后自动运行：

| 检查项 | 说明 |
|--------|------|
| lint | 代码格式 |
| validate-yaml | YAML 配置校验 |
| shellcheck | Shell 脚本静态分析 |
| secret-scan | API Key 泄露检测 |

### Secrets 管理

- API Key 禁止硬编码，通过环境变量或 `.env`（已在 `.gitignore`）
- `config/api-endpoints.yaml` 只存 URL 模板
- PR diff 中出现 `sk-`、`Bearer ` 后跟长字符串会被 CI 阻断

## 架构变更须知

修改以下内容时，**必须同步更新 CLAUDE.md**：

- 新增/删除/修改 Agent
- 新增/修改 Phase
- 状态文件结构变更
- 配置文件 schema 变更
- 新增 Skill
