# 本体论 + Nanobanana 集成实施计划

**日期**: 2026-03-31  
**目标**: 将本体论驱动的世界模型与 Nanobanana 图像生成集成到 AI 短剧生成系统，实现从"即兴生成"到"预制作工业化"的架构升级

---

## 执行摘要

### 核心改进

| 维度 | 旧架构 | 新架构 |
|------|--------|--------|
| **角色一致性** | text2video 随机生成 | Nanobanana 预生成角色图 → img2video 强制一致 |
| **场景稳定性** | 每次生成不同 | 场景图预制 + 时段变体锁定 |
| **分镜可控性** | 提示词黑盒 | 分镜图预览 → 人工审核 → 再生成视频 |
| **本体约束** | 无，靠 prompt 描述 | 本体模型强制约束（能力/物理/叙事规则） |
| **返工成本** | 视频生成后才发现问题 | 分镜阶段发现，成本降低 90% |

### 新流程图

```
Phase 0: 本体论构建（NEW）
  ↓
Phase 1: 合规预检（不变）
  ↓
Phase 2A: 美术设计（NEW - Nanobanana 生成角色/场景/道具图）
  ↓
Phase 2B: 分镜设计（重构 - Nanobanana 生成构图图/故事板/关键帧）
  ↓
Phase 3: 分镜审核（重构 - 从文件检查改为分镜图审核）
  ↓
Phase 4: 音色配置（不变）
  ↓
Phase 5: 视频生成（改为 img2video 模式）
```

---

## Nanobanana API 规格

### 模型选择

| 模型 | 用途 | 分辨率 | 速度 |
|------|------|--------|------|
| `gemini-3.1-flash-image-preview` | 快速迭代、故事板 | 512px-4K | 最快 |
| `gemini-3-pro-image-preview` | 高质量角色/场景设计 | 1K-4K | 慢 |
| `gemini-2.5-flash-image` | 平衡选择 | 1K-4K | 中等 |

**推荐配置**:
- **Phase 2A（美术设计）**: `gemini-3-pro-image-preview` @ 2K（高质量）
- **Phase 2B（分镜图）**: `gemini-3.1-flash-image-preview` @ 1K（快速迭代）

### 支持的参数

```json
{
  "model": "gemini-3-pro-image-preview",
  "contents": [
    {
      "role": "user",
      "parts": [
        {"text": "角色设计图，苏夜（青玉蚕形态），通体碧绿、肥嘟嘟的蚕宝宝..."}
      ]
    }
  ],
  "generation_config": {
    "response_modalities": ["IMAGE"],
    "image_config": {
      "aspect_ratio": "1:1",  // 1:1, 4:3, 16:9, 9:16 等
      "image_size": "2K"      // 512, 1K, 2K, 4K
    }
  }
}
```

**关键特性**:
- ✅ 支持 text-to-image 和 image-to-image
- ✅ 支持多轮对话式编辑（迭代优化）
- ✅ 支持最多 14 张参考图组合
- ✅ 支持 21 种宽高比
- ❌ 不支持显式 seed 参数（通过 prompt 控制一致性）
- ❌ 不支持显式 style 参数（通过 prompt 描述风格）

---

## 实施阶段

### 阶段 1: 本体论 + 美术预制作（1-2 周）

#### 1.1 本体论构建

**新增文件**:
```
config/ontology/
  ├─ world-schema.yaml          # 本体模型 Schema 定义
  └─ validation-rules.yaml      # 本体约束验证规则

.claude/agents/
  └─ ontology-builder-agent.md  # 本体构建 Agent

state/ontology/
  └─ {ep}-world-model.json      # 每集的世界模型实例
```

**ontology-builder-agent 职责**:
1. 读取 `script/{ep}.md`、`assets/characters/profiles/*.yaml`、`assets/scenes/profiles/*.yaml`
2. 提取实体（角色、场景、道具）和关系（空间、时间、社会、因果）
3. 应用本体约束（物理规则、能力限制、叙事规则）
4. 输出 `state/ontology/{ep}-world-model.json`
5. 验证逻辑一致性（例如：角色在 A 场景死亡，不能在后续 B 场景出现）

**world-model.json 结构**:
```json
{
  "world_id": "qyccan-ep01",
  "entities": {
    "苏夜": {
      "type": "character",
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
    },
    "叶红衣闺房": {
      "type": "location",
      "spatial": {"type": "indoor", "size": "small"},
      "temporal_variants": ["day", "night"],
      "lighting_rules": {
        "day": "柔和日光透过窗纱",
        "night": "烛光摇曳"
      }
    }
  },
  "relationships": [
    {
      "type": "social.契约",
      "from": "苏夜",
      "to": "叶红衣",
      "properties": {"strength": "生死相依"}
    }
  ],
  "physics": {
    "gravity": "normal",
    "magic_system": "cultivation"
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

#### 1.2 美术设计（Nanobanana 生成）

**新增文件**:
```
.claude/agents/
  └─ art-design-agent.md        # 美术设计 Agent

config/nanobanana/
  ├─ character-prompt-template.yaml  # 角色图提示词模板
  ├─ scene-prompt-template.yaml     # 场景图提示词模板
  └─ prop-prompt-template.yaml      # 道具图提示词模板

scripts/
  └─ nanobanana-caller.sh       # Nanobanana API 调用脚本
```

**art-design-agent 职责**:
1. 读取 `state/ontology/{ep}-world-model.json`
2. 读取 `assets/characters/profiles/*.yaml` 和 `assets/scenes/profiles/*.yaml`
3. 为每个角色的每个变体生成多角度参考图（front/side/back/expression）
4. 为每个场景的每个时段生成参考图（day/night/dusk/dawn）
5. 为关键道具生成参考图
6. 输出到 `assets/characters/images/`、`assets/scenes/images/`、`assets/props/images/`

**Nanobanana 提示词模板**:

```yaml
# config/nanobanana/character-prompt-template.yaml
character_design:
  base_prompt: |
    角色设计图，{character_name}，{appearance_description}，
    {pose}，白色背景，角色设计稿风格，{angle}视图，全身像，
    高清细节，无水印，无文字，纯净背景
  
  angles:
    front: "正面视图，面向镜头"
    side: "侧面视图，90度侧身"
    back: "背面视图，背对镜头"
  
  poses:
    default: "标准站姿，双手自然下垂"
    action: "动作姿态，{action_description}"
  
  expressions:
    neutral: "中性表情"
    happy: "开心表情，微笑"
    angry: "愤怒表情，皱眉"
    sad: "悲伤表情，低头"
  
  generation_config:
    model: "gemini-3-pro-image-preview"
    aspect_ratio: "1:1"
    image_size: "2K"
```

```yaml
# config/nanobanana/scene-prompt-template.yaml
scene_design:
  base_prompt: |
    场景设计图，{scene_name}，{scene_description}，
    {time_of_day}，{lighting_description}，{atmosphere}，
    电影级场景概念图，高清细节，无人物，无水印
  
  time_of_day:
    day: "白天，明亮自然光"
    night: "夜晚，{night_lighting}"
    dusk: "黄昏，暖色调夕阳"
    dawn: "清晨，柔和晨光"
  
  night_lighting:
    candle: "烛光照明，温暖昏黄"
    moonlight: "月光透窗，冷色调"
    neon: "霓虹灯光，五彩斑斓"
  
  generation_config:
    model: "gemini-3-pro-image-preview"
    aspect_ratio: "16:9"
    image_size: "2K"
```

**nanobanana-caller.sh 脚本**:

```bash
#!/bin/bash
# scripts/nanobanana-caller.sh

set -euo pipefail

TUZI_API_KEY="${TUZI_API_KEY:-}"
NANOBANANA_MODEL="${NANOBANANA_MODEL:-gemini-3-pro-image-preview}"
NANOBANANA_API_URL="https://generativelanguage.googleapis.com/v1beta/models/${NANOBANANA_MODEL}:generateContent"

generate_image() {
    local prompt="$1"
    local aspect_ratio="${2:-1:1}"
    local image_size="${3:-2K}"
    local output_path="$4"
    
    local payload=$(cat <<EOF
{
  "contents": [{
    "role": "user",
    "parts": [{"text": "${prompt}"}]
  }],
  "generation_config": {
    "response_modalities": ["IMAGE"],
    "image_config": {
      "aspect_ratio": "${aspect_ratio}",
      "image_size": "${image_size}"
    }
  }
}
EOF
)
    
    local response=$(curl -s -X POST "${NANOBANANA_API_URL}?key=${TUZI_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "${payload}")
    
    # 提取 base64 图像并保存
    echo "${response}" | jq -r '.candidates[0].content.parts[0].inline_data.data' | base64 -d > "${output_path}"
    
    echo "✓ 图像已保存: ${output_path}"
}

case "$1" in
    generate)
        generate_image "$2" "$3" "$4" "$5"
        ;;
    *)
        echo "用法: $0 generate <prompt> <aspect_ratio> <image_size> <output_path>"
        exit 1
        ;;
esac
```

#### 1.3 验证任务

- [ ] 为 `qyccan-ep01` 生成完整本体模型
- [ ] 为「苏夜」的 4 个变体生成角色图（default, snake_green, snake_large, python_black）
- [ ] 为「叶红衣闺房」生成 day/night 两个场景图
- [ ] 验证图像质量和一致性

---

### 阶段 2: 分镜预览（2-3 周）

#### 2.1 重构 Visual Agent → Storyboard Agent

**修改文件**:
```
.claude/agents/
  └─ visual-agent.md → storyboard-agent.md  # 重命名并重构

outputs/{ep}/
  └─ storyboard/                # 新增分镜图目录
      ├─ shot-01-composition.png      # A: 静态构图（img2video 首帧）
      ├─ shot-01-storyboard.png       # B: 故事板（4格漫画）
      └─ shot-01-keyframes/           # C: 关键帧序列
          ├─ start.png
          └─ end.png
```

**storyboard-agent 新职责**:
1. 读取 `outputs/{ep}/render-script.md` 和 `state/ontology/{ep}-world-model.json`
2. 基于本体约束拆分镜次
3. 为每个镜次调用 Nanobanana 生成 3 类图：
   - **A: 静态构图参考** - img2video 首帧
   - **B: 故事板** - 4格漫画式预览
   - **C: 关键帧序列** - 首尾帧（可选）
4. 生成 Seedance img2video 提示词
5. 输出 `visual-direction.yaml` 和 `visual-direction.md`

**visual-direction.yaml 新增字段**:

```yaml
shots:
  - shot_id: "ep01-shot-01"
    duration: 8
    
    # 本体论约束
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
    
    # Nanobanana 生成的分镜图
    storyboard_assets:
      composition: "outputs/ep01/storyboard/shot-01-composition.png"
      storyboard: "outputs/ep01/storyboard/shot-01-storyboard.png"
      keyframes:
        start: "outputs/ep01/storyboard/shot-01-keyframes/start.png"
        end: "outputs/ep01/storyboard/shot-01-keyframes/end.png"
    
    # Seedance 2.0 参数
    generation_mode: "img2video"
    reference_image: "outputs/ep01/storyboard/shot-01-composition.png"
    prompt: |
      【出镜角色-场景】
      角色：@图片1 作为<苏夜（青玉蚕形态）>
      场景：<叶红衣闺房-夜>
      [画面]：[苏夜]从床边爬向窗台，肉乎乎的小短腿一步步挪动。
      [后景]：古风闺房，烛光摇曳，窗纱轻飘。
      
      画面风格: 古风玄幻，温馨氛围，柔和光影。
      镜头1：中景固定镜头，[苏夜]缓慢爬行，复眼视角呈现周围环境。
      
      画面风格: 古风玄幻，温馨氛围；搭配轻柔环境音；禁止出现字幕、对话框、背景音乐
```

**Nanobanana 分镜图生成提示词**:

```python
# A: 静态构图参考（img2video 首帧）
composition_prompt = f"""
电影分镜构图图，{shot.scene_name}，{shot.time_of_day}，
{shot.camera_type}，{shot.subject}位于{shot.position}，
{shot.lighting}，电影感构图，高清，无水印，无文字
"""

# B: 故事板（4格漫画）
storyboard_prompt = f"""
故事板，4格分镜，{shot.scene_name}，
第1格：{shot.action_start}
第2格：{shot.action_mid1}
第3格：{shot.action_mid2}
第4格：{shot.action_end}
黑白线稿，分镜脚本风格，标注镜头运动箭头，无水印
"""

# C: 关键帧序列（首尾帧）
start_frame_prompt = f"""
关键帧，{shot.scene_name}，{shot.time_of_day}，
{shot.subject}，动作开始状态：{shot.action_start}，
{shot.camera_type}，电影感，高清，无水印
"""

end_frame_prompt = f"""
关键帧，{shot.scene_name}，{shot.time_of_day}，
{shot.subject}，动作结束状态：{shot.action_end}，
{shot.camera_type}，电影感，高清，无水印
"""
```

#### 2.2 重构 Phase 3: 分镜审核

**修改文件**:
```
.claude/agents/
  └─ design-agent.md → storyboard-review-agent.md  # 重命名并重构
```

**storyboard-review-agent 新职责**:
1. 读取 `outputs/{ep}/storyboard/` 中的所有分镜图
2. 生成人工审核报告（包含图片预览）
3. 推送飞书审核卡片（视觉类审核，Web 页面）
4. 等待审核结果（通过/重做/终止）

**审核报告格式**:

```markdown
# 分镜审核 - ep01

## Shot 01 - 叶红衣闺房

### 构图图
![](outputs/ep01/storyboard/shot-01-composition.png)

### 故事板
![](outputs/ep01/storyboard/shot-01-storyboard.png)

### 关键帧
| 开始帧 | 结束帧 |
|--------|--------|
| ![](outputs/ep01/storyboard/shot-01-keyframes/start.png) | ![](outputs/ep01/storyboard/shot-01-keyframes/end.png) |

### 本体约束检查
- [x] 角色外貌符合本体设定（苏夜为青玉蚕，拇指大小）
- [x] 场景光线符合时段（夜晚，烛光）
- [x] 构图符合镜头语言（中景，固定镜头）
- [x] 动作连贯性（从爬行到抬头）

### 审核结果
- [ ] 通过
- [ ] 重做（附原因）
- [ ] 终止

---

## Shot 02 - ...
```

#### 2.3 验证任务

- [ ] 为 `qyccan-ep01` 的前 3 个镜次生成完整分镜图（A/B/C 三类）
- [ ] 验证分镜图质量和叙事连贯性
- [ ] 测试飞书审核流程

---

### 阶段 3: img2video 切换（1 周）

#### 3.1 修改 gen-worker

**修改文件**:
```
.claude/agents/
  └─ gen-worker.md  # 添加 img2video 模式支持
```

**新逻辑**:

```python
# 旧逻辑：text2video
payload = {
    "model": "doubao-seedance-1-5-pro",
    "content": [{"type": "text", "text": prompt}]
}

# 新逻辑：img2video（使用 Nanobanana 生成的构图图）
payload = {
    "model": "doubao-seedance-1-5-pro",
    "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": shot.reference_image}  # 首帧
    ]
}

# 如果有尾帧（关键帧序列模式）
if shot.keyframes.end:
    payload["content"].append({
        "type": "image_url",
        "image_url": shot.keyframes.end
    })
```

#### 3.2 A/B 测试

对比 text2video vs img2video 质量：

| 维度 | text2video | img2video（首帧） | img2video（首尾帧） |
|------|-----------|------------------|-------------------|
| 角色一致性 | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 场景稳定性 | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 动作自然度 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 生成速度 | 快 | 中 | 慢 |

#### 3.3 验证任务

- [ ] 为 `qyccan-ep01` 的前 3 个镜次生成视频（img2video 模式）
- [ ] 对比 text2video vs img2video 质量
- [ ] 测试首帧模式 vs 首尾帧模式

---

## 新增 Skills

### ~build-ontology

```bash
~build-ontology ep01  # 为单集构建本体
~build-ontology --all # 为所有剧本构建本体
```

### ~art-design

```bash
~art-design           # 为所有角色/场景生成美术资产
~art-design --character 苏夜  # 只生成指定角色
~art-design --scene 叶红衣闺房  # 只生成指定场景
```

### ~storyboard

```bash
~storyboard ep01      # 为单集生成分镜图
~storyboard --mode composition  # 只生成构图图（A）
~storyboard --mode storyboard   # 只生成故事板（B）
~storyboard --mode keyframes    # 只生成关键帧（C）
```

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

### config/api-endpoints.yaml

```yaml
# 新增 Nanobanana API 配置
nanobanana:
  base_url: "https://generativelanguage.googleapis.com/v1beta"
  models:
    fast: "gemini-3.1-flash-image-preview"
    balanced: "gemini-2.5-flash-image"
    quality: "gemini-3-pro-image-preview"
  default_model: "gemini-3-pro-image-preview"
  default_aspect_ratio: "1:1"
  default_image_size: "2K"
```

---

## 环境变量

```bash
# 现有
export ARK_API_KEY="..."        # Seedance 视频生成
export TUZI_API_KEY="..."       # 兔子 API Key（已有）

# 新增（如果 TUZI_API_KEY 不支持 Nanobanana，则需要单独配置）
export NANOBANANA_API_KEY="..."  # Nanobanana 图像生成（可选，默认使用 TUZI_API_KEY）
```

---

## 成本估算

### Nanobanana 成本（基于兔子 API 价格）

| 任务 | 模型 | 分辨率 | 数量 | 单价 | 小计 |
|------|------|--------|------|------|------|
| 角色设计图 | Pro | 2K | 10角色 × 4变体 × 4角度 = 160 | $0.24 | $38.4 |
| 场景设计图 | Pro | 2K | 15场景 × 2时段 = 30 | $0.24 | $7.2 |
| 分镜构图图 | Flash | 1K | 60集 × 12镜次 = 720 | $0.05 | $36 |
| 分镜故事板 | Flash | 1K | 720 | $0.05 | $36 |
| 关键帧（可选） | Flash | 1K | 720 × 2 = 1440 | $0.05 | $72 |
| **总计** | | | | | **$189.6** |

**对比 Seedance 成本**（假设 60 集 × 12 镜次 = 720 个视频）:
- Seedance 1.5 Pro: 720 × $0.5 = **$360**
- **总成本**: $189.6 (Nanobanana) + $360 (Seedance) = **$549.6**

**ROI 分析**:
- 旧流程返工率 30% → 额外成本 $108
- 新流程返工率 5% → 额外成本 $18
- **净节省**: $108 - $18 - $189.6 = **-$99.6**（首次投入）
- **长期收益**: 质量提升 + 返工减少 + 可复用资产

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Nanobanana 生成质量不稳定 | 高 | 多轮迭代 + 人工审核 + 保留 text2video 备选 |
| img2video 动作不自然 | 中 | 测试首尾帧模式 + 调整提示词 |
| 本体约束过于严格 | 中 | 分级约束（硬约束 vs 软约束） |
| 成本超预算 | 低 | 使用 Flash 模型 + 批量生成优化 |

---

## 下一步行动

**立即开始**:
1. [ ] 创建 `config/ontology/world-schema.yaml`
2. [ ] 实现 `ontology-builder-agent.md`
3. [ ] 实现 `scripts/nanobanana-caller.sh`
4. [ ] 为 `qyccan-ep01` 生成本体模型（验证）

**本周完成**:
5. [ ] 实现 `art-design-agent.md`
6. [ ] 为「苏夜」生成 4 个变体的角色图
7. [ ] 为「叶红衣闺房」生成 day/night 场景图

**下周完成**:
8. [ ] 重构 `visual-agent.md` → `storyboard-agent.md`
9. [ ] 为 ep01 前 3 个镜次生成分镜图
10. [ ] 测试 img2video 模式

---

## 参考资料

- [Google Gemini Image Generation API](https://ai.google.dev/gemini-api/docs/image-generation)
- [Nano Banana API Complete Guide](https://evolink.ai/blog/how-to-use-nano-banana-2-api-complete-tutorial)
- [Nano Banana Pro API Documentation](https://fastgptplus.com/en/posts/nano-banana-pro-api)
- [Ultimate Prompting Guide for Nano Banana](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana)

---

**计划作者**: Claude Code  
**审核状态**: 待审核  
**预计完成时间**: 4-6 周
