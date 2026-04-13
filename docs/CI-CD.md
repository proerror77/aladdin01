# CI/CD 规范

## 流水线概览

```text
PR 提交 → lint-validate → security-scan → dry-run-check → ✅ 可合并
main 合并 → 同上 + compliance-config-test → 通知
```

## GitHub Actions 触发条件

| 事件 | 触发 Job |
|------|---------|
| PR → main | lint, validate-yaml, shellcheck, secret-scan |
| push → main | 同上 + compliance-config-test |
| 手动触发 | env-check（需配置 Secrets） |

## 本地预检（推送前必跑）

```bash
# Shell 脚本语法检查
shellcheck scripts/api-caller.sh

# YAML 格式校验
python3 -m yamllint config/

# 合规配置完整性检查
./scripts/api-caller.sh env-check

# 敏感词表格式验证
python3 -c "import yaml; yaml.safe_load(open('config/compliance/blocklist.yaml'))"
```

## Secrets 管理

**本地开发**：通过 `.env`（已加入 `.gitignore`）或 shell profile 设置。

**CI 环境**：在 GitHub → Settings → Secrets and variables → Actions 中配置：

| Secret 名称 | 对应环境变量 | 用途 |
|------------|------------|------|
| `ARK_API_KEY` | `ARK_API_KEY` | Seedance 视频生成 |
| `IMAGE_GEN_API_URL` | `IMAGE_GEN_API_URL` | 图像生成端点 |
| `IMAGE_GEN_API_KEY` | `IMAGE_GEN_API_KEY` | 图像生成鉴权 |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | Moderation API |
| `AIGC_DETECT_API_KEY` | `AIGC_DETECT_API_KEY` | AIGC 检测 API（可选） |

**规则**：
- 禁止将任何 API Key 硬编码进脚本或配置文件
- `config/api-endpoints.yaml` 只存 URL 模板，不存 Key
- PR diff 中出现疑似 Key 格式（`sk-`、`Bearer` 后跟长字符串）时 CI 自动阻断

## 分支策略（GitHub Flow）

```text
main           # 唯一长期分支，始终可部署
feature/*      # 新功能（agent、phase、config 改动）
fix/*          # 修复
```

**规则**：
- `main` 禁止直接 push，**唯一例外：仓库初始化的第一个 commit**
- 分支从最新 `main` 切出，合并后立即删除
- PR 需 CI 全绿才可合并，使用 squash merge 保持 main 历史整洁

**分支命名**：
```text
feature/add-comply-agent
feature/voice-config-yaml
fix/gen-worker-retry-logic
```

## 完整开发流程

**1. 开始新工作（使用 Worktree 隔离）**
```bash
git checkout main && git pull origin main

# 创建 worktree，每个 feature 独立目录，互不干扰
git worktree add .worktrees/your-feature -b feature/your-feature
cd .worktrees/your-feature
```

**2. 开发 + atomic commits**
```bash
git add <specific-files>
git commit -m "feat(scope): 描述"
```

**3. 推送并开 PR**
```bash
git push origin feature/your-feature
gh pr create --title "feat(scope): 描述" --body "## 改动内容\n\n## 测试方式"
```

**4. PR checklist（合并前确认）**
- [ ] CI 全绿（lint、shellcheck、secret-scan）
- [ ] commit message 符合规范，无 WIP/update
- [ ] 不含 `.mp4`、API Key、`state/*.json`
- [ ] CLAUDE.md 如有架构变更已同步更新

**5. 合并 + 清理**
```bash
# GitHub 上 squash merge 后，回到主目录
cd /path/to/aladdin01
git checkout main && git pull origin main

# 删除 worktree（同时删除本地分支）
git worktree remove .worktrees/your-feature
git branch -d feature/your-feature

# 批量清理所有已合并的本地分支 + 远端追踪引用
git branch --merged main | grep -v '^\* main' | xargs git branch -d
git fetch --prune
```

**Worktree 常用命令**
```bash
git worktree list              # 查看所有 worktree
git worktree remove <path>     # 删除 worktree（需先 cd 出去）
git worktree prune             # 清理失效的 worktree 引用
```

## Atomic Commits

每个 commit 只做一件事，能独立 revert。

**粒度参考**：

| 场景 | 正确拆分 |
|------|---------|
| 新增 agent + 更新 CLAUDE.md | 2 个 commit |
| 修复 retry 逻辑 + 顺手改注释 | 2 个 commit |
| 新增 phase + 对应 state schema | 2 个 commit |
| 同一 agent 的多处 bug fix | 1 个 commit（同一关注点） |

**commit message 格式**：`type(scope): 描述`

| type | 用途 |
|------|------|
| `feat` | 新 agent、新 phase、新功能 |
| `fix` | bug 修复 |
| `config` | 配置文件改动（compliance、platform、voice） |
| `docs` | CLAUDE.md、注释 |
| `refactor` | 重构，不改行为 |
| `ci` | GitHub Actions、脚本 |

**禁止**：`fix stuff`、`WIP`、`update`、一个 commit 跨多个不相关 scope。

## CI 不覆盖的内容

以下需人工验证，CI 不自动执行：
- 实际视频生成（涉及付费 API）
- Phase 3/4 人工确认流程
- 跨集角色资产一致性
