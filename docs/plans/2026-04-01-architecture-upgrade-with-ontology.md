# 架构升级：加入本体论与状态管理层

**日期**: 2026-04-01  
**版本**: v2.0  
**状态**: 实施中

---

## 执行摘要

本文档定义如何在现有架构基础上，加入**本体论层**和**状态管理层**，将系统从"线性流水线"升级为"状态驱动的镜头工厂"。

### 核心升级

**保留现有优势**：
- ✅ Agent Teams 架构
- ✅ ~scriptwriter / ~preprocess / ~design / ~batch 工作流
- ✅ Phase 1-5 流水线
- ✅ 角色/场景一致性机制（variants + time_of_day）

**新增能力**：
- 🆕 Phase 0: 本体论构建（World State Graph）
- 🆕 Phase 2.5: 资产工厂（Nanobanana Asset Packs）
- 🆕 Phase 3.5: Shot Packet 编译
- 🆕 Phase 6: Audit & Repair 闭环
- 🆕 状态快照机制（CharacterState @ shot）

---

## 新架构拓扑

### 完整流程（7 层 + 原有 5 阶段）

```
[新增] Phase 0: 本体论构建
  ├─ ontology-builder-agent
  └─ 输出: state/ontology/{ep}-world-model.json

Phase 1: 合规预检（不变）
  └─ comply-agent

Phase 2: 视觉指导（不变）
  └─ visual-agent

[新增] Phase 2.5: 资产工厂
  ├─ asset-factory-agent (调用 Nanobanana)
  └─ 输出: assets/packs/{character|scene|prop}/*.png

Phase 3: 美术校验（不变）
  └─ design-agent

[新增] Phase 3.5: Shot Packet 编译
  ├─ memory-agent (检索相关 references)
  ├─ shot-compiler-agent (编译 shot packet)
  └─ 输出: state/shot-packets/{ep}-shot-{N}.json

Phase 4: 音色配置（不变）
  └─ voice-agent

Phase 5: 视频生成（升级为 i2v）
  ├─ gen-worker (改为 img2video 模式)
  └─ 输入: shot packet + reference images

[新增] Phase 6: Audit & Repair
  ├─ qa-agent (3 种 QA: symbolic / visual / semantic)
  ├─ repair-agent (决策: pass / local_repair / regenerate)
  └─ 输出: state/audit/{ep}-shot-{N}-audit.json
```

---

## 数据结构升级

### 新增目录结构

```
state/
├── ontology/                    # 本体论模型（新增）
│   └── {ep}-world-model.json
├── character-states/            # 角色状态快照（新增）
│   └── {ep}-{character}-states.json
├── shot-packets/                # Shot Packet（新增）
│   └── {ep}-shot-{N}.json
├── audit/                       # 审计结果（新增）
│   └── {ep}-shot-{N}-audit.json
├── progress.json                # 进度索引（保留）
└── {ep}-phase{N}.json          # 各阶段状态（保留）

assets/
├── packs/                       # 资产包（新增）
│   ├── characters/
│   │   ├── {角色名}-{variant}-front.png
│   │   ├── {角色名}-{variant}-side.png
│   │   ├── {角色名}-{variant}-back.png
│   │   └── {角色名}-{variant}-expression-{emotion}.png
│   ├── scenes/
│   │   └── {场景名}-{time_of_day}-styleframe.png
│   └── props/
│       └── {道具名}-{condition}.png
├── characters/images/           # 参考图（保留）
├── scenes/images/               # 参考图（保留）
└── ...
```

### World Model 数据结构

```json
{
  "world_id": "qyccan-ep01",
  "episode": "ep01",
  "created_at": "2026-04-01T10:00:00Z",
  
  "entities": {
    "characters": {
      "苏夜": {
        "id": "suye",
        "tier": "protagonist",
        "current_variant": "default",
        "physical": {
          "species": "灵兽",
          "form": "青玉蚕",
          "size": "拇指大小"
        },
        "abilities": {
          "can_speak": false,
          "can_fly": false,
          "cultivation_level": "凡胎级"
        },
        "constraints": {
          "movement": "爬行",
          "视角": "复眼效果"
        }
      }
    },
    
    "locations": {
      "叶红衣闺房": {
        "id": "yehongyi_bedroom",
        "spatial": {
          "type": "indoor",
          "size": "small",
          "layout": "古风闺房"
        },
        "temporal_variants": ["day", "night"],
        "lighting_rules": {
          "day": "柔和日光透过窗纱",
          "night": "烛光摇曳"
        },
        "atmosphere": "温馨、私密"
      }
    },
    
    "props": {
      "戒指": {
        "id": "ring",
        "description": "古朴戒指，内藏戒指老爷爷",
        "owner": "苏夜",
        "condition": "intact"
      }
    }
  },
  
  "relationships": [
    {
      "type": "social.契约",
      "from": "苏夜",
      "to": "叶红衣",
      "properties": {
        "strength": "生死相依",
        "established_at": "ep01_sc01"
      }
    }
  ],
  
  "physics": {
    "gravity": "normal",
    "magic_system": "cultivation",
    "power_scaling": "strict"
  },
  
  "narrative_constraints": {
    "苏夜_cannot_speak_until": "ep07",
    "苏夜_evolution_timeline": {
      "ep01-02": "青玉蚕",
      "ep03-06": "碧鳞蛇",
      "ep07+": "玄冥黑金蟒"
    }
  }
}
```

### Character State 数据结构

```json
{
  "episode": "ep01",
  "character_id": "苏夜",
  "states": [
    {
      "shot_id": "ep01-shot-01",
      "variant": "default",
      "costume": "无（灵兽形态）",
      "emotion": "好奇",
      "injury": "none",
      "knowledge_state": [],
      "location": "叶红衣闺房",
      "props_in_possession": ["戒指"],
      "state_snapshot": {
        "physical": {
          "form": "青玉蚕",
          "size": "拇指大小",
          "color": "碧绿"
        },
        "abilities": {
          "can_speak": false,
          "can_fly": false
        }
      }
    },
    {
      "shot_id": "ep01-shot-05",
      "variant": "default",
      "emotion": "紧张",
      "knowledge_state": ["知道叶红衣被欺负"],
      "state_snapshot": {
        "physical": {
          "form": "青玉蚕",
          "size": "拇指大小"
        }
      }
    }
  ]
}
```

### Shot Packet 数据结构

```json
{
  "shot_id": "ep01-shot-05",
  "episode": "ep01",
  "scene_id": "ep01-sc03",
  "shot_number": 5,
  
  "scene_goal": "苏夜决定保护叶红衣",
  "duration_sec": 8,
  "dialogue_mode": "external_dub",
  
  "characters": [
    {
      "id": "苏夜",
      "state_ref": "苏夜@ep01-shot-05",
      "variant": "default",
      "ref_assets": [
        "assets/packs/characters/苏夜-default-front.png",
        "assets/characters/images/苏夜-default-front.png"
      ],
      "must_preserve": ["form", "size", "color"],
      "current_state": {
        "emotion": "紧张",
        "location": "叶红衣闺房",
        "knowledge": ["知道叶红衣被欺负"]
      }
    },
    {
      "id": "叶红衣",
      "state_ref": "叶红衣@ep01-shot-05",
      "variant": "default",
      "ref_assets": [
        "assets/packs/characters/叶红衣-default-front.png"
      ],
      "must_preserve": ["face", "hair", "costume"]
    }
  ],
  
  "background": {
    "location": "叶红衣闺房",
    "time_of_day": "night",
    "ref_assets": [
      "assets/packs/scenes/叶红衣闺房-night-styleframe.png",
      "assets/scenes/images/叶红衣闺房-night.png"
    ]
  },
  
  "camera": {
    "shot_size": "medium_closeup",
    "movement": "slow_push_in",
    "lens_style": "cinematic",
    "lighting": "烛光摇曳"
  },
  
  "seedance_inputs": {
    "mode": "img2video",
    "images": [
      "assets/packs/characters/苏夜-default-front.png",
      "assets/packs/scenes/叶红衣闺房-night-styleframe.png"
    ],
    "videos": [],
    "audios": [],
    "prompt": "{即梦官方脚本格式的完整提示词}"
  },
  
  "forbidden_changes": [
    "不要改变苏夜的形态（必须是青玉蚕）",
    "不要改变苏夜的大小（拇指大小）",
    "不要让苏夜说话（ep07 之前不能说话）"
  ],
  
  "repair_policy": {
    "max_retries": 2,
    "prefer_local_edit": true
  },
  
  "ontology_constraints": {
    "world_rules": ["gravity: normal", "magic_system: cultivation"],
    "character_abilities": {
      "苏夜": {
        "can_speak": false,
        "can_fly": false
      }
    }
  }
}
```

---

## 新增 Agents

### 1. ontology-builder-agent

**职责**: 从剧本和角色档案构建世界本体模型

**输入**:
- `script/{ep}.md`
- `assets/characters/profiles/*.yaml`
- `assets/scenes/profiles/*.yaml`

**输出**:
- `state/ontology/{ep}-world-model.json`

**执行流程**:
1. 读取剧本，提取实体（角色、场景、道具）
2. 读取角色档案，提取能力、约束、变体
3. 读取场景档案，提取空间、时间、光线规则
4. 构建关系图（社会、空间、因果）
5. 应用叙事约束（时间线、能力限制）
6. 验证逻辑一致性
7. 输出 world-model.json

**新增文件**: `.claude/agents/ontology-builder-agent.md`

---

### 2. asset-factory-agent

**职责**: 调用 Nanobanana 生成资产包

**输入**:
- `state/ontology/{ep}-world-model.json`
- `assets/characters/profiles/*.yaml`
- `assets/scenes/profiles/*.yaml`

**输出**:
- `assets/packs/characters/*.png`
- `assets/packs/scenes/*.png`
- `assets/packs/props/*.png`

**执行流程**:
1. 读取本体模型，获取所有实体
2. 为每个角色的每个变体生成定妆包：
   - front / side / back / expression-{emotion}
3. 为每个场景的每个时段生成 styleframe：
   - {场景名}-{time_of_day}-styleframe.png
4. 为关键道具生成资产：
   - {道具名}-{condition}.png
5. 记录生成参数到 metadata

**新增文件**: `.claude/agents/asset-factory-agent.md`

**新增脚本**: `scripts/nanobanana-caller.sh`

---

### 3. memory-agent

**职责**: 为每个 shot 检索最相关的 references

**输入**:
- `state/ontology/{ep}-world-model.json`
- `outputs/{ep}/visual-direction.yaml`
- `assets/packs/` 目录

**输出**:
- 每个 shot 的 reference 列表

**执行流程**:
1. 读取 shot 上下文（角色、场景、时段）
2. 从 assets/packs/ 检索最相关的资产
3. 优先级排序：
   - 角色当前变体 > 其他变体
   - 场景当前时段 > 其他时段
   - 前一镜结尾帧 > 其他帧
4. 返回 top-K references

**新增文件**: `.claude/agents/memory-agent.md`

---

### 4. shot-compiler-agent

**职责**: 编译 shot packet

**输入**:
- `state/ontology/{ep}-world-model.json`
- `state/character-states/{ep}-{character}-states.json`
- `outputs/{ep}/visual-direction.yaml`
- Memory Agent 输出的 references

**输出**:
- `state/shot-packets/{ep}-shot-{N}.json`

**执行流程**:
1. 读取 shot 定义（visual-direction.yaml）
2. 读取角色状态快照
3. 读取本体约束
4. 组装 shot packet：
   - 角色状态引用
   - 资产引用
   - 禁止变化项
   - 本体约束
5. 验证 packet 完整性
6. 输出 JSON

**新增文件**: `.claude/agents/shot-compiler-agent.md`

---

### 5. qa-agent

**职责**: 审计 shot 输出

**输入**:
- `state/shot-packets/{ep}-shot-{N}.json`
- `outputs/{ep}/videos/shot-{N}.mp4`

**输出**:
- `state/audit/{ep}-shot-{N}-audit.json`

**执行流程**:

**Symbolic QA**（硬逻辑）:
- 角色是否突然换装
- 傷勢是否消失
- 道具是否憑空出現
- 前一鏡知道的秘密，這一鏡是否合理延續

**Visual QA**（画面）:
- 臉像不像（与 reference 对比）
- 衣服是否漂色
- 道具是否消失
- 背景是否跳變

**Semantic QA**（戏剧）:
- 角色情緒有沒有跳太快
- 對白口吻有沒有崩
- 鏡頭語言是否符合戲劇目標

**新增文件**: `.claude/agents/qa-agent.md`

---

### 6. repair-agent

**职责**: 根据 QA 结果决定修复策略

**输入**:
- `state/audit/{ep}-shot-{N}-audit.json`

**输出**:
- 修复决策

**决策树**:
```
if audit.passed:
    return "pass"
elif audit.issues.severity == "low":
    return "local_repair"  # 局部修复
elif audit.issues.severity == "medium":
    if shot.attempt_number < 2:
        return "regenerate_shot"  # 重生该 shot
    else:
        return "local_repair"  # 尝试修补
else:  # high severity
    return "regenerate_shot"
```

**修复策略**:
1. **pass**: 直接通过
2. **local_repair**: 
   - 用 Nanobanana 修关键帧
   - 用 Seedance 局部编辑
3. **regenerate_shot**: 
   - 换 reference 重试
   - 调整 prompt
   - 重新渲染

**新增文件**: `.claude/agents/repair-agent.md`

---

## 现有 Agents 升级

### visual-agent 升级

**新增输入**:
- `state/ontology/{ep}-world-model.json`

**新增输出字段**（visual-direction.yaml）:
```yaml
shots:
  - shot_id: "ep01-shot-01"
    # 新增：本体约束
    ontology_context:
      character_state:
        苏夜:
          variant: "default"
          can_speak: false
          size: "拇指大小"
      location_rules:
        叶红衣闺房:
          time_of_day: "night"
          lighting: "烛光摇曳"
```

**修改文件**: `.claude/agents/visual-agent.md`

---

### gen-worker 升级

**新增模式**: `img2video`

**新增输入**:
- `state/shot-packets/{ep}-shot-{N}.json`

**新增逻辑**:
```python
# 旧逻辑：text2video
payload = {
    "model": "doubao-seedance-1-5-pro",
    "content": [{"type": "text", "text": prompt}]
}

# 新逻辑：img2video
shot_packet = load_shot_packet(shot_id)
payload = {
    "model": "doubao-seedance-1-5-pro",
    "content": [
        {"type": "text", "text": shot_packet["seedance_inputs"]["prompt"]},
        *[{"type": "image_url", "image_url": img} 
          for img in shot_packet["seedance_inputs"]["images"]]
    ]
}
```

**修改文件**: `.claude/agents/gen-worker.md`

---

## 新增 Skills

### ~build-ontology

```bash
~build-ontology ep01       # 为单集构建本体
~build-ontology --all      # 为所有剧本构建本体
```

**实现**: `.claude/skills/build-ontology.md`

---

### ~asset-factory

```bash
~asset-factory             # 为所有角色/场景生成资产包
~asset-factory --character 苏夜  # 只生成指定角色
~asset-factory --scene 叶红衣闺房  # 只生成指定场景
```

**实现**: `.claude/skills/asset-factory.md`

---

### ~compile-shots

```bash
~compile-shots ep01        # 为单集编译 shot packets
~compile-shots --all       # 为所有剧本编译
```

**实现**: `.claude/skills/compile-shots.md`

---

### ~qa

```bash
~qa ep01                   # 审计单集所有 shots
~qa ep01 shot-05           # 审计单个 shot
~qa --type visual          # 只做 visual QA
```

**实现**: `.claude/skills/qa.md`

---

### ~repair

```bash
~repair ep01               # 修复单集失败的 shots
~repair ep01 shot-05       # 修复单个 shot
~repair --strategy local   # 强制局部修复
```

**实现**: `.claude/skills/repair.md`

---

## 配置文件更新

### config/platforms/seedance-v2.yaml

```yaml
# 新增 img2video 模式配置
generation_modes:
  text2video:
    enabled: true
    default: false  # 改为 false
  img2video:
    enabled: true
    default: true   # 改为 true
    reference_mode: "composition"  # composition / keyframes
```

### config/nanobanana/nanobanana-config.yaml（新增）

```yaml
api:
  base_url: "https://generativelanguage.googleapis.com/v1beta"
  model: "gemini-3-pro-image-preview"
  api_key_env: "TUZI_API_KEY"

generation:
  default_aspect_ratio: "1:1"
  default_image_size: "2K"
  
asset_types:
  character_pack:
    angles: ["front", "side", "back"]
    expressions: ["neutral", "happy", "angry", "sad"]
    aspect_ratio: "1:1"
    image_size: "2K"
  
  scene_styleframe:
    aspect_ratio: "16:9"
    image_size: "2K"
  
  prop_pack:
    aspect_ratio: "1:1"
    image_size: "1K"
```

---

## 实施路线图

### Phase 1: 本体论基础（1 周）

**目标**: 建立本体论层

**交付物**:
- [ ] 创建 `state/ontology/` 目录
- [ ] 实现 `ontology-builder-agent.md`
- [ ] 实现 `~build-ontology` skill
- [ ] 为 `qyccan-ep01` 生成 world-model.json
- [ ] 验证本体模型数据结构

---

### Phase 2: 资产工厂（1 周）

**目标**: 集成 Nanobanana 资产生成

**交付物**:
- [ ] 创建 `assets/packs/` 目录
- [ ] 实现 `scripts/nanobanana-caller.sh`
- [ ] 实现 `asset-factory-agent.md`
- [ ] 实现 `~asset-factory` skill
- [ ] 为「苏夜」生成 4 个变体的定妆包
- [ ] 为「叶红衣闺房」生成 day/night styleframe

---

### Phase 3: Shot Packet 编译（1 周）

**目标**: 实现状态驱动的 shot packet

**交付物**:
- [ ] 创建 `state/shot-packets/` 目录
- [ ] 创建 `state/character-states/` 目录
- [ ] 实现 `memory-agent.md`
- [ ] 实现 `shot-compiler-agent.md`
- [ ] 实现 `~compile-shots` skill
- [ ] 为 `qyccan-ep01` 前 3 个 shots 生成 shot packets

---

### Phase 4: img2video 切换（1 周）

**目标**: 升级 gen-worker 为 img2video 模式

**交付物**:
- [ ] 修改 `gen-worker.md` 支持 img2video
- [ ] 修改 `config/platforms/seedance-v2.yaml`
- [ ] 测试 img2video 模式
- [ ] 对比 text2video vs img2video 质量

---

### Phase 5: Audit & Repair（1 周）

**目标**: 补齐审计修复闭环

**交付物**:
- [ ] 创建 `state/audit/` 目录
- [ ] 实现 `qa-agent.md`
- [ ] 实现 `repair-agent.md`
- [ ] 实现 `~qa` skill
- [ ] 实现 `~repair` skill
- [ ] 测试完整闭环

---

### Phase 6: 集成测试（1 周）

**目标**: 端到端跑通新架构

**交付物**:
- [ ] 更新 `~start` skill 集成新 phases
- [ ] 更新 `~batch` skill 集成新 phases
- [ ] 为 `qyccan-ep01` 完整跑通新流程
- [ ] 性能优化
- [ ] 文档更新

---

## 向后兼容策略

### 渐进式升级

**阶段 1**: 新旧并行
- 保留现有 Phase 1-5
- 新增 Phase 0, 2.5, 3.5, 6 为可选
- 通过 `--use-ontology` flag 启用新架构

**阶段 2**: 默认启用
- 新架构成为默认
- 旧架构通过 `--legacy` flag 保留

**阶段 3**: 完全切换
- 移除旧架构
- 新架构成为唯一选项

### 数据迁移

**现有数据保留**:
- `assets/characters/images/` → 保留，作为 fallback
- `assets/scenes/images/` → 保留，作为 fallback
- `state/progress.json` → 保留，扩展字段

**新数据共存**:
- `assets/packs/` → 新增，优先使用
- `state/ontology/` → 新增
- `state/shot-packets/` → 新增

---

## 成本估算

### Nanobanana 成本（Phase 2）

| 任务 | 模型 | 分辨率 | 数量 | 单价 | 小计 |
|------|------|--------|------|------|------|
| 角色定妆包 | Pro | 2K | 10角色 × 4变体 × 4角度 = 160 | $0.24 | $38.4 |
| 场景 styleframe | Pro | 2K | 15场景 × 2时段 = 30 | $0.24 | $7.2 |
| 道具包 | Pro | 2K | 10道具 × 2状态 = 20 | $0.24 | $4.8 |
| **总计** | | | | | **$50.4** |

### 对比现有成本

**旧流程**（60 集 × 12 镜次 = 720 shots）:
- Seedance text2video: 720 × $0.5 = $360
- 返工率 30%: $108
- **总成本**: $468

**新流程**:
- Nanobanana 资产包: $50.4（一次性）
- Seedance img2video: 720 × $0.5 = $360
- 返工率 5%: $18
- **总成本**: $428.4

**净节省**: $468 - $428.4 = **$39.6**（首次）  
**长期收益**: 返工减少 + 质量提升 + 资产可复用

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 本体构建复杂度高 | 中 | 先做最小 schema，逐步扩展 |
| Nanobanana 生成质量不稳定 | 高 | 多轮迭代 + 人工审核 + 保留 text2video 备选 |
| Shot packet 编译耗时 | 中 | 缓存机制 + 并行处理 |
| img2video 动作不自然 | 中 | 测试首尾帧模式 + 调整提示词 |
| 向后兼容成本 | 低 | 渐进式升级 + 数据共存 |

---

## 下一步行动

**本周立即开始**（Phase 1）:
1. [ ] 创建 `state/ontology/` 目录结构
2. [ ] 实现 `ontology-builder-agent.md`
3. [ ] 实现 `~build-ontology` skill
4. [ ] 为 `qyccan-ep01` 生成 world-model.json

**下周完成**（Phase 2）:
5. [ ] 创建 `assets/packs/` 目录结构
6. [ ] 实现 `scripts/nanobanana-caller.sh`
7. [ ] 实现 `asset-factory-agent.md`
8. [ ] 为「苏夜」生成定妆包

---

**文档作者**: Claude Code  
**审核状态**: 待审核  
**预计完成时间**: 6 周
