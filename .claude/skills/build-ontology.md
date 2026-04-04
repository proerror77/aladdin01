---
name: build-ontology
description: 构建世界本体模型。从剧本和角色/场景档案提取实体、关系和约束，生成 world-model.json。
---

# ~build-ontology — 构建世界本体模型

## 用法

```bash
~build-ontology ep01       # 为单集构建本体
~build-ontology --all      # 为所有剧本构建本体
~build-ontology --validate # 只验证现有本体模型
```

## 功能

从剧本和角色/场景档案构建世界本体模型（World Model），为后续的状态管理和 shot packet 编译提供基础。

## 执行流程

### 单集模式（~build-ontology ep01）

```bash
#!/usr/bin/env bash
set -euo pipefail

ep="$1"

# 1. 检查输入文件是否存在
if [[ ! -f "script/${ep}.md" ]]; then
  echo "ERROR: 剧本文件不存在: script/${ep}.md" >&2
  exit 1
fi

echo "✓ 剧本文件存在: script/${ep}.md"

# 检查角色档案
character_count=$(find projects/{project}/assets/characters/profiles -name "*.yaml" -type f 2>/dev/null | wc -l || echo "0")
echo "✓ 角色档案: ${character_count} 个"

# 检查场景档案
scene_count=$(find projects/{project}/assets/scenes/profiles -name "*.yaml" -type f 2>/dev/null | wc -l || echo "0")
echo "✓ 场景档案: ${scene_count} 个"

# 2. 生成 session_id 和 trace_file
session_id="ontology-$(date +%Y%m%d-%H%M%S)"
trace_file="${ep}-phase0-trace"

echo "Session ID: ${session_id}"

# 3. 调用 ontology-builder-agent
# 注意：这里需要使用 Claude Code 的 Agent tool 调用
# 在实际执行时，由 Claude Code 调用 ontology-builder-agent

echo "正在构建世界本体模型..."

# 这里是占位符，实际由 Claude Code 的 Agent tool 执行
# Agent(
#   subagent_type="ontology-builder-agent",
#   prompt="为 ${ep} 构建世界本体模型",
#   session_id="${session_id}",
#   trace_file="${trace_file}"
# )

# 4. 验证输出
if [[ ! -f "projects/{project}/state/ontology/${ep}-world-model.json" ]]; then
  echo "ERROR: 世界模型文件未生成: projects/{project}/state/ontology/${ep}-world-model.json" >&2
  exit 1
fi

if [[ ! -f "state/${ep}-phase0.json" ]]; then
  echo "ERROR: 状态文件未生成: state/${ep}-phase0.json" >&2
  exit 1
fi

# 5. 输出摘要
echo ""
echo "✓ 世界本体模型已生成: projects/{project}/state/ontology/${ep}-world-model.json"
echo ""

# 读取统计信息
character_count=$(jq '.entities.characters | length' "projects/{project}/state/ontology/${ep}-world-model.json")
location_count=$(jq '.entities.locations | length' "projects/{project}/state/ontology/${ep}-world-model.json")
prop_count=$(jq '.entities.props | length' "projects/{project}/state/ontology/${ep}-world-model.json")
relationship_count=$(jq '.relationships | length' "projects/{project}/state/ontology/${ep}-world-model.json")

echo "实体统计:"
echo "  - 角色: ${character_count}"
echo "  - 场景: ${location_count}"
echo "  - 道具: ${prop_count}"
echo ""
echo "关系统计:"
echo "  - 总数: ${relationship_count}"
echo ""

# 显示叙事约束（如果有）
if jq -e '.narrative_constraints.character_evolution | length > 0' "projects/{project}/state/ontology/${ep}-world-model.json" > /dev/null 2>&1; then
  echo "叙事约束:"
  jq -r '.narrative_constraints.character_evolution[] | "  - \(.character): \(.from) → \(.to) (触发: \(.trigger))"' "projects/{project}/state/ontology/${ep}-world-model.json"
  echo ""
fi

# 显示警告（如果有）
warning_count=$(jq '.data.warnings' "state/${ep}-phase0.json")
if [[ "$warning_count" -gt 0 ]]; then
  echo "⚠️ 冲突检测: ${warning_count} 个警告"
else
  echo "✓ 冲突检测: 无警告"
fi
```

### 批量模式（~build-ontology --all）

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. 扫描 script/ 目录，获取所有剧本
scripts=$(find script -name "*.md" -type f | sort)
script_count=$(echo "$scripts" | wc -l)

echo "发现 ${script_count} 个剧本"
echo ""

# 2. 并行调用 ontology-builder-agent（每集一个 agent）
# 注意：实际并行由 Claude Code 的 Agent tool 处理

for script_file in $scripts; do
  ep=$(basename "$script_file" .md)
  echo "处理: ${ep}"
  
  # 调用单集模式
  # 这里是占位符，实际由 Claude Code 调用
  # ~build-ontology "$ep"
done

# 3. 汇总统计
echo ""
echo "批量构建完成"
echo ""

total_characters=0
total_locations=0
total_props=0
total_relationships=0

for script_file in $scripts; do
  ep=$(basename "$script_file" .md)
  
  if [[ -f "projects/{project}/state/ontology/${ep}-world-model.json" ]]; then
    character_count=$(jq '.entities.characters | length' "projects/{project}/state/ontology/${ep}-world-model.json")
    location_count=$(jq '.entities.locations | length' "projects/{project}/state/ontology/${ep}-world-model.json")
    prop_count=$(jq '.entities.props | length' "projects/{project}/state/ontology/${ep}-world-model.json")
    relationship_count=$(jq '.relationships | length' "projects/{project}/state/ontology/${ep}-world-model.json")
    
    total_characters=$((total_characters + character_count))
    total_locations=$((total_locations + location_count))
    total_props=$((total_props + prop_count))
    total_relationships=$((total_relationships + relationship_count))
  fi
done

echo "全局统计:"
echo "  - 总角色: ${total_characters}"
echo "  - 总场景: ${total_locations}"
echo "  - 总道具: ${total_props}"
echo "  - 总关系: ${total_relationships}"
```

### 验证模式（~build-ontology --validate ep01）

```bash
#!/usr/bin/env bash
set -euo pipefail

ep="$1"

# 1. 读取现有 world-model.json
if [[ ! -f "projects/{project}/state/ontology/${ep}-world-model.json" ]]; then
  echo "ERROR: 世界模型文件不存在: projects/{project}/state/ontology/${ep}-world-model.json" >&2
  exit 1
fi

echo "正在验证: projects/{project}/state/ontology/${ep}-world-model.json"
echo ""

# 2. 验证 Schema 完整性
required_fields=("world_id" "episode" "created_at" "entities" "relationships" "physics")

for field in "${required_fields[@]}"; do
  if ! jq -e ".${field}" "projects/{project}/state/ontology/${ep}-world-model.json" > /dev/null 2>&1; then
    echo "❌ 缺少必需字段: ${field}"
  else
    echo "✓ 字段存在: ${field}"
  fi
done

echo ""

# 3. 验证逻辑一致性
echo "验证逻辑一致性..."

# 检查关系中的实体是否存在
relationship_count=$(jq '.relationships | length' "projects/{project}/state/ontology/${ep}-world-model.json")
invalid_count=0

for i in $(seq 0 $((relationship_count - 1))); do
  from=$(jq -r ".relationships[$i].from" "projects/{project}/state/ontology/${ep}-world-model.json")
  to=$(jq -r ".relationships[$i].to" "projects/{project}/state/ontology/${ep}-world-model.json")
  
  # 检查 from 实体
  if ! jq -e ".entities.characters[] | select(.name == \"$from\")" "projects/{project}/state/ontology/${ep}-world-model.json" > /dev/null 2>&1 && \
     ! jq -e ".entities.locations[] | select(.name == \"$from\")" "projects/{project}/state/ontology/${ep}-world-model.json" > /dev/null 2>&1 && \
     ! jq -e ".entities.props[] | select(.name == \"$from\")" "projects/{project}/state/ontology/${ep}-world-model.json" > /dev/null 2>&1; then
    echo "⚠️ 关系 #$i: 实体 $from 不存在"
    invalid_count=$((invalid_count + 1))
  fi
  
  # 检查 to 实体
  if ! jq -e ".entities.characters[] | select(.name == \"$to\")" "projects/{project}/state/ontology/${ep}-world-model.json" > /dev/null 2>&1 && \
     ! jq -e ".entities.locations[] | select(.name == \"$to\")" "projects/{project}/state/ontology/${ep}-world-model.json" > /dev/null 2>&1 && \
     ! jq -e ".entities.props[] | select(.name == \"$to\")" "projects/{project}/state/ontology/${ep}-world-model.json" > /dev/null 2>&1; then
    echo "⚠️ 关系 #$i: 实体 $to 不存在"
    invalid_count=$((invalid_count + 1))
  fi
done

echo ""

if [[ $invalid_count -eq 0 ]]; then
  echo "✓ 逻辑一致性验证通过"
else
  echo "⚠️ 发现 ${invalid_count} 个逻辑不一致"
fi

echo ""
echo "验证完成"
```

## 输出

- `projects/{project}/state/ontology/{ep}-world-model.json` — 世界本体模型
- `projects/{project}/state/{ep}-phase0.json` — Phase 0 状态文件
- `projects/{project}/state/ontology/{ep}-conflicts.txt` — 冲突报告（如有）

## 依赖

- `ontology-builder-agent`
- `config/ontology/world-model-schema.yaml`

## 示例

```bash
# 为 ep01 构建本体
~build-ontology ep01

# 为所有剧本构建本体
~build-ontology --all

# 验证现有本体模型
~build-ontology --validate ep01
```

## 注意事项

- 本体构建是 Phase 0，应在 Phase 1（合规预检）之前运行
- 如果角色/场景档案更新，需要重新构建本体
- 本体模型会被 Phase 2.5（资产工厂）和 Phase 3.5（Shot Packet 编译）使用
