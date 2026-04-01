---
name: ontology-builder-agent
description: 本体论构建 agent。从剧本和角色档案构建世界本体模型，提取实体、关系和约束。
tools:
  - Read
  - Write
  - Bash
---

# ontology-builder-agent — 本体论构建

## 职责

从剧本和角色/场景档案构建世界本体模型（World Model），为后续的状态管理和 shot packet 编译提供基础。

## 输入

- `script/{ep}.md` — 剧本
- `assets/characters/profiles/*.yaml` — 角色档案
- `assets/scenes/profiles/*.yaml` — 场景档案
- `config/ontology/world-model-schema.yaml` — Schema 定义

## 输出

- `state/ontology/{ep}-world-model.json` — 世界本体模型

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
if [[ ! -f "script/${ep}.md" ]]; then
  echo "ERROR: 剧本文件不存在: script/${ep}.md" >&2
  exit 1
fi

# 读取剧本
script_content=$(cat "script/${ep}.md")

# 读取所有角色档案
character_files=$(find assets/characters/profiles -name "*.yaml" -type f 2>/dev/null || echo "")
character_count=$(echo "$character_files" | grep -c . || echo "0")

# 读取所有场景档案
scene_files=$(find assets/scenes/profiles -name "*.yaml" -type f 2>/dev/null || echo "")
scene_count=$(echo "$scene_files" | grep -c . || echo "0")

# 记录 trace
./scripts/trace.sh "$session_id" "$trace_file" "read_inputs" \
  "{\"script\": \"script/${ep}.md\", \"character_count\": ${character_count}, \"scene_count\": ${scene_count}}"

echo "✓ 读取输入: 剧本 1 个, 角色档案 ${character_count} 个, 场景档案 ${scene_count} 个"
```

### Step 2: 提取角色实体

使用 LLM 从角色档案中提取结构化信息：

```bash
# 构造 LLM prompt
cat > /tmp/extract_characters_prompt.txt <<'EOF'
从以下角色档案中提取结构化实体信息，输出 JSON 数组格式。

要求：
1. 每个角色一个对象
2. 从 tier 字段读取层级（protagonist/supporting/minor）
3. 从 variants 字段读取变体信息，current_variant 默认为 "default"
4. 从 appearance 字段提取物理属性
5. 从 cultivation_level 或 abilities 字段提取能力
6. 从 personality 和 background 推断约束

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
    "abilities": ["能力1", "能力2"],
    "constraints": ["约束1", "约束2"]
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

### Step 3: 提取场景实体

使用 LLM 从场景档案中提取结构化信息：

```bash
# 构造 LLM prompt
cat > /tmp/extract_locations_prompt.txt <<'EOF'
从以下场景档案中提取结构化实体信息，输出 JSON 数组格式。

要求：
1. 每个场景一个对象
2. 从 description 字段提取空间属性
3. 从 lighting 字段推断时间变体
4. 推断 indoor/outdoor 类型

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
    "atmosphere": "氛围描述"
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

# 组装 world-model.json
cat > /tmp/world_model.json <<EOF
{
  "world_id": "aladdin01-${ep}",
  "episode": "${ep}",
  "created_at": "${timestamp}",
  "entities": {
    "characters": ${characters_json},
    "locations": ${locations_json},
    "props": ${props_json}
  },
  "relationships": ${relationships_json},
  "physics": ${physics_json},
  "narrative_constraints": ${narrative_json}
}
EOF

# 创建输出目录
mkdir -p state/ontology

# 写入文件
cat /tmp/world_model.json | jq '.' > "state/ontology/${ep}-world-model.json"

# 计算实体总数
entity_count=$(($(echo "$characters_json" | jq 'length') + $(echo "$locations_json" | jq 'length') + $(echo "$props_json" | jq 'length')))

# 记录 trace
./scripts/trace.sh "$session_id" "$trace_file" "write_world_model" \
  "{\"output\": \"state/ontology/${ep}-world-model.json\", \"entity_count\": ${entity_count}}"

echo "✓ 世界模型已写入: state/ontology/${ep}-world-model.json"
echo "  - 实体总数: ${entity_count}"
echo "  - 关系总数: ${relationship_count}"
```

## 完成后

向 team-lead 发送消息：`ontology-builder-agent 完成，world-model 已生成，实体数：{entity_count}，关系数：{relationship_count}`

写入独立状态文件 `state/{ep}-phase0.json`：
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
