# Aladdin — AI 短剧自动生成系统

从创意发想到视频输出的全链路自动化，基于 Claude Code Agent Teams 架构。

## 这是什么

Aladdin 是一套运行在 **Claude Code** 里的 AI Agent 系统。你在 Claude Code 的对话框里输入 `~command`，背后会自动调度多个 AI Agent 协作完成剧本创作、参考图生成、视频生成等任务。

**你不需要写代码**，只需要：
1. 安装好依赖、配置好 API Key
2. 打开 Claude Code，进入这个项目目录
3. 输入 `~` 开头的命令

## 功能概览

- **剧本创作**：从一句话创意生成完整分集剧本（大纲 → 角色/场景 → 分集 → 质检）
- **视觉生成**：合规预检 → 视觉指导 → 参考图 → 视频生成，全流程自动化
- **广告片工作流**：先设定广告总时长，编译 `钩子 → 产品 → 功能 → 信任 → CTA`，再生成广告 storyboard 和 Seedance 分段 payload
- **多模式支持**：text\_to\_video（v1.0 快速原型）和 img2video（v2.0 高质量长剧），视频/音频多模态参考（Seedance 2.0）
- **批量处理**：多集并行生成，断点续传，多人协作任务分配
- **质量保证**：自动评分过关（Auto-Gate）、飞书异步审核、A/B 提示词测试
- **可观测性**：Agent Trace Log，支持路径追踪、回溯诊断、LLM 自动摘要

## 选哪个版本

| | v1.0 (text\_to\_video) | v2.0 (img2video) |
|---|---|---|
| 适合场景 | 短剧（<10 集）、快速验证创意 | 长剧（>20 集）、需要严格角色一致性 |
| 生成速度 | 快 | 慢（多了资产生成和 QA 环节） |
| 角色一致性 | 依赖 prompt 描述 | 参考图 + 状态快照 + 本体约束 |
| 推荐新手 | ✅ 从这里开始 | 熟悉 v1.0 后再用 |

**新手建议**：先用 v1.0 跑通一个完整流程，再考虑 v2.0。

## 快速开始

### 1. 安装依赖

```bash
# macOS
brew install jq ffmpeg yq

# Claude Code（如果还没装）
npm install -g @anthropic-ai/claude-code
```

详细依赖说明见 [docs/SETUP-GUIDE.md](docs/SETUP-GUIDE.md)。

### 2. 配置 API Key

这个系统需要以下服务的 API Key：

| Key | 用途 | 获取地址 |
|-----|------|---------|
| `ARK_API_KEY` | 视频生成（必需） | [火山方舟](https://www.volcengine.com/product/ark) |
| `TUZI_API_KEY` | 图像生成 + LLM（推荐） | [兔子 API](https://api.tu-zi.com) |

> **Seedance 2.0 说明**：模型已于 2026-04-02 正式开放 API，需账户余额 ≥ 200 元才能开通。默认模型已切换至 `doubao-seedance-2-0-260128`，支持图片/视频/音频多模态输入、时长 4-15 秒、最高 2K 分辨率。

```bash
export ARK_API_KEY="your-key-here"
export TUZI_API_KEY="your-key-here"

# 验证配置
./scripts/api-caller.sh env-check
```

> **注意**：视频和图像生成会消耗 API 额度/credit，建议先小批量测试。

### 3. 登录 Dreamina（视频生成后端）

```bash
# 安装 Dreamina CLI
curl -fsSL https://jimeng.jianying.com/cli | bash

# 登录（会打开浏览器授权）
dreamina login

# 验证登录 + 查看余额
dreamina user_credit
```

### 4. 打开 Claude Code，进入项目目录

```bash
cd /path/to/aladdin01
claude  # 启动 Claude Code
```

### 5. 生成你的第一个视频

**方式 A：从创意一键生成（最简单）**

```bash
~scriptwriter-to-video --idea "一个现代都市复仇故事" --episodes 5 --length short
```

系统会依次完成：剧本创作 → 参考图生成 → 视频生成。过程中会在关键节点暂停等待你确认（大纲、质量报告等）。

**方式 B：已有剧本，直接生成视频**

把剧本文件（.docx/.md/.txt）放入 `raw/` 目录，然后：

```bash
~preprocess raw/your-script.docx   # 拆解为分集剧本
~design                             # 生成参考图
~batch                              # 批量生成视频
```

**剧本格式参考**：见 `script/ep01.md`（已有示例）。

**查看进度：**

```bash
~status          # 全局进度
~status ep01     # 单集进度
~trace           # Agent 链路追踪
```

**可视化控制台：**

```bash
python3 studio-ui/server.py --port 4173
```

打开 `http://127.0.0.1:4173/` 可以查看本地项目、角色/场景资产、脚本、分镜图和交付物摘要。控制台也提供受控动作入口：环境检查、workflow-sync、继续生成请求和 trace 摘要都通过白名单 job 执行，需要确认的动作会先弹出确认面板。

**产出文件位置**：`outputs/{ep}/videos/`

## 架构

### v1.0 流程（text\_to\_video）

```
剧本 → 合规预检 → 视觉指导 → 美术校验 → 音色配置 → 视频生成
```

### v2.0 流程（img2video）

```
剧本 → 本体论构建 → 合规预检 → 视觉指导 → 叙事审查（Phase 2.2）
     → 分镜图（Phase 2.3）→ 资产工厂 → 美术校验
     → 两段记忆检索（entities/states → assets）+ Shot Packet（Phase 3.5）
     → 音色配置 → 视频生成 → QA 审计 → 自动修复
```

详细架构文档：
- [架构总览（v2.0）](docs/ARCHITECTURE-V2-COMPLETE.md)
- [E2E 工作流（含本体论）](docs/E2E-WORKFLOW-WITH-ONTOLOGY.md)
- [v2.0 实施指南](docs/V2-IMPLEMENTATION-GUIDE.md)
- [图像生成最佳实践](docs/IMAGE-GENERATION-BEST-PRACTICES.md)

## 常用命令速查

| 命令 | 用途 |
|------|------|
| `~scriptwriter-to-video` | 从创意一键生成视频（E2E） |
| `~ad-video` | 广告片工作流：结构、storyboard、Seedance payload |
| `~scriptwriter` | 只做剧本创作 |
| `~preprocess <file>` | 预处理已有剧本文件 |
| `~design` | 生成所有参考图 |
| `~start` | 单集视频生成 |
| `~batch` | 批量视频生成 |
| `~batch --resume` | 断点续传 |
| `~status` | 查看进度 |
| `~review` | 人工审核 |
| `~trace` | Agent 链路追踪 |

## Agent 一览

| Agent | 职责 |
|-------|------|
| `outline-agent` | 故事大纲生成 |
| `episode-writer-agent` | 分集剧本撰写（并行） |
| `script-reviewer-agent` | 剧本质量检查 |
| `preprocess-agent` | 长篇剧本拆解 + 角色融合 |
| `comply-agent` | 三层合规预检 |
| `visual-agent` | 视觉指导生成 |
| `narrative-review-agent` | 叙事审查与修复（Phase 2.2） |
| `storyboard-agent` | 构图分镜图生成（Phase 2.3） |
| `gate-agent` | 自动评分过关 |
| `design-agent` | 美术校验（文件存在性检查） |
| `voice-agent` | 角色音色配置 |
| `gen-worker` | 视频生成（API 模式） |
| `browser-gen-worker` | 视频生成（浏览器模式） |
| `ontology-builder-agent` | 世界本体模型构建（v2.0） |
| `asset-factory-agent` | 资产包生成（v2.0） |
| `memory-agent` | 两段记忆检索（entities/states → assets，v2.0） |
| `shot-compiler-agent` | Shot Packet 编译（v2.0） |
| `qa-agent` | 质量审计 + 在线状态同步（v2.0） |
| `repair-agent` | 自动修复 + 在线状态同步（v2.0） |

## 目录结构

```
projects/        # 项目工作区
  └─ {project}/
     ├─ script/   # 分集剧本
     ├─ assets/   # 项目资产（角色图/场景图/音色/资产包）
     ├─ outputs/  # 产出（报告 + 视频 + storyboard）
     └─ state/    # 运行时状态（phase/shot/ontology/shot-packets）
raw/             # 原始剧本（.docx/.md/.txt，由 ~preprocess 处理）
config/          # 平台/合规/音色/API 配置
state/           # 全局状态（vectordb / traces）
scripts/         # Shell/Python 脚本
tests/           # 测试套件
review-server/   # 审核 Web 服务（FastAPI）
.claude/agents/  # Agent 定义
.claude/skills/  # Skill 定义
docs/            # 文档
```

各目录详细说明见对应的 README.md。

## 多人协作

```bash
~assign ep01-ep20 alice     # Producer 分配任务
~batch --mine               # Operator 处理自己的任务
~board                      # 查看全局看板
```

## 文档索引

| 文档 | 内容 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | 完整技术参考（Agent 指令） |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献指南 |
| [docs/SETUP-GUIDE.md](docs/SETUP-GUIDE.md) | 环境搭建指南 |
| [docs/ARCHITECTURE-V2-COMPLETE.md](docs/ARCHITECTURE-V2-COMPLETE.md) | v2.0 架构文档 |
| [docs/E2E-WORKFLOW-WITH-ONTOLOGY.md](docs/E2E-WORKFLOW-WITH-ONTOLOGY.md) | E2E 工作流 |
| [docs/V2-IMPLEMENTATION-GUIDE.md](docs/V2-IMPLEMENTATION-GUIDE.md) | v2.0 实施指南 |
| [docs/IMAGE-GENERATION-BEST-PRACTICES.md](docs/IMAGE-GENERATION-BEST-PRACTICES.md) | 图像生成最佳实践 |
| [docs/PHASE6-IMPLEMENTATION.md](docs/PHASE6-IMPLEMENTATION.md) | Phase 6 实现详情 |
| [scripts/README.md](scripts/README.md) | 脚本参考 |
| [config/README.md](config/README.md) | 配置参考 |
| [review-server/README.md](review-server/README.md) | 审核服务文档 |
| [tests/README.md](tests/README.md) | 测试指南 |

## License

Private — 内部使用。
