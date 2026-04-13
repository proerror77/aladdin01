---
name: ontology-builder-agent
description: 本体论构建 agent。从剧本和角色档案构建世界本体模型，提取实体、关系和约束。
tools:
  - Read
  - Write
  - Bash
write_scope:
  - "projects/{project}/state/ontology/{ep}-world-model.json"
  - "projects/{project}/state/{ep}-phase0.json"
  - "projects/{project}/state/signals/"
read_scope:
  - "projects/{project}/script/"
  - "projects/{project}/assets/characters/profiles/"
  - "projects/{project}/assets/scenes/profiles/"
---

# ontology-builder-agent — 本体论构建

## 职责

从剧本和角色/场景档案构建世界本体模型（World Model），为后续的状态管理和 shot packet 编译提供基础。

## 输入

- `projects/{project}/script/{ep}.md` — 剧本
- `projects/{project}/assets/characters/profiles/*.yaml` — 角色档案
- `projects/{project}/assets/scenes/profiles/*.yaml` — 场景档案
- `config/ontology/world-model-schema.yaml` — Schema 定义

## 输出

- `projects/{project}/state/ontology/{ep}-world-model.json` — 世界本体模型

## 执行流程

### Step 1: 读取输入

读取剧本和所有相关档案：
```bash
#!/usr/bin/env bash
set -euo pipefail

ep="$1"
session_id="$2"
trace_file="$3"

# 检查输入文件
if [[ ! -f "projects/{project}/script/${ep}.md" ]]; then
  echo "ERROR: 剧本文件不存在: projects/{project}/script/${ep}.md" >&2
  exit 1
fi

# 读取剧本
script_content=$(cat "projects/{project}/script/${ep}.md")

# 读取所有角色档案
character_files=$(find projects/{project}/assets/characters/profiles -name "*.yaml" -type f 2>/dev/null || echo "")
character_count=$(echo "$character_files" | grep -c . || echo "0")

# 读取所有场景档案
scene_files=$(find projects/{project}/assets/scenes/profiles -name "*.yaml" -type f 2>/dev/null || echo "")
scene_count=$(echo "$scene_files" | grep -c . || echo "0")

# 记录 trace
./scripts/trace.sh "$session_id" "$trace_file" "read_inputs" \
  "{\"script\": \"projects/{project}/script/${ep}.md\", \"character_count\": ${character_count}, \"scene_count\": ${scene_count}}"

echo "✓ 读取输入: 剧本 1 个, 角色档案 ${character_count} 个, 场景档案 ${scene_count} 个"
```

### Step 2: 提取角色实体

使用 LLM 从角色档案中提取结构化信息（v2.2：新增 visual_signature、camera_preference，abilities 改为 skill ID 列表）：

```bash
# 构造 LLM prompt
cat > /tmp/extract_characters_prompt.txt <<'EOF'
从以下角色档案中提取结构化实体信息，输出 JSON 数组格式。

要求：
1. 每个角色一个对象
2. 从 tier 字段读取层级（protagonist/supporting/minor）
3. 从 variants 字段读取变体信息，current_variant 默认为 "default"
4. 从 appearance 字段提取物理属性
5. 从 cultivation_level 或 abilities 字段提取能力名称列表（abilities 字段，后续 Step 2.5 会转为 skill 实体）
6. 从 personality 和 background 推断约束
7. 从 appearance 提取 visual_signature（标志性视觉元素，用于跨 shot 一致性）
8. 根据角色体型/形态推断 camera_preference（每个变体适合的景别）

输出格式：
[
  {
    "id": "角色拼音或英文ID",
    "name": "角色中文名",
    "tier": "protagonist/supporting/minor",
    "current_variant": "default",
    "physical": {
      "species": "human/demon/spirit/beast",
      "form": "形态描述",
      "size": "尺寸描述"
    },
    "abilities": ["能力名1", "能力名2"],
    "constraints": ["约束1", "约束2"],
    "visual_signature": {
      "color_palette": ["主色1", "主色2"],
      "distinctive_features": ["标志性特征1", "标志性特征2"],
      "silhouette_keywords": "剪影关键词（用于 Seedance prompt）",
      "must_preserve_across_shots": ["跨 shot 必须保持的特征1", "特征2"]
    },
    "camera_preference": {
      "{variant_id}": {
        "preferred_shots": ["大特写", "特写"],
        "reason": "体型极小，中景以上看不清",
        "avoid": ["大远景"],
        "power_moment_shot": "仰拍特写（技能释放时）"
      }
    }
  }
]

角色档案内容：
EOF

# 拼接所有角色档案
for f in $character_files; do
  echo "---" >> /tmp/extract_characters_prompt.txt
  cat "$f" >> /tmp/extract_characters_prompt.txt
done

# 调用 Tuzi LLM
cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [
    {
      "role": "user",
      "content": $(jq -Rs . /tmp/extract_characters_prompt.txt)
    }
  ],
  "response_format": { "type": "json_object" }
}
EOF

characters_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')

# 记录 trace
character_count=$(echo "$characters_json" | jq 'length')
./scripts/trace.sh "$session_id" "$trace_file" "extract_character_entities" \
  "{\"count\": ${character_count}}"

echo "✓ 提取角色实体: ${character_count} 个"
```

### Step 2.5: 提取技能实体（v2.2 新增）

从角色档案的 abilities 字段和剧本中的技能使用场景，构建独立的 skills 实体：

```bash
cat > /tmp/extract_skills_prompt.txt <<EOF
从以下角色档案和剧本中提取所有技能/能力，构建独立的 skills 实体列表，输出 JSON 数组格式。

要求：
1. 每个技能一个对象，不同角色的同名技能分开
2. 从角色档案的 abilities 字段获取技能名称
3. 从剧本中找到技能使用场景，推断触发条件、代价、约束
4. 如果技能有明显的视觉效果，关联到 vfx_id（格式：{技能拼音}_vfx）
5. 根据剧本中的技能使用情境推断 scene_restrictions

输出格式：
[
  {
    "id": "技能拼音_v1",
    "name": "技能中文名",
    "owner": "角色ID",
    "unlock_variant": "解锁该技能所需的变体ID（如无则null）",
    "vfx_id": "关联vfx实体ID（如无视觉效果则null）",
    "trigger": {
      "type": "active/passive/conditional",
      "condition": "触发条件描述",
      "cooldown_narrative": "叙事层面的冷却描述（如有）"
    },
    "cost": {
      "resource": "消耗资源（灵力/体力/null）",
      "side_effect": "使用后的副作用描述",
      "visual_side_effect": "副作用的视觉表现（下一shot需体现）"
    },
    "level": 1,
    "constraints": ["约束1", "约束2"],
    "scene_restrictions": ["不能在X场景使用"]
  }
]

角色档案：
$(for f in $character_files; do cat "$f"; echo "---"; done)

剧本内容：
$(cat "script/${ep}.md")
EOF

cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [{"role": "user", "content": $(jq -Rs . /tmp/extract_skills_prompt.txt)}],
  "response_format": { "type": "json_object" }
}
EOF

skills_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')
skill_count=$(echo "$skills_json" | jq 'length')
./scripts/trace.sh "$session_id" "$trace_file" "extract_skill_entities" \
  "{\"count\": ${skill_count}}"

echo "✓ 提取技能实体: ${skill_count} 个"
```

### Step 3: 提取场景实体

使用 LLM 从场景档案中提取结构化信息（v2.2：新增 functional 字段）：

```bash
# 构造 LLM prompt
cat > /tmp/extract_locations_prompt.txt <<'EOF'
从以下场景档案中提取结构化实体信息，输出 JSON 数组格式。

要求：
1. 每个场景一个对象
2. 从 description 字段提取空间属性
3. 从 lighting 字段推断时间变体
4. 推断 indoor/outdoor 类型
5. 从场景描述和剧本中推断 functional 字段（行为约束 + 视觉标志物）

输出格式：
[
  {
    "id": "场景拼音或英文ID",
    "name": "场景中文名",
    "spatial": {
      "type": "indoor/outdoor/mixed",
      "size": "small/medium/large",
      "layout": "布局描述"
    },
    "temporal_variants": ["day", "night", "dusk", "dawn"],
    "lighting_rules": {
      "day": "日光描述",
      "night": "夜间描述"
    },
    "atmosphere": "氛围描述",
    "functional": {
      "affordances": ["允许的行为1", "允许的行为2"],
      "forbidden_actions": ["禁止的行为1（原因）"],
      "hazards": [
        {
          "type": "environmental/creature/trap",
          "description": "危险描述",
          "visual_cue": "角色受到影响时的视觉表现",
          "trigger": "触发条件（可选）"
        }
      ],
      "visual_landmarks": [
        {
          "name": "标志物名称",
          "description": "详细描述",
          "seedance_keywords": "直接注入 Seedance prompt 的关键词"
        }
      ],
      "scene_states": [
        {
          "state": "normal",
          "description": "正常状态描述"
        },
        {
          "state": "状态名",
          "description": "该状态的视觉描述",
          "trigger": "触发条件（ep_shot 格式，如 ep03-shot-05）"
        }
      ]
    }
  }
]

场景档案内容：
EOF

# 拼接所有场景档案
for f in $scene_files; do
  echo "---" >> /tmp/extract_locations_prompt.txt
  cat "$f" >> /tmp/extract_locations_prompt.txt
done

# 调用 Tuzi LLM
cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [
    {
      "role": "user",
      "content": $(jq -Rs . /tmp/extract_locations_prompt.txt)
    }
  ],
  "response_format": { "type": "json_object" }
}
EOF

locations_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')

# 记录 trace
location_count=$(echo "$locations_json" | jq 'length')
./scripts/trace.sh "$session_id" "$trace_file" "extract_location_entities" \
  "{\"count\": ${location_count}}"

echo "✓ 提取场景实体: ${location_count} 个"
```

### Step 3.5: 提取场景功能性（v2.2 新增）

场景档案通常只有外观描述，需要结合剧本推断场景的行为约束和视觉标志物。此步骤补充 Step 3 中 functional 字段不完整的部分：

```bash
cat > /tmp/enrich_locations_prompt.txt <<EOF
根据以下剧本，补充场景的功能性信息（functional 字段）。

对于每个场景，从剧本中找到：
1. 角色在该场景中实际做了什么（affordances）
2. 有什么行为导致了负面后果（forbidden_actions）
3. 场景中有什么危险（hazards）
4. 场景中有哪些标志性视觉元素被反复提及（visual_landmarks）
5. 场景在剧情中是否发生了状态变化（scene_states）

输出 JSON 对象，key 为场景 ID，value 为 functional 字段的补充内容：
{
  "场景ID": {
    "affordances": [...],
    "forbidden_actions": [...],
    "hazards": [...],
    "visual_landmarks": [...],
    "scene_states": [...]
  }
}

已提取的场景列表：
$(echo "$locations_json" | jq '[.[] | {id, name}]')

剧本内容：
$(cat "script/${ep}.md")
EOF

cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [{"role": "user", "content": $(jq -Rs . /tmp/enrich_locations_prompt.txt)}],
  "response_format": { "type": "json_object" }
}
EOF

location_functional_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')

# 将 functional 字段合并回 locations_json
locations_json=$(echo "$locations_json" | jq --argjson functional "$location_functional_json" '
  map(. + {functional: ($functional[.id] // {})})
')

./scripts/trace.sh "$session_id" "$trace_file" "enrich_location_functional" \
  "{\"enriched_count\": $(echo "$location_functional_json" | jq 'keys | length')}"

echo "✓ 场景功能性补充完成"
```

### Step 4: 提取道具实体

使用 LLM 从剧本中提取关键道具：

```bash
# 构造 LLM prompt
cat > /tmp/extract_props_prompt.txt <<EOF
从以下剧本中提取所有关键道具（对剧情有重要影响的物品），输出 JSON 数组格式。

要求：
1. 只提取关键道具，忽略背景道具
2. 识别道具的所有者（角色名）
3. 推断道具的当前状态

输出格式：
[
  {
    "id": "道具拼音或英文ID",
    "name": "道具中文名",
    "description": "描述",
    "owner": "角色名",
    "condition": "intact/damaged/destroyed",
    "significance": "剧情意义"
  }
]

剧本内容：
$(cat "script/${ep}.md")
EOF

# 调用 Tuzi LLM
cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [
    {
      "role": "user",
      "content": $(jq -Rs . /tmp/extract_props_prompt.txt)
    }
  ],
  "response_format": { "type": "json_object" }
}
EOF

props_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')

# 记录 trace
prop_count=$(echo "$props_json" | jq 'length')
./scripts/trace.sh "$session_id" "$trace_file" "extract_prop_entities" \
  "{\"count\": ${prop_count}}"

echo "✓ 提取道具实体: ${prop_count} 个"
```

### Step 5: 提取关系

使用 LLM 从剧本和档案中提取实体间关系：

```bash
# 构造 LLM prompt
cat > /tmp/extract_relationships_prompt.txt <<EOF
从以下剧本和角色档案中提取实体之间的关系，输出 JSON 数组格式。

关系类型：
- social: 契约、师徒、敌对、亲属、朋友
- spatial: 包含、邻近、可见、隔离
- causal: 导致、阻止、需要、依赖
- temporal: 之前、之后、同时

输出格式：
[
  {
    "type": "social/spatial/causal/temporal",
    "from": "实体1",
    "to": "实体2",
    "relation": "具体关系",
    "properties": {
      "strength": "weak/medium/strong",
      "established_at": "场景ID或时间点"
    }
  }
]

剧本内容：
$(cat "script/${ep}.md")

角色档案：
$(for f in $character_files; do cat "$f"; echo "---"; done)
EOF

# 调用 Tuzi LLM
cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [
    {
      "role": "user",
      "content": $(jq -Rs . /tmp/extract_relationships_prompt.txt)
    }
  ],
  "response_format": { "type": "json_object" }
}
EOF

relationships_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')

# 记录 trace
relationship_count=$(echo "$relationships_json" | jq 'length')
./scripts/trace.sh "$session_id" "$trace_file" "extract_relationships" \
  "{\"count\": ${relationship_count}}"

echo "✓ 提取关系: ${relationship_count} 个"
```

### Step 6: 提取物理规则

使用 LLM 从世界观设定中推断物理规则：

```bash
# 构造 LLM prompt
cat > /tmp/extract_physics_prompt.txt <<EOF
从以下剧本和角色档案中推断世界的物理规则，输出 JSON 格式。

要求：
1. 判断重力类型（normal/low/high/none）
2. 识别魔法系统（cultivation/elemental/none）
3. 判断力量等级是否严格（strict/loose）

输出格式：
{
  "gravity": "normal/low/high/none",
  "magic_system": "cultivation/elemental/none",
  "power_scaling": "strict/loose",
  "notes": "补充说明"
}

剧本内容：
$(cat "script/${ep}.md")

角色档案：
$(for f in $character_files; do cat "$f"; echo "---"; done)
EOF

# 调用 Tuzi LLM
cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [
    {
      "role": "user",
      "content": $(jq -Rs . /tmp/extract_physics_prompt.txt)
    }
  ],
  "response_format": { "type": "json_object" }
}
EOF

physics_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')

# 记录 trace
magic_system=$(echo "$physics_json" | jq -r '.magic_system')
./scripts/trace.sh "$session_id" "$trace_file" "extract_physics" \
  "{\"magic_system\": \"${magic_system}\"}"

echo "✓ 提取物理规则: magic_system=${magic_system}"
```

### Step 7: 提取叙事约束

使用 LLM 从剧本中提取叙事约束：

```bash
# 构造 LLM prompt
cat > /tmp/extract_narrative_prompt.txt <<EOF
从以下剧本中提取叙事约束（角色进化、能力解锁、世界规则），输出 JSON 格式。

要求：
1. 识别角色进化时间线
2. 识别能力解锁条件
3. 提取世界规则

输出格式：
{
  "character_evolution": [
    {
      "character": "角色名",
      "from": "状态1",
      "to": "状态2",
      "trigger": "触发条件"
    }
  ],
  "ability_unlocks": [
    {
      "character": "角色名",
      "ability": "能力名",
      "condition": "解锁条件"
    }
  ],
  "world_rules": ["规则1", "规则2"]
}

剧本内容：
$(cat "script/${ep}.md")

角色档案：
$(for f in $character_files; do cat "$f"; echo "---"; done)
EOF

# 调用 Tuzi LLM
cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [
    {
      "role": "user",
      "content": $(jq -Rs . /tmp/extract_narrative_prompt.txt)
    }
  ],
  "response_format": { "type": "json_object" }
}
EOF

narrative_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')

# 记录 trace
evolution_count=$(echo "$narrative_json" | jq '.character_evolution | length')
./scripts/trace.sh "$session_id" "$trace_file" "extract_narrative_constraints" \
  "{\"evolution_count\": ${evolution_count}}"

echo "✓ 提取叙事约束: ${evolution_count} 个进化时间线"
```

### Step 7.5: 提取情绪弧线（v2.2 新增）

从剧本的情节发展中提取每个主要角色的情绪弧线，供 visual-agent 选择景别和 qa-agent 检查情绪跳变：

```bash
cat > /tmp/extract_emotional_arcs_prompt.txt <<EOF
从以下剧本中提取主要角色的情绪弧线，输出 JSON 格式。

要求：
1. 只提取 protagonist 和 supporting 层级的角色
2. 按剧情发展划分情绪阶段（对应 shot 范围）
3. intensity 表示情绪强度（0.0-1.0），影响 visual-agent 的景别选择：
   - 0.8+ → 特写/大特写
   - 0.5-0.8 → 近景/中景
   - 0.0-0.5 → 中景/全景
4. forbidden_transitions 记录不合理的情绪跳变（用于 qa-agent 检查）

输出格式：
{
  "emotional_arcs": [
    {
      "character": "角色ID",
      "episode": "${ep}",
      "arc": [
        {
          "shot_range": "shot-01~shot-02",
          "emotion": "情绪标签（英文，如 confused_panicked / curious / triumphant）",
          "intensity": 0.8,
          "description": "该阶段情绪的简短描述"
        }
      ],
      "forbidden_transitions": [
        {
          "from": "情绪标签",
          "to": "情绪标签",
          "reason": "为什么这个跳变不合理"
        }
      ]
    }
  ]
}

剧本内容：
$(cat "script/${ep}.md")

主要角色列表：
$(echo "$characters_json" | jq '[.[] | select(.tier == "protagonist" or .tier == "supporting") | {id, name}]')
EOF

cat > /tmp/tuzi_payload.json <<EOF
{
  "model": "nano-banana-vip",
  "messages": [{"role": "user", "content": $(jq -Rs . /tmp/extract_emotional_arcs_prompt.txt)}],
  "response_format": { "type": "json_object" }
}
EOF

emotional_arcs_json=$(./scripts/api-caller.sh tuzi chat /tmp/tuzi_payload.json | jq -r '.choices[0].message.content')
arc_count=$(echo "$emotional_arcs_json" | jq '.emotional_arcs | length')

./scripts/trace.sh "$session_id" "$trace_file" "extract_emotional_arcs" \
  "{\"arc_count\": ${arc_count}}"

echo "✓ 提取情绪弧线: ${arc_count} 个角色"
```

### Step 8: 验证逻辑一致性

检查实体和关系的逻辑一致性：

```bash
# 验证关系中的实体是否存在
warning_count=0

echo "$relationships_json" | jq -c '.[]' | while read -r rel; do
  from=$(echo "$rel" | jq -r '.from')
  to=$(echo "$rel" | jq -r '.to')
  
  # 检查 from 实体是否存在
  if ! echo "$characters_json" | jq -e ".[] | select(.name == \"$from\")" > /dev/null 2>&1 && \
     ! echo "$locations_json" | jq -e ".[] | select(.name == \"$from\")" > /dev/null 2>&1 && \
     ! echo "$props_json" | jq -e ".[] | select(.name == \"$from\")" > /dev/null 2>&1; then
    echo "⚠️ 关系验证失败：实体 $from 不存在" >&2
    warning_count=$((warning_count + 1))
  fi
  
  # 检查 to 实体是否存在
  if ! echo "$characters_json" | jq -e ".[] | select(.name == \"$to\")" > /dev/null 2>&1 && \
     ! echo "$locations_json" | jq -e ".[] | select(.name == \"$to\")" > /dev/null 2>&1 && \
     ! echo "$props_json" | jq -e ".[] | select(.name == \"$to\")" > /dev/null 2>&1; then
    echo "⚠️ 关系验证失败：实体 $to 不存在" >&2
    warning_count=$((warning_count + 1))
  fi
done

# 记录 trace
./scripts/trace.sh "$session_id" "$trace_file" "validate_consistency" \
  "{\"status\": \"passed\", \"warnings\": ${warning_count}}"

if [[ $warning_count -gt 0 ]]; then
  echo "⚠️ 验证完成，发现 ${warning_count} 个警告"
else
  echo "✓ 验证完成，无警告"
fi
```

### Step 9: 组装并写入 world-model.json

组装完整的世界模型并写入文件：

```bash
# 获取当前时间戳
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")


# 组装 world-model.json（v2.2：新增 skills + emotional_arcs）
cat > /tmp/world_model.json <<EOF
{
  "world_id": "aladdin01-${ep}",
  "schema_version": "2.2",
  "episode": "${ep}",
  "created_at": "${timestamp}",
  "entities": {
    "characters": ${characters_json},
    "locations": ${locations_json},
    "props": ${props_json},
    "skills": ${skills_json}
  },
  "relationships": ${relationships_json},
  "physics": ${physics_json},
  "narrative_constraints": $(echo "$narrative_json" | jq ". + {\"emotional_arcs\": $(echo "$emotional_arcs_json" | jq '.emotional_arcs')}")
}
EOF

# 创建输出目录
mkdir -p state/ontology

# 写入文件
cat /tmp/world_model.json | jq '.' > "projects/{project}/state/ontology/${ep}-world-model.json"

# 计算实体总数（v2.2：包含 skills）
entity_count=$(($(echo "$characters_json" | jq 'length') + $(echo "$locations_json" | jq 'length') + $(echo "$props_json" | jq 'length') + $(echo "$skills_json" | jq 'length')))

# 记录 trace
./scripts/trace.sh "$session_id" "$trace_file" "write_world_model" \
  "{\"output\": \"projects/{project}/state/ontology/${ep}-world-model.json\", \"entity_count\": ${entity_count}}"

echo "✓ 世界模型已写入: projects/{project}/state/ontology/${ep}-world-model.json"
echo "  - 实体总数: ${entity_count}"
echo "  - 关系总数: ${relationship_count}"
```

### Step 10: 写入 LanceDB 向量库

world-model.json 写入完成后，立即将实体和关系嵌入向量库：

```bash
# 检查 LanceDB 是否可用
if python3 -c "import lancedb" 2>/dev/null; then
    echo "写入 LanceDB 向量库..."

    # 确保数据库已初始化
    python3 scripts/vectordb-manager.py --project "{project}" init 2>/dev/null || true

    # 写入世界模型（实体 + 关系）
    python3 scripts/vectordb-manager.py --project "{project}" upsert-world-model "projects/{project}/state/ontology/${ep}-world-model.json"

    # 顺带索引现有资产（幂等，已存在的不重复写入）
    if [[ -d "assets/" ]]; then
        python3 scripts/vectordb-manager.py --project "{project}" index-assets assets/
    fi

    # 记录 trace
    ./scripts/trace.sh "$session_id" "$trace_file" "write_vectordb" \
      "{\"db\": \"state/vectordb/lancedb\", \"episode\": \"${ep}\"}"

    echo "✓ LanceDB 写入完成"
else
    echo "⚠️ lancedb 未安装，跳过向量库写入（建议：pip3 install lancedb）"
fi
```

**说明**：
- LanceDB 是可选功能，未安装时自动跳过，不影响主流程
- 向量库写入完成后，memory-agent 会优先使用语义检索
- 安装命令：`pip3 install lancedb sentence-transformers pyarrow`
  - `sentence-transformers` 提供本地多语言 embedding（无需 API Key）
  - 未安装时降级为哈希向量（可运行但语义质量低）

## 完成后

向 team-lead 发送消息：`ontology-builder-agent 完成，world-model 已生成，实体数：{entity_count}，关系数：{relationship_count}`

写入独立状态文件 `projects/{project}/state/{ep}-phase0.json`：
```bash
cat > "state/${ep}-phase0.json" <<EOF
{
  "episode": "${ep}",
  "phase": 0,
  "status": "completed",
  "started_at": "${start_time}",
  "completed_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "data": {
    "entities_count": {
      "characters": $(echo "$characters_json" | jq 'length'),
      "locations": $(echo "$locations_json" | jq 'length'),
      "props": $(echo "$props_json" | jq 'length')
    },
    "relationships_count": ${relationship_count},
    "warnings": ${warning_count}
  }
}
EOF
```

## 错误处理

- 剧本文件不存在 → 报错退出
- 角色/场景档案为空 → 警告但继续（从剧本中提取）
- LLM 返回格式错误 → 重试 3 次，失败则报错
- 逻辑一致性验证失败 → 记录警告，不阻断流程

## 完整脚本示例

```bash
#!/usr/bin/env bash
set -euo pipefail

ep="$1"
session_id="$2"
trace_file="$3"
start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Step 1: 读取输入
# ... (见上文)

# Step 2: 提取角色实体
# ... (见上文)

# Step 3: 提取场景实体
# ... (见上文)

# Step 4: 提取道具实体
# ... (见上文)

# Step 5: 提取关系
# ... (见上文)

# Step 6: 提取物理规则
# ... (见上文)

# Step 7: 提取叙事约束
# ... (见上文)

# Step 8: 验证逻辑一致性
# ... (见上文)

# Step 9: 组装并写入 world-model.json
# ... (见上文)

# 写入状态文件
cat > "state/${ep}-phase0.json" <<EOF
{
  "episode": "${ep}",
  "phase": 0,
  "status": "completed",
  "started_at": "${start_time}",
  "completed_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "data": {
    "entities_count": {
      "characters": $(echo "$characters_json" | jq 'length'),
      "locations": $(echo "$locations_json" | jq 'length'),
      "props": $(echo "$props_json" | jq 'length')
    },
    "relationships_count": ${relationship_count},
    "warnings": ${warning_count}
  }
}
EOF

echo "✓ Phase 0 完成"
```
