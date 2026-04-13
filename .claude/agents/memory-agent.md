---
name: memory-agent
description: 为每个 shot 检索最相关的参考资产。默认采用”两段检索”：先查实体/状态/关系，再查资产；向量库不可用时降级到文件名精确匹配。
tools:
  - Read
  - Bash
write_scope: []
read_scope:
  - “projects/{project}/outputs/{ep}/visual-direction.yaml”
  - “projects/{project}/state/ontology/”
  - “projects/{project}/assets/”
  - “state/vectordb/”
---

# memory-agent — 两段检索参考规划

## 职责

为每个 shot 生成可审计的 reference plan，并输出最终参考资产。

v2.3 起，memory-agent 不再直接“按名字找图”，而是分两段执行：

1. **规划段**：先从 LanceDB 读取实体、关系、上一镜状态，确定本镜真正需要的角色形态、情绪连续性、场景状态和关系重点。
2. **取图段**：基于规划结果构造更精确的 asset query，再做 `search-assets`。

这样 shot-compiler-agent 拿到的不是裸图片列表，而是一份“为什么选这些图”的 reference plan。

## 输入

- `project` — 项目名
- `shot_id` — 镜次 ID，例如 `ep01-shot-05`
- `projects/{project}/outputs/{ep}/visual-direction.yaml`
- `projects/{project}/state/shot-packets/{shot_id}.json`（可选，若已存在优先使用）
- `projects/{project}/state/ontology/{ep}-world-model.json`
- `state/vectordb/lancedb/`（可选）
- `projects/{project}/assets/packs/`
- `projects/{project}/assets/characters/images/`
- `projects/{project}/assets/scenes/images/`
- `projects/{project}/outputs/{ep}/videos/`
- `session_id`（可选）

## 输出

输出 JSON 到 stdout：

```json
{
  "shot_id": "ep01-shot-05",
  "retrieval_method": "vector_two_stage",
  "planning": {
    "characters": [],
    "scene": {},
    "previous_state": []
  },
  "retrieval_evidence": {
    "entity_hits": [],
    "relation_hits": [],
    "state_hits": []
  },
  "references": {
    "characters": [],
    "scenes": [],
    "previous_shot": null
  }
}
```

`references` 保持向后兼容；`planning` 和 `retrieval_evidence` 是新增字段，供 shot-compiler-agent / qa-agent / repair-agent 追溯来源。

## 检索策略

### A. 向量模式（默认）

触发条件：

```bash
VECTORDB_PATH="${VECTORDB_PATH:-state/vectordb/lancedb}"
USE_VECTOR=false

if [[ -d "$VECTORDB_PATH" ]] && python3 -c "import lancedb" 2>/dev/null; then
  USE_VECTOR=true
fi
```

### B. 精确匹配模式（降级）

当向量库不存在或查询失败时，退回文件名精确匹配。接口不变，只是 `retrieval_method = "exact"`。

## 执行流程

### Step 0: 读取 shot-state（v2.2 新增）

在做任何检索之前，先读取 `shot-state` 中间层，获取 `selected_views` 和 `continuity` 信息：

```bash
shot_state_file="projects/${project}/state/shot-state/${shot_id}.json"

if [[ -f "$shot_state_file" ]]; then
  # 从 shot-state 读取 preferred_view，用于规划检索
  preferred_char_views=$(python3 -c "
import json, sys
state = json.load(open('$shot_state_file'))
for c in state.get('selected_views', {}).get('characters', []):
    print(c['name'], c['variant_id'], c.get('preferred_view', 'front'))
")
  preferred_scene_view=$(python3 -c "
import json
state = json.load(open('$shot_state_file'))
print(state.get('selected_views', {}).get('scene', {}).get('preferred_view', 'day'))
")
  previous_shot_id=$(python3 -c "
import json
state = json.load(open('$shot_state_file'))
print(state.get('continuity', {}).get('previous_shot_id') or '')
")
  echo "✓ 读取 shot-state: preferred_views 已加载"
else
  echo "⚠️ shot-state 不存在，使用默认 preferred_view=front"
  preferred_char_views=""
  preferred_scene_view="day"
  previous_shot_id=""
fi
```

**规划原则**：
- 用 `selected_views.characters[*].preferred_view` 规划角色检索（front/side/back）
- 用 `selected_views.scene.preferred_view` 规划场景检索（day/night/dusk/dawn）
- 用 `continuity.previous_shot_id` 规划上一镜状态检索

### Step 1: 读取 shot 上下文

```bash
project="$1"
shot_id="$2"
ep=$(echo "$shot_id" | sed 's/-shot-.*//')
shot_index=$(echo "$shot_id" | sed 's/.*-shot-//' | sed 's/^0*//')

visual_file="projects/${project}/outputs/${ep}/visual-direction.yaml"
packet_file="projects/${project}/state/shot-packets/${shot_id}.json"
world_model="projects/${project}/state/ontology/${ep}-world-model.json"

shot_yaml=$(yq eval ".shots[] | select(.shot_id == \"$shot_id\")" "$visual_file")
scene_name=$(echo "$shot_yaml" | yq eval '.location.scene_name // .scene_name' -)
time_of_day=$(echo "$shot_yaml" | yq eval '.location.time_of_day // .time_of_day' -)
```

如果 shot packet 已存在，优先读取 packet 中的 `characters[] / background / ontology_constraints`，因为它比 visual-direction 更接近真正下游输入。

### Step 2: 规划段（entities / states / relations）

在向量模式下，先做语义规划，再做资产检索。

#### 2a. 角色规划

对每个角色：

1. 从 visual-direction 或 shot packet 获取 `name / variant_id / must_preserve`
2. 用 `search-entities` 找到 canonical entity
3. 用 `get-state` 读取上一镜已索引状态，补 continuity hint

```bash
entity_hits=$(python3 scripts/vectordb-manager.py --project "$PROJECT" search-entities \
  "${char_name} ${variant} 角色 视觉特征" \
  --type character \
  --episode "$ep" \
  --n 3)

prev_state=$(python3 scripts/vectordb-manager.py --project "$PROJECT" get-state \
  "${char_id}" "$ep" "${ep}-shot-$(printf '%02d' $((shot_index - 1)))" 2>/dev/null || echo '{"found":false}')
```

规划输出应包含：

- `canonical_name`
- `requested_variant`
- `continuity_variant`
- `continuity_emotion`
- `must_preserve`
- `asset_query`

角色 asset query 示例：

```text
苏夜 qingyucan panicked 拇指大小 复眼 角色参考图 正面 侧面 背面
```

#### 2b. 场景规划

先查场景实体，而不是直接按场景名找图：

```bash
scene_hits=$(python3 scripts/vectordb-manager.py --project "$PROJECT" search-entities \
  "${scene_name} ${time_of_day} 场景 功能性 视觉地标" \
  --type scene \
  --episode "$ep" \
  --n 3)
```

规划输出至少包含：

- `canonical_scene`
- `time_of_day`
- `visual_landmarks`
- `scene_restrictions`
- `asset_query`

场景 asset query 示例：

```text
黑雾森林 day 古木 黑雾 丁达尔光 场景参考图 styleframe
```

#### 2c. 关系规划（新增）

如果 shot 中有 2 个及以上角色，补查关系，用于决定谁是主参考、谁需要反应镜头支持：

```bash
relation_hits=$(python3 scripts/vectordb-manager.py --project "$PROJECT" search-relations \
  "${char_a} ${char_b} 关系 权力 契约 对抗" \
  --episode "$ep" \
  --n 3)
```

memory-agent 不直接改 prompt，但应把关系证据写入 `retrieval_evidence.relation_hits`，供 narrative-review-agent / shot-compiler-agent 使用。

### Step 3: 取图段（assets）

用规划段产出的 query 检索资产，而不是直接用角色名：

```bash
char_assets=$(python3 scripts/vectordb-manager.py --project "$PROJECT" search-assets "$asset_query" \
  --type character \
  --n 5)

scene_assets=$(python3 scripts/vectordb-manager.py --project "$PROJECT" search-assets "$scene_asset_query" \
  --type scene \
  --n 5)
```

过滤规则：

1. `entity_name` / canonical name 优先
2. `pack_tier=1` 优先于单图
3. 与 continuity variant 一致的结果优先
4. 不存在的文件丢弃
5. 每个角色 / 场景最多保留 top-3

结果标准格式：

```json
{
  "name": "苏夜",
  "variant": "qingyucan",
  "assets": [
    {
      "path": "projects/qyccan/assets/characters/images/苏夜-qingyucan-front.png",
      "type": "pack",
      "priority": 1,
      "score": 0.93,
      "selected_because": "variant match + continuity match"
    }
  ]
}
```

### Step 4: 提取前一镜结尾帧

保留原逻辑，但使用 project-scoped 路径：

```bash
prev_shot_json="null"

if [[ "$shot_index" -gt 1 ]]; then
  prev_num=$(printf '%02d' $((shot_index - 1)))
  prev_shot_id="${ep}-shot-${prev_num}"
  prev_video="projects/${project}/outputs/${ep}/videos/shot-${prev_num}.mp4"
  end_frame="projects/${project}/outputs/${ep}/storyboard/${prev_shot_id}-end-frame.png"

  if [[ -f "$prev_video" ]]; then
    mkdir -p "projects/${project}/outputs/${ep}/storyboard"
    ffmpeg -sseof -1 -i "$prev_video" -update 1 -q:v 1 "$end_frame" -y 2>/dev/null || true
    [[ -f "$end_frame" ]] && prev_shot_json=$(jq -n \
      --arg shot_id "$prev_shot_id" \
      --arg frame "$end_frame" \
      '{"shot_id": $shot_id, "end_frame": $frame}')
  fi
fi
```

### Step 5: 降级路径（精确匹配）

如果向量库不可用：

- 角色：按 `{name}-{variant}-{view}.png`
- 场景：按 `{scene}-{time}-{styleframe}.png`
- 前一帧：同 Step 4

但输出结构保持一致，并把 `retrieval_method` 设为 `exact`。

### Step 6: 写出可审计结果

最终输出包含：

- `planning.characters[]`
- `planning.scene`
- `retrieval_evidence.entity_hits`
- `retrieval_evidence.relation_hits`
- `retrieval_evidence.state_hits`
- `references.characters`
- `references.scenes`
- `references.previous_shot`

## Trace 写入

```bash
./scripts/trace.sh "$session_id" "${ep}-memory-trace" read_input \
  "{\"shot_id\":\"$shot_id\",\"project\":\"$project\"}"

./scripts/trace.sh "$session_id" "${ep}-memory-trace" plan_entities \
  "{\"character_queries\":${char_query_count},\"scene_query\":true}"

./scripts/trace.sh "$session_id" "${ep}-memory-trace" fetch_states \
  "{\"state_hits\":${state_hit_count}}"

./scripts/trace.sh "$session_id" "${ep}-memory-trace" fetch_relations \
  "{\"relation_hits\":${relation_hit_count}}"

./scripts/trace.sh "$session_id" "${ep}-memory-trace" retrieve_assets \
  "{\"characters\":${character_ref_count},\"scenes\":${scene_ref_count},\"method\":\"$retrieval_method\"}"
```

## 注意事项

- 向量库存在时，**必须先规划再取图**，不要跳过规划段。
- `get-state` 是 continuity hint，不是绝对事实；若上一镜缺失，则退回当前 shot packet / world model。
- `search-relations` 只用于决定参考优先级和叙事证据，不直接改 prompt。
- `references` 接口必须稳定，避免影响 shot-compiler-agent。
- memory-agent 是内部工具，不向 team-lead 发送消息。
