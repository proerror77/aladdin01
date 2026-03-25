# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

AI 短剧自动生成系统。从剧本输入到视频输出的全链路自动化，基于 Claude Code Agent Teams 架构。

## 快速开始

```bash
# 检查环境变量
./scripts/api-caller.sh env-check

# 单剧本模式：将剧本放入 script/ 后运行
~start

# 批量模式：将多个剧本放入 script/ 后运行
~batch

# 查看进度
~status
~status ep01

# 人工审核
~review
~review approve
~review reject ep01
```

## 环境变量

运行前需设置：
```bash
export ARK_API_KEY="..."        # 火山方舟 API Key（视频生成，必需）
export IMAGE_GEN_API_URL="..."  # 图像生成端点（Phase 3 参考图，可选）
export IMAGE_GEN_API_KEY="..."  # 图像生成 Key（Phase 3 参考图，可选）
export OPENAI_API_KEY="..."     # 用于 Moderation API（Phase 1 第三层，可选）
```

## Agent Teams 架构

### 单剧本模式（~start）

```
team-lead
├── comply-agent    Phase 1: 合规预检
├── visual-agent    Phase 2: 视觉指导 → 🔴人工确认
├── design-agent    Phase 3: 美术指导 → 🔴人工确认
├── voice-agent     Phase 4: 音色配置（交互式）
└── gen-worker × N  Phase 5: 视频生成（并行）
```

### 批量模式（~batch）

**重要：Phase 3 和 Phase 4 采用串行执行，避免竞态条件和交互冲突。**

| 阶段 | 执行方式 | 原因 |
|------|---------|------|
| Phase 1+2 | 并行 | 独立剧本，无共享资源 |
| Phase 3 美术 | **串行** | 跨集角色资产复用，避免竞态 |
| Phase 4 音色 | **串行** | 交互式询问用户，避免冲突 |
| Phase 5 视频 | 并行 | 每个镜次独立状态文件 |

## 流水线阶段

| 阶段 | Agent | 输入 | 输出 |
|------|-------|------|------|
| Phase 1 合规预检 | comply-agent | script/{ep}.md | render-script.md, compliance-report.md |
| Phase 2 视觉指导 | visual-agent | render-script.md | visual-direction.yaml（结构化镜次数据） |
| Phase 3 美术指导 | design-agent | render-script + visual-direction.yaml | 角色/场景参考图, art-direction-review.md |
| Phase 4 音色配置 | voice-agent | render-script + visual-direction.yaml | voice-config.yaml × N, voice-assignment.md |
| Phase 5 视频生成 | gen-worker × N | prompt, duration, reference_image, voice_config | shot-{N}.mp4 |

## Seedance 2.0 提示词格式

**text_to_video 模式**：
```
[主体] + [动作] + [场景] + [镜头] + [风格] + [音频]
```

**image_to_video 模式**：
```
主体+动作, 背景+动作, 镜头+运动
```

- 最大长度：2000 字符
- 时长范围：4-15 秒
- 对白格式：`角色名: "台词内容"`（唇形同步）
- 参考图引用：`@{角色名}`，`@scene_{场景名}`

## 状态文件结构

**避免并发写入冲突**，每个 agent 写入独立状态文件：

```
state/
├── progress.json           # 索引文件（汇总）
├── progress-schema.yaml    # Schema 定义
├── {ep}-phase1.json        # 合规预检状态
├── {ep}-phase2.json        # 视觉指导状态
├── {ep}-phase3.json        # 美术指导状态
├── {ep}-phase4.json        # 音色配置状态
└── {ep}-shot-{N}.json      # 各镜次状态
```

## 合规层设计

三层检测，全部通过才输出 render_script：
1. 敏感词表（`config/compliance/blocklist.yaml`）— 精确匹配
2. LLM 语义判断（`config/compliance/policy-rules.yaml`）— 维度评分
3. OpenAI Moderation API — 类别阈值（通过文件输入，避免 shell 注入）

改写策略：暴力→反应镜头，性→情绪氛围，辱骂→中性冲突，违法细节→删除。

## 视频生成重试机制

每个 gen-worker 独立运行：
1. 原始提示词最多重试 5 次
2. 5 次失败 → LLM 最小改写提示词
3. 每轮改写后重试 3 次
4. 最多 3 轮改写（总计最多 14 次 API 调用）
5. 全部失败 → 标记 failed，记录到 generation-report.md

## 关键架构决策

- **render_script 优先**：所有阶段使用合规后的 render_script，原始剧本仅存档
- **资产全局共享**：`assets/` 目录跨集共享，design-agent 和 voice-agent 自动复用已有角色
- **TTS 预留**：音色配置已写入 `voice-config.yaml`，`tts_platform: "pending"`，TTS 平台接入后更新
- **多平台扩展**：`config/platforms/` 下每个平台一个 yaml，新增平台只需添加配置文件
- **独立状态文件**：避免批量模式下的并发写入冲突

## CI/CD 规范

### 流水线概览

```
PR 提交 → lint-validate → security-scan → dry-run-check → ✅ 可合并
main 合并 → 同上 + compliance-config-test → 通知
```

### GitHub Actions 触发条件

| 事件 | 触发 Job |
|------|---------|
| PR → main | lint, validate-yaml, shellcheck, secret-scan |
| push → main | 同上 + compliance-config-test |
| 手动触发 | env-check（需配置 Secrets） |

### 本地预检（推送前必跑）

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

### Secrets 管理

**本地开发**：通过 `.env`（已加入 `.gitignore`）或 shell profile 设置。

**CI 环境**：在 GitHub → Settings → Secrets and variables → Actions 中配置：

| Secret 名称 | 对应环境变量 | 用途 |
|------------|------------|------|
| `ARK_API_KEY` | `ARK_API_KEY` | Seedance 视频生成 |
| `IMAGE_GEN_API_URL` | `IMAGE_GEN_API_URL` | 图像生成端点 |
| `IMAGE_GEN_API_KEY` | `IMAGE_GEN_API_KEY` | 图像生成鉴权 |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | Moderation API |

**规则**：
- 禁止将任何 API Key 硬编码进脚本或配置文件
- `config/api-endpoints.yaml` 只存 URL 模板，不存 Key
- PR diff 中出现疑似 Key 格式（`sk-`、`Bearer ` 后跟长字符串）时 CI 自动阻断

### 分支策略（GitHub Flow）

```
main           # 唯一长期分支，始终可部署
feature/*      # 新功能（agent、phase、config 改动）
fix/*          # 修复
```

**规则**：
- `main` 禁止直接 push，**唯一例外：仓库初始化的第一个 commit**
- 分支从最新 `main` 切出，合并后立即删除
- PR 需 CI 全绿才可合并，使用 squash merge 保持 main 历史整洁

**分支命名**：
```
feature/add-comply-agent
feature/voice-config-yaml
fix/gen-worker-retry-logic
```

### 完整开发流程

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

### Atomic Commits

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

### CI 不覆盖的内容

以下需人工验证，CI 不自动执行：
- 实际视频生成（涉及付费 API）
- Phase 3/4 人工确认流程
- 跨集角色资产一致性

## 目录结构

```
script/          # 放入剧本（.md 格式）
outputs/{ep}/    # 各剧本产出（报告 + 视频）
  ├── render-script.md
  ├── compliance-report.md
  ├── visual-direction.yaml
  ├── art-direction-review.md
  ├── voice-assignment.md
  ├── generation-report.md
  └── videos/
assets/          # 全局资产（角色图/场景图/音色）
  ├── characters/images/
  ├── characters/voices/
  └── scenes/images/
config/          # 平台/合规/音色/API 配置
  ├── platforms/seedance-v2.yaml
  ├── compliance/
  ├── voices/
  └── api-endpoints.yaml
state/           # 进度状态（独立状态文件）
.claude/agents/  # Agent 定义（comply/visual/design/voice/gen-worker）
.claude/skills/  # Skill 定义（~start, ~batch, ~status, ~review）
scripts/         # api-caller.sh（统一 API 调用）
```