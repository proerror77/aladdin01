# AGENTS.md

AI 短剧自动生成系统的 Agent 规格文档。供 Codex、Gemini CLI 或其他 AI coding agent 使用。

本文档描述每个 agent 的职责、输入输出、调用方式，以及系统的整体流水线结构。

---

## 系统概览

```
剧本 (.md)
  └─ 流水线（当前以 workflow-sync / concat-episode 为落盘入口）
       ├─ Phase 0  ontology-builder-agent   世界本体模型
       ├─ Phase 1  comply-agent             合规预检 → render-script.md
       ├─ Phase 2  visual-agent             镜次拆解 → visual-direction.yaml
       ├─ Phase 2.2 narrative-review-agent  叙事审查（自动修复）
       ├─ Phase 2.3 storyboard-agent        分镜图生成
       ├─ Phase 2.5 asset-factory-agent     资产包生成（v2.0）
       ├─ Phase 3  design-agent             参考图存在性校验
       ├─ Phase 3.5 shot-compiler-agent     Shot Packet 编译（v2.0）
       ├─ Phase 4  voice-agent              音色配置
       ├─ Phase 5  gen-worker × N           视频生成（并行）
       └─ Phase 6  qa-agent + repair-agent  质量审计 + 自动修复（v2.0）
```

**同步/修复入口**：`scripts/workflow-sync.py`
**成片交付入口**：`scripts/concat-episode.sh --project <project> <ep>`

---

## 当前可用入口

当前仓库中不存在 `scripts/pipeline-runner.py` 或 `config/pipeline/phases.yaml`。
现有可用入口以文件系统产物和同步脚本为准：

```bash
# 同步已有 episode 产物、补 phase/shot state、生成 deliverables/review 入口
python3 scripts/workflow-sync.py --project qyccan --episode ep01

# 批量同步 outputs 下已有集数
python3 scripts/workflow-sync.py --project qyccan --all-output-episodes

# 生成当前集的最终成片和交付清单
bash scripts/concat-episode.sh --project qyccan ep01
```

---

## 目录结构（关键路径）

```
projects/{project}/
  script/{ep}.md                          原始剧本
  outputs/{ep}/
    render-script.md                      合规改写后剧本
    visual-direction.yaml                 结构化镜次数据
    art-direction-review.md               美术校验报告
    voice-assignment.md                   音色分配报告
    storyboard/shot-{N}.png               分镜图
    videos/shot-{N}.mp4                   规范命名的镜次视频（流水线内部）
    deliverables/final.mp4                人类查看的最终成片
    deliverables/shots/shot-{N}.mp4       人类查看的逐镜成片
    deliverables/manifest.json            交付清单
    review/storyboard-preview.md          人类查看的分镜入口
    build/raw-videos/*.mp4                原始下载视频 / hash 命名中间件
  state/
    {ep}-phase{N}.json                    各 Phase 状态
    {ep}-shot-{N}.json                    各 Shot 状态
    ontology/{ep}-world-model.json        世界本体模型
    shot-packets/{ep}-shot-{N}.json       Shot Packet
    audit/{ep}-shot-{N}-audit.json        QA 审计结果
    design-lock.json                      参考图锁定清单
  assets/
    characters/images/                    角色参考图
    characters/profiles/                  角色档案 (.yaml)
    scenes/images/                        场景参考图
    scenes/profiles/                      场景档案 (.yaml)
    packs/                                v2.0 资产包

scripts/workflow-sync.py                  当前同步/修复入口
scripts/concat-episode.sh                 当前成片交付入口
scripts/api-caller.sh                     统一 API 调用
scripts/trace.sh                          Trace 写入
```

---

## Agent 规格

### comply-agent — 合规预检

**Phase**: 1  
**职责**: 四层合规检测，输出合规改写版剧本。

**输入**:
| 参数 | 路径 |
|------|------|
| 原始剧本 | `projects/{project}/script/{ep}.md` |
| 敏感词表 | `config/compliance/blocklist.yaml` |
| 合规规则 | `config/compliance/policy-rules.yaml` |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/outputs/{ep}/render-script.md` | 合规改写后剧本 |
| `projects/{project}/outputs/{ep}/compliance-report.md` | 检测报告 |
| `projects/{project}/state/{ep}-phase1.json` | Phase 状态 |

**检测层次**:
1. 敏感词表精确匹配
2. LLM 语义评分（violence/sexual/hate/self_harm）
3. OpenAI Moderation API（可选，需 `OPENAI_API_KEY`）
4. AIGC 痕迹检测（可选，需 `AIGC_DETECT_API_KEY`）

---

### visual-agent — 视觉指导

**Phase**: 2  
**职责**: 将 render_script 拆解为结构化镜次列表（visual-direction.yaml）。

**输入**:
| 参数 | 路径 |
|------|------|
| 合规剧本 | `projects/{project}/outputs/{ep}/render-script.md` |
| 世界模型（可选） | `projects/{project}/state/ontology/{ep}-world-model.json` |
| 风格配置 | `config/styles/{style_id}.yaml` |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/outputs/{ep}/visual-direction.yaml` | 结构化镜次数据 |
| `projects/{project}/state/{ep}-phase2.json` | Phase 状态 |

**visual-direction.yaml 关键字段**（每个 shot）:
```yaml
shots:
  - shot_id: ep01-shot-01
    shot_index: 1
    seedance_prompt: "..."
    duration: 8
    generation_mode: text2video   # 或 img2video
    has_dialogue: true
    audio:
      character: "角色名"
      text: "台词内容"
    references:
      - type: character
        name: "角色名"
        variant_id: default
      - type: scene
        name: "场景名"
        time_of_day: day
    storyboard_image_path: null   # storyboard-agent 填充
```

---

### narrative-review-agent — 叙事审查

**Phase**: 2.2  
**职责**: 审查 visual-direction.yaml 的叙事质量，自动修复后继续；低于阈值退回 visual-agent。

**输入**:
| 参数 | 路径 |
|------|------|
| 镜次数据 | `projects/{project}/outputs/{ep}/visual-direction.yaml` |
| 合规剧本 | `projects/{project}/outputs/{ep}/render-script.md` |
| 世界模型（可选） | `projects/{project}/state/ontology/{ep}-world-model.json` |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/outputs/{ep}/visual-direction.yaml` | 修复后（in-place 更新） |
| `projects/{project}/outputs/{ep}/narrative-review.md` | 审查报告 |
| `projects/{project}/state/{ep}-phase2.2.json` | Phase 状态（含 `result: auto_pass/fixed_pass/reject`） |

**决策阈值**:
- ≥85 分 → `auto_pass`，继续
- 50-84 分 → `fixed_pass`，修复后继续
- <50 分 → `reject`，退回 visual-agent（最多重试 2 次）

---

### storyboard-agent — 分镜图生成

**Phase**: 2.3  
**职责**: 为每个 shot 生成构图参考图，更新 visual-direction.yaml 的 `storyboard_image_path`。

**输入**:
| 参数 | 路径 |
|------|------|
| 镜次数据 | `projects/{project}/outputs/{ep}/visual-direction.yaml` |
| 角色参考图 | `projects/{project}/assets/characters/images/` |
| 场景参考图 | `projects/{project}/assets/scenes/images/` |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/outputs/{ep}/storyboard/shot-{N}.png` | 构图参考图 |
| `projects/{project}/outputs/{ep}/visual-direction.yaml` | 更新 `storyboard_image_path` |
| `projects/{project}/outputs/{ep}/storyboard-preview.md` | 预览报告 |
| `projects/{project}/state/{ep}-phase2.3.json` | Phase 状态 |

**调用 API**: `scripts/api-caller.sh image_gen generate`（需 `TUZI_API_KEY` 或 `IMAGE_GEN_API_KEY`）

---

### asset-factory-agent — 资产工厂（v2.0）

**Phase**: 2.5（可选，需 `--use-v2`）  
**职责**: 生成角色定妆包、场景 styleframe、道具包。

**输入**:
| 参数 | 路径 |
|------|------|
| 世界模型 | `projects/{project}/state/ontology/{ep}-world-model.json` |
| 角色档案 | `projects/{project}/assets/characters/profiles/*.yaml` |
| 场景档案 | `projects/{project}/assets/scenes/profiles/*.yaml` |
| Nanobanana 配置 | `config/nanobanana/nanobanana-config.yaml` |

**输出**:
```
projects/{project}/assets/packs/
  characters/{角色名}-{variant}-{angle}.png
  scenes/{场景名}-{time_of_day}-styleframe.png
  props/{道具名}-{condition}.png
  asset-manifest.json
```

**幂等性**: 文件已存在则跳过，不重复生成。

---

### design-agent — 美术校验

**Phase**: 3  
**职责**: 纯文件存在性检查，校验参考图是否齐全。不生成图，不调用 LLM。

**输入**:
| 参数 | 路径 |
|------|------|
| 镜次数据 | `projects/{project}/outputs/{ep}/visual-direction.yaml` |
| 参考图锁定 | `projects/{project}/state/design-lock.json` |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/outputs/{ep}/art-direction-review.md` | 校验报告（缺失清单） |
| `projects/{project}/state/{ep}-phase3.json` | Phase 状态 |

**检查路径规则**:
- 角色（单变体）: `assets/characters/images/{角色名}-front.png`
- 角色（多变体）: `assets/characters/images/{角色名}-{variant_id}-front.png`
- 场景: `assets/scenes/images/{场景名}-{time_of_day}.png`

---

### shot-compiler-agent — Shot Packet 编译（v2.0）

**Phase**: 3.5（可选，需 `--use-v2`）  
**职责**: 组装完整的 shot packet，供 gen-worker 使用。

**输入**:
| 参数 | 路径 |
|------|------|
| 镜次数据 | `projects/{project}/outputs/{ep}/visual-direction.yaml` |
| 世界模型 | `projects/{project}/state/ontology/{ep}-world-model.json` |
| memory-agent 输出 | references（由 memory-agent 内联提供） |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/state/shot-packets/{ep}-shot-{N}.json` | Shot Packet |
| `projects/{project}/state/{ep}-phase3.5.json` | Phase 状态 |

**Shot Packet 关键字段**:
```json
{
  "shot_id": "ep01-shot-03",
  "seedance_inputs": {
    "mode": "img2video",
    "prompt": "...",
    "images": ["path/to/ref1.png", "path/to/ref2.png"],
    "duration": 8
  },
  "continuity_inputs": {
    "previous_shot_id": "ep01-shot-02",
    "previous_end_frame_path": "outputs/ep01/storyboard/ep01-shot-02-end-frame.png"
  },
  "ontology_constraints": {
    "forbidden_changes": ["角色服装", "道具状态"],
    "repair_policy": "regenerate"
  }
}
```

---

### voice-agent — 音色配置

**Phase**: 4  
**职责**: 为有对白的角色配置音色。

**输入**:
| 参数 | 路径 |
|------|------|
| 合规剧本 | `projects/{project}/outputs/{ep}/render-script.md` |
| 镜次数据 | `projects/{project}/outputs/{ep}/visual-direction.yaml` |
| 预设音色库 | `config/voices/` |
| 已有音色（跨集复用） | `projects/{project}/assets/characters/voices/` |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/assets/characters/voices/{角色名}/voice-config.yaml` | 音色配置 |
| `projects/{project}/outputs/{ep}/voice-assignment.md` | 分配报告 |
| `projects/{project}/state/{ep}-phase4.json` | Phase 状态 |

**注意**: `voice-config.yaml` 当前为 TTS 预留（`tts_platform: "pending"`）。gen-worker 通过 Seedance API 的 `generate_audio` 参数控制音频，不读取此文件。

---

### gen-worker — 视频生成

**Phase**: 5（并行，每个 shot 一个 worker）  
**职责**: 处理单个镜次的视频生成，含重试和提示词改写逻辑。

**输入**（由 team-lead 传入）:
| 参数 | 说明 |
|------|------|
| `project` | 项目名 |
| `ep` | 集数 ID |
| `shot_id` | 镜次 ID |
| `shot_index` | 镜次序号 |
| `prompt` | Seedance 提示词 |
| `duration` | 时长（秒） |
| `ratio` | 宽高比（`9:16` / `16:9` 等） |
| `generation_mode` | `text2video` 或 `img2video` |
| `reference_images` | 参考图路径列表（img2video 时使用） |
| `generate_audio` | 是否生成音频（来自 `has_dialogue` 字段） |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/outputs/{ep}/videos/shot-{N}.mp4` | 生成视频（流水线内部 canonical 输出） |
| `projects/{project}/outputs/{ep}/deliverables/shots/shot-{N}.mp4` | 人类查看的逐镜成片（由 `workflow-sync.py` / `concat-episode.sh` 镜像） |
| `projects/{project}/state/{ep}-shot-{N}.json` | Shot 状态（`gen_status: completed/failed`） |

**重试机制**:
1. 原始 prompt 最多重试 5 次
2. 5 次失败 → LLM 最小改写 prompt
3. 每轮改写后重试 3 次，最多 3 轮改写
4. 全部失败 → 标记 `gen_status: failed`

**API 调用**: `scripts/api-caller.sh seedance create` / `scripts/api-caller.sh seedance status`  
**环境变量**: `ARK_API_KEY`（必需）

---

### qa-agent — 质量审计（v2.0）

**Phase**: 6（可选，需 `--use-v2`）  
**职责**: 审计 shot 输出，执行 3 种 QA。

**输入**:
| 参数 | 路径 |
|------|------|
| Shot Packet | `projects/{project}/state/shot-packets/{ep}-shot-{N}.json` |
| 生成视频 | `projects/{project}/outputs/{ep}/videos/shot-{N}.mp4` |
| 世界模型 | `projects/{project}/state/ontology/{ep}-world-model.json` |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/state/audit/{ep}-shot-{N}-audit.json` | 审计结果 |

**审计结果格式**:
```json
{
  "shot_id": "ep01-shot-03",
  "repair_action": "pass",        // pass / local_repair / regenerate
  "issues": [],
  "severity": "none"
}
```

---

### repair-agent — 自动修复（v2.0）

**Phase**: 6（可选，需 `--use-v2`）  
**职责**: 根据 QA 结果调整 shot packet，由 team-lead 编排后续重新生成。

**输入**（由 team-lead 传入）:
| 参数 | 说明 |
|------|------|
| `project` | 项目名 |
| `ep` | 集数 ID |
| `shot_id` | 镜次 ID |
| `repair_strategy` | `local_repair` 或 `adjust_packet` |
| `signal_mode` | `false`（team-lead 编排模式，不使用信号文件） |
| `attempt` | 当前重试次数 |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/state/shot-packets/{ep}-shot-{N}.json` | 更新后的 Shot Packet |
| `projects/{project}/state/audit/{ep}-shot-{N}-repair-history.json` | 修复历史 |

**重要**: `signal_mode: false` 时，repair-agent 只调整 shot packet 后退出，不等待 gen-worker。team-lead 负责在 repair-agent 完成后 spawn gen-worker，再 spawn qa-agent 验证。

**Phase 6 编排流程**（team-lead 执行）:
```
for each shot:
  spawn qa-agent → 读取 repair_action
  if pass: 继续
  if local_repair: spawn repair-agent (signal_mode=false, repair_strategy=local_repair)
  if regenerate:
    for attempt in 1..3:
      spawn repair-agent (signal_mode=false, repair_strategy=adjust_packet)
      spawn gen-worker (重新生成)
      spawn qa-agent (验证)
      if pass: break
```

---

### ontology-builder-agent — 本体论构建（v2.0）

**Phase**: 0（可选，需 `--use-v2`）  
**职责**: 从剧本和档案构建世界本体模型。

**输入**:
| 参数 | 路径 |
|------|------|
| 剧本 | `projects/{project}/script/{ep}.md` |
| 角色档案 | `projects/{project}/assets/characters/profiles/*.yaml` |
| 场景档案 | `projects/{project}/assets/scenes/profiles/*.yaml` |

**输出**:
| 文件 | 说明 |
|------|------|
| `projects/{project}/state/ontology/{ep}-world-model.json` | 世界本体模型 |
| `projects/{project}/state/{ep}-phase0.json` | Phase 状态 |

**world-model.json 关键结构**:
```json
{
  "entities": {
    "characters": [...],
    "scenes": [...],
    "props": [...]
  },
  "relations": [...],
  "physics_rules": [...],
  "narrative_constraints": [...]
}
```

---

### memory-agent — 参考资产检索（v2.0）

**职责**: 为每个 shot 检索最相关的参考资产（两段检索）。由 shot-compiler-agent 内部调用。

**两段检索流程**:
1. 规划段：从 LanceDB 查实体/状态/关系，确定本镜需要的角色形态和场景状态
2. 取图段：基于规划结果构造精确 query，查 `search-assets`

**降级策略**: LanceDB 不可用时，降级为文件名精确匹配。

---

### gate-agent — 自动评分过关

**职责**: 在确认点前自动评分，决定自动过关/退回/推送人审。由 visual-agent 内部调用。

**评分阈值**（`config/scoring/auto-gate-rules.yaml`）:
- ≥85 分 → 自动通过，不推飞书
- 50-84 分 → 推飞书人审
- <50 分 → 自动退回重做

---

## 剧本创作 Agent（~scriptwriter 流程）

以下 agent 用于从创意生成剧本，独立于视频生成流水线。

| Agent | 职责 | 输出 |
|-------|------|------|
| `outline-agent` | 生成故事大纲 | `outputs/scriptwriter/{project}/outline.md` |
| `character-creator-agent` | 生成角色档案 | `outputs/scriptwriter/{project}/characters/*.yaml` |
| `scene-creator-agent` | 生成场景档案 | `outputs/scriptwriter/{project}/scenes/*.yaml` |
| `episode-writer-agent` | 生成分集剧本（并行） | `outputs/scriptwriter/{project}/episodes/ep*.md` |
| `script-reviewer-agent` | 质量检查 | `outputs/scriptwriter/{project}/review-report.md` |
| `format-converter-agent` | 格式转换合并 | `raw/{project}-complete.md` |
| `preprocess-agent` | 长剧本拆解 + 角色融合 | `projects/{project}/script/ep*.md` |

---

## 环境变量

| 变量 | 用途 | 必需 |
|------|------|------|
| `ARK_API_KEY` | 火山方舟（Seedance 视频生成） | 必需 |
| `TUZI_API_KEY` | 兔子 API（图像生成 + LLM） | 推荐 |
| `IMAGE_GEN_API_URL` | 自定义图像生成端点 | 可选 |
| `IMAGE_GEN_API_KEY` | 自定义图像生成 Key | 可选 |
| `OPENAI_API_KEY` | Moderation API（Phase 1 第三层） | 可选 |
| `AIGC_DETECT_API_KEY` | AIGC 检测 API | 可选 |
| `DEEPSEEK_API_KEY` | Trace 摘要 | 可选 |
| `LARK_APP_ID` | 飞书审核通知 | 可选 |
| `LARK_APP_SECRET` | 飞书审核通知 | 可选 |

---

## Shot 状态机

```
pending → generating → generated → auditing → done
              ↓                        ↓
            failed                 repairing → generating (重试)
                                       ↓
                                     failed
```

**事件列表**:
| 事件 | 触发时机 |
|------|---------|
| `gen_started` | gen-worker 开始生成 |
| `gen_success` | 视频下载成功 |
| `gen_failed` | 重试耗尽仍失败 |
| `audit_start` | qa-agent 开始审计 |
| `audit_pass` | QA 通过 |
| `audit_repair` | QA 要求 local_repair |
| `audit_regen` | QA 要求 regenerate |
| `repair_done` | repair-agent 调整完 packet，准备重新生成 |
| `repair_failed` | 超过 max_retries |

**当前 CLI 入口**:
```bash
python3 scripts/workflow-sync.py --project qyccan --episode ep01
bash scripts/concat-episode.sh --project qyccan ep01
```
