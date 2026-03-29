# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

AI 短剧自动生成系统。从创意发想到视频输出的全链路自动化，基于 Claude Code Agent Teams 架构。

**完整 E2E 流程**：`~scriptwriter-to-video`（一键）或分步：`~scriptwriter`（创意→剧本） → `~preprocess`（剧本拆解） → `~design`（参考图） → `~batch`/`~start`（视频生成）

## 快速开始

```bash
# 检查环境变量
./scripts/api-caller.sh env-check

# 从创意生成完整剧本（可选，替代手写剧本）
~scriptwriter                           # 交互式创作
~scriptwriter --idea "你的创意" --episodes 15 --length short

# 一键从创意到视频（E2E，推荐）
~scriptwriter-to-video --idea "你的创意" --episodes 15 --length short
~scriptwriter-to-video --resume {project}  # 断点续传

# 长篇剧本预处理（.docx/.md/.txt → 分集剧本 + 角色档案）
~preprocess /path/to/script.docx
~preprocess /path/to/script.docx project-name

# 参考图全量生成（所有角色 + 所有场景，一步到位）
~design

# 单剧本模式：将剧本放入 script/ 后运行
~start

# 批量模式：将多个剧本放入 script/ 后运行
~batch                      # 从头开始
~batch --resume             # 断点续传
~batch --mine               # 只跑分配给我的集数

# 查看进度
~status
~status ep01
~status --mine              # 我的进度

# 可观测性（Agent Trace Log）
~trace                      # 最近 session 的路径概览
~trace ep01                 # 某集的 agent 链路
~trace ep01 shot-03         # 某 shot 的生成追溯
~trace --backtrack ep01 shot-03  # 从失败 shot 反向追溯根因
~trace --summary            # 查看/生成 LLM 摘要

# 人工审核
~review
~review approve
~review reject ep01

# A/B 测试模式
~start --ab

# A/B 评分
~ab-review
~ab-review ep01
~ab-review report ep01

# 多人协作（Producer 分配任务）
~assign ep01-ep20 alice     # 分配 ep01-ep20 给 alice
~assign ep41-ep60           # 自己认领 ep41-ep60
~assign --list              # 查看未分配的集数

# 任务看板
~board                      # 全局看板
~board alice                # 某人的任务
~board --stale              # 卡住的任务
```

## 环境变量

运行前需设置：
```bash
export ARK_API_KEY="..."        # 火山方舟 API Key（视频生成，必需）
export IMAGE_GEN_API_URL="..."  # 图像生成端点（Phase 3 参考图，可选）
export IMAGE_GEN_API_KEY="..."  # 图像生成 Key（Phase 3 参考图，可选）
export OPENAI_API_KEY="..."     # 用于 Moderation API（Phase 1 第三层，可选）
export DEEPSEEK_API_KEY="..."   # 用于 Trace 摘要（可观测性，可选）
export LARK_APP_ID="..."        # 飞书应用 ID（审核通知，可选）
export LARK_APP_SECRET="..."    # 飞书应用 Secret（审核通知，可选）
export REVIEW_SERVER_URL="..."  # Review Server 地址（默认 http://localhost:8080）
```

## Browser Backend（Seedance 2.0 via 即梦 Web UI）

Seedance 2.0 API 未开放时，使用 Actionbook CLI 驱动浏览器操作即梦 Web UI 生成视频。

### 前置条件

- `actionbook` CLI 已安装（`actionbook --version`，需 >= 0.6.0）
- `jq` 已安装

### 首次登录

```bash
./scripts/api-caller.sh jimeng-web setup
# 浏览器弹出，手动登录即梦，登录后 Ctrl+C
```

### 切换后端

修改 `config/platforms/seedance-v2.yaml`：
```yaml
generation_backend: "browser"  # 从 "api" 改为 "browser"
```

### 注意事项

- browser 模式使用 `browser-gen-worker` agent（而非 `gen-worker`）
- 串行执行，每次只能生成一个视频，速度远慢于 API 模式
- 不支持 A/B 测试模式
- CSS 选择器可能因即梦 UI 更新而失效
- Seedance 2.0 API 开放后改回 `generation_backend: "api"` 即可

## Agent Teams 架构

### 剧本创作模式（~scriptwriter）

```
scriptwriter (skill orchestrator)
├── outline-agent              Step 2: 故事大纲（结构、角色、场景、分集规划）
│                              → 🔴人工确认（outline.md）
├── character-creator          Step 3: 角色档案（内联处理）
├── scene-creator              Step 4: 场景档案（内联处理）
├── episode-writer-agent × N   Step 5: 分集剧本（并行，每集一个 agent）
│                              → 🔴每 5 集人工确认
├── script-reviewer-agent      Step 6: 质量检查（连贯性、一致性、时长、对白）
│                              → 🔴人工确认（review-report.md）
└── format-converter           Step 7: 格式转换（内联处理，输出 .docx + .md）
```

### 单剧本模式（~start）

```
team-lead
├── comply-agent           Phase 1: 合规预检
├── visual-agent           Phase 2: 视觉指导
│   └── gate-agent         评分过关（prompt 质量 + 安全预检）
├── design-agent           Phase 3: 美术校验
├── voice-agent            Phase 4: 音色配置（交互式 / --auto-voice 自动匹配）
├── gen-worker × N         Phase 5: 视频生成（并行，backend=api）
└── browser-gen-worker × 1 Phase 5: 视频生成（串行，backend=browser）
```

### 批量模式（~batch）

**全并行架构：角色预扫描 + 融合去重 + 自动过关 + 音色自动匹配，消除所有串行瓶颈。**

| 阶段 | 执行方式 | 原因 |
|------|---------|------|
| Phase 1+2 | 并行 | 独立剧本，无共享资源 |
| Phase 3 美术校验 | **并行** | 纯校验：检查参考图是否存在，不生图（所有图由 `~design` 预先生成） |
| Phase 4 音色 | **并行** | 自动匹配模式无交互，无冲突 |
| Phase 5 视频 | 并行 | 每个镜次独立状态文件 |

### 角色/场景一致性机制

**核心目标**：生成参考图后，所有涉及该角色/场景的镜次都引用同一张图。

| 问题 | 解决方案 | 关键字段 |
|------|---------|---------|
| 角色多形态（人形/鬼形/兽形） | 角色档案 `forms` 字段，每个形态独立外貌+参考图 | `form_id` |
| 场景时间维度（白天/晚上） | 镜次级 `time_of_day`，场景图按时间变体生成 | `time_of_day` |
| 跨集角色名融合 | merge-agent 扫描后自动识别别名/昵称/笔误 | `aliases` |
| 主角形象迭代 | `~design` 中主角迭代审核，锁定后全集复用 | `design-lock.json` |
| 分级审核 | `~design` 一步完成：protagonist 迭代 / supporting 标准审核 / minor 自动过 | `tier` |

## 流水线阶段

| 阶段 | Agent | 输入 | 输出 |
|------|-------|------|------|
| Phase 1 合规预检 | comply-agent | script/{ep}.md | render-script.md, compliance-report.md |
| Phase 2 视觉指导 | visual-agent | render-script.md | visual-direction.yaml（含 form_id + time_of_day） |
| Phase 3 美术校验 | design-agent | visual-direction.yaml + design-lock.json | art-direction-review.md（纯校验，不生图） |
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
├── design-lock.json        # 参考图锁定（~design 产出）
├── task-board.json         # 任务看板（多人协作模式）
├── character-merge-map.json # 跨集角色融合映射（preprocess 产出）
├── {ep}-phase1.json        # 合规预检状态
├── {ep}-phase2.json        # 视觉指导状态
├── {ep}-phase3.json        # 美术指导状态
├── {ep}-phase4.json        # 音色配置状态
└── {ep}-shot-{N}.json      # 各镜次状态
```

## 断点续传

`~batch` 和 `~start` 自动检测已有状态文件，跳过已完成的阶段：

```
检查断点状态...

[resume] ep01 Phase 1-4 已完成，Phase 5: 8/12 镜次完成
[resume] ep02 全部完成，跳过
[start] ep03 从 Phase 1 开始

摘要：
- 1 个剧本已全部完成，跳过
- 1 个剧本从 Phase 5 继续
- 1 个剧本从 Phase 1 开始
```

跳过规则：
- Phase X `status: completed` → 跳过该阶段
- 镜次 `status: completed` 且视频文件存在 → 跳过该镜次

## 多人协作

### 角色

| 角色 | 权限 |
|------|------|
| Producer | 分配任务、清除分配、查看全局进度 |
| Operator | 认领任务、运行 ~batch --mine、清除自己负责的任务 |
| Reviewer | 只读权限，查看任务状态 |

### 工作流

```
Producer                    Operator A              Operator B
   │                           │                        │
   ├─ ~assign ep01-ep20 alice  │                        │
   ├─ ~assign ep21-ep40 bob    │                        │
   │                           │                        │
   │                      ~batch --mine            ~batch --mine
   │                           │                        │
   │                      [处理 ep01-ep20]         [处理 ep21-ep40]
   │                           │                        │
   ├─ ~board ←─────────────────┴────────────────────────┘
   │  (查看全局进度)
```

### 冲突检测

`~batch --mine` 启动前检查任务锁定状态，避免多人同时操作同一集数：

```
⚠️ 冲突检测：
- ep05 已被 alice 锁定（task-001，进行中）

是否继续处理未锁定的剧本？(yes/no)
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

## A/B 提示词测试

### 工作流程

1. `~start --ab` — 选择两个提示词变体，每个镜次生成 2 个视频
2. `~ab-review` — 人工逐镜次评分（5 维度 × 1-5 分）
3. 查看 `outputs/{ep}/ab-report.md` — 胜率、各维度对比、建议

### 新增变体

在 `config/ab-testing/variants/` 下创建 YAML 文件：
- `transform_type: passthrough` — 直接使用原始提示词
- `transform_type: llm_rewrite` — LLM 按 `rewrite_instruction` 改写

### 评分维度

画面质量(0.25) + 场景匹配(0.20) + 角色一致(0.20) + 动作自然(0.20) + 唇形同步(0.15)

无对白镜次自动重分配权重（lip_sync 权重分配给其他维度）。

### 注意事项

- A/B 模式 API 调用量翻倍（每镜次 2 个变体）
- 新增变体只需添加 YAML 文件，无需改代码
- 失败变体自动跳过评分，记录到报告

## 飞书审核集成 + Review Server

所有确认点通过飞书异步通知，用户不用盯终端。视觉内容（角色图/场景图/视频）通过 Web 页面审核。

### 架构

```
Claude Code → 写 state/reviews/{id}.json → 发飞书卡片 → session 结束
                                              ↓
                              用户点卡片按钮（文字类）或 Web 链接（视觉类）
                                              ↓
                              Review Server 收到 webhook/表单提交
                                              ↓
                              写 review response → Remote Trigger 唤醒新 session
```

### 审核方式

| 内容类型 | 飞书卡片 | 审核方式 |
|---------|---------|---------|
| 文字（大纲/质量报告） | 摘要 + 3 按钮 | 卡片按钮直接审 |
| 视觉（角色图/场景图） | 缩略图 + Web 链接 | Web 页面审核 |
| 视频（生成的视频） | 摘要 + Web 链接 | Web 页面审核 |

### 审核结果

- **通过** → 流程继续
- **重做**（附原因）→ 重跑当前确认点，reason 传给 agent 作为修改指令
- **终止** → 流程结束

### 启动 Review Server

```bash
cd review-server
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

### 配置

- `config/lark/lark-config.yaml` — 飞书 app、审核群、Review Server URL
- `config/lark/card-templates/` — 卡片模板（text-review、visual-review、alert）
- `state/reviews/` — 审核状态文件

详细设计见 `docs/plans/2026-03-29-lark-review-integration-design.md`。

## Auto-Gate 自动评分过关

所有确认点在推飞书之前，先由 `gate-agent` 自动评分：

```
产出完成 → gate-agent 评分 → ≥85 分自动过（不推飞书）
                            → 50-85 分推飞书人审（附评分报告）
                            → <50 分自动退回重做（附退回原因）
```

### 评分类型

| 类型 | 适用确认点 | 维度 |
|------|-----------|------|
| text_scoring.outline | 大纲确认 | 结构完整性、角色设计、冲突看点、节奏、伏笔、受众匹配 |
| text_scoring.episode_quality | 质量报告 | 剧情连贯、角色一致、时长控制、对白自然、悬念钩子 |
| prompt_scoring.visual_direction | 视觉指导 | 5-block 结构、单动词、长度、Quality Suffix、风格具体性、安全合规 |
| visual_scoring.character_design | 主角形象 | 身份一致性、风格统一、参考图质量、裁切格式 |

### Prompt 安全预检

`gate-agent` 在评分 visual_direction 时额外执行 prompt 安全预检：
- 对照 `config/compliance/blocklist.yaml` 检查 prompt 中的敏感词
- 检查 Seedance 2.0 已知拒绝模式（多动词、超长、负面描述）
- 检查 5-block 结构完整性（Subject/Action/Camera/Style/Quality Suffix）

不通过的 prompt 在 Phase 2 就拦住，不等 Phase 5 API 被拒才发现。

### 配置

评分规则：`config/scoring/auto-gate-rules.yaml`
- 可调整阈值（默认 ≥85 自动过，<50 自动退回）
- 可调整每个维度的权重
- 连续自动过关保护：超过 10 次连续自动过后强制人审一次

## 可观测性（Agent Trace Log）

每次 `~start` / `~batch` 运行自动记录所有 agent 的过程日志（JSONL 格式），支持路径追踪、回溯诊断、LLM 自动摘要。

### Trace 文件结构

```
state/traces/{session-id}/
├── session.jsonl                # Session 级事件（spawn/complete/error）
├── {ep}-phase{N}-trace.jsonl    # Agent 步骤日志
├── {ep}-shot-{N}-trace.jsonl    # Shot 生成日志
└── summary.md                   # LLM 摘要报告
```

### 写入方式

Agent 通过 `scripts/trace.sh` 写入结构化事件：
```bash
./scripts/trace.sh <session-id> <trace-file> <step> [json-detail]
```

### 查询方式

```bash
~trace                              # 路径概览（哪个 agent 做了什么）
~trace --backtrack ep01 shot-03     # 从失败 shot 反向追溯到根因
~trace --summary                    # LLM 自动摘要（需要 DEEPSEEK_API_KEY）
```

### LLM 摘要配置

设置 `DEEPSEEK_API_KEY` 后，session 结束自动生成摘要。也可手动触发：
```bash
./scripts/api-caller.sh trace-summary state/traces/{session-id}
```

详细格式规范见 `config/trace-protocol.md`。

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
raw/             # 放入原始剧本文件（.docx/.md/.txt，~preprocess 处理后输出到 script/）
outputs/{ep}/    # 各剧本产出（报告 + 视频）
  ├── render-script.md
  ├── compliance-report.md
  ├── visual-direction.yaml
  ├── art-direction-review.md
  ├── voice-assignment.md
  ├── generation-report.md
  └── videos/
outputs/scriptwriter/{project}/  # 剧本创作产出（~scriptwriter）
  ├── outline.md
  ├── characters/*.yaml
  ├── scenes/*.yaml
  ├── episodes/ep*.md
  ├── review-report.md
  └── complete.md
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
.claude/agents/  # Agent 定义（outline/episode-writer/script-reviewer/preprocess/comply/visual/design/voice/gen-worker）
.claude/skills/  # Skill 定义（~scriptwriter-to-video, ~scriptwriter, ~preprocess, ~start, ~batch, ~status, ~trace, ~review）
scripts/         # api-caller.sh（统一 API 调用）
```