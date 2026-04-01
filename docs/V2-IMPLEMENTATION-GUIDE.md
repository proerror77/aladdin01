# v2.0 架构完整实现指南

**日期**: 2026-04-01  
**版本**: v2.0 完整升级

---

## 实现概览

本文档提供 v2.0 架构的完整实现指南，包括所有新 phases 的 agents、skills 和配置文件。

---

## 实现清单

### ✅ 已完成
- [x] 配置文件（world-model-schema.yaml, shot-packet-schema.yaml, nanobanana-config.yaml）
- [x] E2E 流程文档（docs/E2E-WORKFLOW-WITH-ONTOLOGY.md）

### 🔄 待实现

#### Phase 0: 本体论构建
- [ ] `.claude/agents/ontology-builder-agent.md`
- [ ] `.claude/skills/build-ontology.md`

#### Phase 2.5: 资产工厂
- [ ] `.claude/agents/asset-factory-agent.md`
- [ ] `.claude/skills/asset-factory.md`
- [ ] `scripts/nanobanana-caller.sh`

#### Phase 2: Visual Agent 升级
- [ ] 升级 `.claude/agents/visual-agent.md`（读取 world-model.json）

#### Phase 3.5: Shot Packet 编译
- [ ] `.claude/agents/memory-agent.md`
- [ ] `.claude/agents/shot-compiler-agent.md`

#### Phase 5: Gen Worker 升级
- [ ] 升级 `.claude/agents/gen-worker.md`（支持 img2video）

#### Phase 6: Audit & Repair
- [ ] `.claude/agents/qa-agent.md`
- [ ] `.claude/agents/repair-agent.md`

#### 集成
- [ ] 升级 `.claude/skills/start.md`（集成 Phase 3.5 和 Phase 6）
- [ ] 升级 `.claude/skills/batch.md`（集成 Phase 3.5 和 Phase 6）
- [ ] 升级 `.claude/skills/scriptwriter-to-video.md`（集成 Phase 0 和 Phase 2.5）

#### 文档
- [ ] 更新 `CLAUDE.md`

---

## 关键实现要点

### 1. ontology-builder-agent

**职责**: 从剧本+角色档案+场景档案中提取实体、关系、物理规则、叙事约束。

**输入**:
- `script/{ep}.md`
- `assets/characters/profiles/*.yaml`
- `assets/scenes/profiles/*.yaml`

**输出**:
- `state/ontology/{ep}-world-model.json`

**关键步骤**:
1. 读取剧本和档案
2. 提取角色实体（variants, abilities, evolution_timeline）
3. 提取场景实体（spatial_properties, time_variants）
4. 提取道具实体（states, owner, significance）
5. 提取关系（social, spatial, causal, temporal）
6. 提取物理规则（gravity, magic_system）
7. 提取叙事约束（character_abilities, prop_states, knowledge_states）
8. 验证逻辑一致性
9. 写入 world-model.json

**LLM 调用**: 使用 api-caller.sh 调用 LLM 提取结构化信息。

---

### 2. ~build-ontology skill

**用法**:
```bash
~build-ontology ep01           # 单集模式
~build-ontology --all          # 批量模式（所有剧本）
~build-ontology --validate ep01 # 验证模式
```

**流程**:
1. 检查输入文件是否存在
2. 调用 ontology-builder-agent
3. 验证输出的 world-model.json
4. 写入状态文件 `state/{ep}-phase0.json`

---

### 3. asset-factory-agent

**职责**: 调用 Nanobanana 生成角色定妆包、场景 styleframe、道具包。

**输入**:
- `assets/characters/profiles/*.yaml`
- `assets/scenes/profiles/*.yaml`
- `state/ontology/*-world-model.json`（可选，用于提取道具）

**输出**:
- `assets/packs/characters/{角色名}-{variant}-{angle}.png`
- `assets/packs/scenes/{场景名}-{time_of_day}-styleframe.png`
- `assets/packs/props/{道具名}-{condition}.png`

**关键步骤**:
1. 读取所有角色档案
2. 对每个角色的每个变体：
   - 调用 nanobanana-caller.sh generate_character_pack
   - 生成 front/side/back 视图
   - 生成 neutral/happy/angry/sad/surprised 表情
3. 读取所有场景档案
4. 对每个场景的每个时段：
   - 调用 nanobanana-caller.sh generate_scene_styleframe
   - 生成 day/night/dusk/dawn styleframe
5. 从本体模型提取关键道具
6. 对每个道具的每个状态：
   - 调用 nanobanana-caller.sh generate_prop_pack
   - 生成 intact/damaged/destroyed 图
7. 主角形象迭代审核（推飞书）

**幂等性**: 生成前检查目标文件是否已存在，已存在则跳过。

---

### 4. nanobanana-caller.sh

**功能**: 封装 Nanobanana API 调用。

**函数**:
```bash
generate_image() {
    local prompt="$1"
    local aspect_ratio="$2"
    local image_size="$3"
    local output_path="$4"
    
    # 调用 Nanobanana API
    # 使用 TUZI_API_KEY
}

generate_character_pack() {
    local character_name="$1"
    local variant="$2"
    local appearance="$3"
    local output_dir="$4"
    
    # 生成 front/side/back 视图
    # 生成表情包
}

generate_scene_styleframe() {
    local scene_name="$1"
    local scene_description="$2"
    local time_of_day="$3"
    local lighting="$4"
    local output_path="$5"
    
    # 生成场景 styleframe
}

generate_prop_pack() {
    local prop_name="$1"
    local description="$2"
    local condition="$3"
    local output_path="$4"
    
    # 生成道具图
}
```

**配置**: 读取 `config/nanobanana/nanobanana-config.yaml`。

---

### 5. visual-agent 升级

**新增功能**: 读取 world-model.json，在 visual-direction.yaml 中输出 variant_id 和 time_of_day。

**关键改动**:
```yaml
shots:
  - shot_id: "ep01-shot-05"
    references:
      characters:
        - name: "苏夜"
          variant_id: "qingyu_silkworm"  # ✨ 新增
      scene:
        name: "叶红衣闺房"
        time_of_day: "night"  # ✨ 新增
```

**实现**:
1. 读取 `state/ontology/{ep}-world-model.json`
2. 从 world_model.entities.characters 中获取 current_variant
3. 从剧本中推断 time_of_day（或从场景档案读取）
4. 写入 visual-direction.yaml

---

### 6. memory-agent

**职责**: 为每个 shot 检索最相关的 references。

**输入**:
- `outputs/{ep}/visual-direction.yaml`
- `assets/packs/`
- `assets/characters/images/`
- `assets/scenes/images/`
- `outputs/{ep}/videos/`（前一镜）

**输出**: JSON 格式的 references 列表。

**优先级**:
1. `assets/packs/` （最高）
2. `assets/characters/images/` 或 `assets/scenes/images/`
3. 前一镜结尾帧

**关键步骤**:
1. 读取 shot 定义（从 visual-direction.yaml）
2. 对每个角色：
   - 检查 `assets/packs/characters/{角色名}-{variant}-front.png` 是否存在
   - 如不存在，检查 `assets/characters/images/{角色名}-{variant}-front.png`
   - 如不存在，使用 default 变体
3. 对场景：
   - 检查 `assets/packs/scenes/{场景名}-{time_of_day}-styleframe.png` 是否存在
   - 如不存在，检查 `assets/scenes/images/{场景名}-{time_of_day}.png`
   - 如不存在，使用其他时段的场景图
4. 提取前一镜结尾帧（如果存在）
5. 排序和过滤（top-K）
6. 输出 JSON

---

### 7. shot-compiler-agent

**职责**: 编译完整的 shot packet。

**输入**:
- `outputs/{ep}/visual-direction.yaml`
- `state/ontology/{ep}-world-model.json`
- memory-agent 输出的 references

**输出**:
- `state/shot-packets/{ep}-shot-{N}.json`

**关键步骤**:
1. 读取 shot 定义
2. 读取角色状态快照（从 world-model 或 character-states）
3. 调用 memory-agent 检索 references
4. 读取本体约束
5. 组装 shot packet：
   - shot_id, episode, scene_id, shot_number
   - characters（含 state_ref, variant, ref_assets, must_preserve, current_state）
   - background（含 location, time_of_day, ref_assets）
   - camera
   - seedance_inputs（mode=img2video, images, prompt）
   - forbidden_changes（从本体约束生成）
   - repair_policy
   - ontology_constraints
6. 验证 packet 完整性
7. 写入 JSON

---

### 8. gen-worker 升级

**新增功能**: 支持读取 shot packet，使用 img2video 模式。

**关键改动**:
1. 检查 `state/shot-packets/{shot_id}.json` 是否存在
2. 如存在，读取 shot packet：
   - 使用 `seedance_inputs.mode`（img2video）
   - 使用 `seedance_inputs.images` 作为参考图
   - 使用 `seedance_inputs.prompt`
3. 如不存在，回退到旧模式（读取 visual-direction.yaml）
4. 调用 api-caller.sh seedance-generate（img2video 模式）

**兼容性**: 完全向后兼容，没有 shot packet 时使用旧流程。

---

### 9. qa-agent

**职责**: 审计 shot 输出，执行 3 种 QA。

**输入**:
- `state/shot-packets/{ep}-shot-{N}.json`
- `outputs/{ep}/videos/shot-{N}.mp4`
- `state/ontology/{ep}-world-model.json`

**输出**:
- `state/audit/{ep}-shot-{N}-audit.json`

**3 种 QA**:

**Symbolic QA（硬逻辑）**:
- 角色是否突然换装
- 伤势是否消失
- 道具是否凭空出现
- 知识状态是否合理

**Visual QA（画面）**:
- 脸像不像（与 reference 对比）
- 衣服是否漂色
- 道具是否消失
- 背景是否跳变

**Semantic QA（戏剧）**:
- 角色情绪是否跳太快
- 对白口吻是否崩
- 镜头语言是否符合戏剧目标

**输出格式**:
```json
{
  "shot_id": "ep01-shot-05",
  "passed": false,
  "issues": [
    {
      "type": "symbolic",
      "items": [{"type": "costume_change", "severity": "high"}]
    },
    {
      "type": "visual",
      "items": [{"type": "face_mismatch", "similarity": 0.65, "severity": "high"}]
    }
  ],
  "repair_action": "local_repair"
}
```

**修复策略决定**:
- high_severity_count == 0 && medium_severity_count == 0 → pass
- high_severity_count <= 1 → local_repair
- high_severity_count > 1 → regenerate

---

### 10. repair-agent

**职责**: 根据 QA 结果执行修复策略。

**输入**:
- `state/audit/{ep}-shot-{N}-audit.json`
- `state/shot-packets/{ep}-shot-{N}.json`
- `outputs/{ep}/videos/shot-{N}.mp4`

**输出**: 修复后的视频（如需修复）。

**3 种修复策略**:

**pass**: 直接通过，无需修复。

**local_repair**: 局部修复
- face_mismatch → repair_face_with_nanobanana（用 Nanobanana 修复关键帧）
- costume_change → adjust_prompt_and_regenerate（调整 prompt 重新生成）
- prop_disappeared → repair_prop_with_seedance（Seedance 局部编辑）
- background_jump → use_prev_frame_as_reference（调整前一帧作为参考）

**regenerate**: 重新生成
- 分析失败原因
- 调整策略：
  - change_reference（换一组参考图）
  - adjust_prompt（调整 prompt）
  - change_model（换模型）
- 调用 gen-worker 重新生成
- 重新审计

**最大重试次数**: 默认 3 次。

---

### 11. ~batch 和 ~start 升级

**新增 Phase 3.5**:
```bash
# Phase 3.5: Shot Packet 编译
for shot_id in $(yq eval '.shots[].shot_id' outputs/${ep}/visual-direction.yaml); do
    # 调用 memory-agent
    references=$(memory-agent "$shot_id")
    
    # 调用 shot-compiler-agent
    shot-compiler-agent "$shot_id" "$references"
done
```

**新增 Phase 6**:
```bash
# Phase 6: Audit & Repair
for shot_id in $(yq eval '.shots[].shot_id' outputs/${ep}/visual-direction.yaml); do
    # 调用 qa-agent
    qa-agent "$shot_id"
    
    # 调用 repair-agent
    repair-agent "$shot_id"
done
```

**兼容性**: 检查 world-model.json 和 shot-packets/ 是否存在，不存在则跳过新 phases。

---

### 12. ~scriptwriter-to-video 升级

**新增步骤**:
```bash
# Step 2: 构建本体（在 ~scriptwriter 之后）
~build-ontology --all

# Step 3: 生成资产（在 ~build-ontology 之后）
~asset-factory

# Step 4: 批量生成视频（在 ~asset-factory 之后）
~batch
```

**完整流程**:
```
~scriptwriter → ~build-ontology → ~asset-factory → ~batch
```

---

## 实现优先级

### 第一阶段（核心功能）
1. ontology-builder-agent + ~build-ontology
2. nanobanana-caller.sh
3. asset-factory-agent + ~asset-factory
4. memory-agent
5. shot-compiler-agent

### 第二阶段（集成）
6. visual-agent 升级
7. gen-worker 升级
8. ~batch 和 ~start 升级

### 第三阶段（质量保证）
9. qa-agent
10. repair-agent

### 第四阶段（E2E）
11. ~scriptwriter-to-video 升级
12. CLAUDE.md 更新

---

## 测试流程

### 单元测试
```bash
# 测试 ontology-builder
~build-ontology ep01

# 测试 asset-factory
~asset-factory

# 测试 memory-agent
memory-agent "ep01-shot-05"

# 测试 shot-compiler
shot-compiler-agent "ep01-shot-05"
```

### 集成测试
```bash
# 测试单集流程
~start ep01

# 测试批量流程
~batch
```

### E2E 测试
```bash
# 测试完整流程
~scriptwriter-to-video --idea "测试创意" --episodes 3 --length short
```

---

## 回退策略

所有新 phases 都是**可选的**，系统会自动检测并回退：

| 检查项 | 不存在时的行为 |
|--------|---------------|
| world-model.json | Phase 2 正常运行，不读取本体约束 |
| assets/packs/ | 使用 assets/images/ 作为 fallback |
| shot-packets/ | gen-worker 使用 visual-direction.yaml |
| Phase 6 | 跳过 Audit & Repair |

**兼容性保证**: 旧流程完全不受影响。

---

## 下一步

1. **选择实现方式**：
   - 方式 A: 我逐个实现所有文件（需要多轮对话）
   - 方式 B: 你基于本指南自行实现
   - 方式 C: 我先实现核心 agents（Phase 0, 2.5, 3.5），你实现其余部分

2. **优先级排序**：
   - 如果你想快速看到效果，先实现 Phase 0 + Phase 2.5
   - 如果你想完整升级，按照上述优先级顺序实现

3. **测试策略**：
   - 每实现一个 phase，立即测试
   - 使用小规模数据（3-5 集）测试

你希望我如何继续？
