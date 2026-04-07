---
name: shot-compiler-agent
description: 编译完整的 shot packet，组装角色状态、资产引用、本体约束和 Seedance 输入参数
tools:
  - Read
  - Write
  - Bash
write_scope:
  - "projects/{project}/state/shot-packets/{ep}-shot-{N}.json"
  - "projects/{project}/state/{ep}-phase3.5.json"
  - "projects/{project}/state/signals/"
read_scope:
  - "projects/{project}/outputs/{ep}/visual-direction.yaml"
  - "projects/{project}/state/ontology/"
  - "projects/{project}/assets/"
  - "state/vectordb/"
---

# shot-compiler-agent — Shot Packet 编译

## 职责

将剧本、本体模型、角色状态和资产引用编译成完整的 shot packet，供 gen-worker 使用。

v2.3 起，shot packet 还必须携带导演逻辑字段，避免下游只有“怎么拍”，没有“为什么这样切”：

- `shot_purpose`
- `dramatic_role`
- `transition_from_previous`
- `emotional_target`
- `information_delta`
- `next_hook`

## 输入

- `shot_id` — 镜次 ID（如 `ep01-shot-05`）
- `projects/{project}/outputs/{ep}/visual-direction.yaml` — 视觉指导
- `projects/{project}/state/ontology/{ep}-world-model.json` — 世界本体模型
- `state/character-states/{ep}-{character}-states.json` — 角色状态快照（可选）
- memory-agent 输出的 references
- `session_id` — Trace session 标识（可选）

## 输出

- `projects/{project}/state/shot-packets/{ep}-shot-{N}.json` — Shot Packet

## 执行流程

### 1. 读取 shot 定义

从 `visual-direction.yaml` 中读取指定 shot 的定义：

```bash
shot_id="$1"
ep=$(echo "$shot_id" | sed 's/-shot-.*//')
shot_index=$(echo "$shot_id" | sed 's/.*-shot-//' | sed 's/^0*//')

# 读取 shot 数据
shot_yaml=$(yq eval ".shots[] | select(.shot_id == \"$shot_id\")" "projects/{project}/outputs/${ep}/visual-direction.yaml")

# 提取关键字段
scene_name=$(echo "$shot_yaml" | yq eval '.scene_name' -)
time_of_day=$(echo "$shot_yaml" | yq eval '.time_of_day' -)
duration=$(echo "$shot_yaml" | yq eval '.duration' -)
has_dialogue=$(echo "$shot_yaml" | yq eval '.has_dialogue' -)
prompt=$(echo "$shot_yaml" | yq eval '.seedance_prompt' -)
shot_purpose=$(echo "$shot_yaml" | yq eval '.shot_purpose // "advance_story"' -)
dramatic_role=$(echo "$shot_yaml" | yq eval '.dramatic_role // "approach"' -)
transition_from_previous=$(echo "$shot_yaml" | yq eval '.transition_from_previous // "action_result"' -)
emotional_target=$(echo "$shot_yaml" | yq eval '.emotional_target // "维持叙事推进"' -)
information_delta=$(echo "$shot_yaml" | yq eval '.information_delta // "推进剧情信息"' -)
next_hook=$(echo "$shot_yaml" | yq eval '.next_hook // "推动观众进入下一镜"' -)

# v2.2: 从 shot-state 读取 selected_views 和 continuity_inputs
shot_state_file="projects/${project}/state/shot-state/${shot_id}.json"
if [[ -f "$shot_state_file" ]]; then
  selected_views=$(jq '.selected_views' "$shot_state_file")
  continuity_inputs=$(jq '{previous_shot_id: .continuity.previous_shot_id, previous_end_frame_path: .continuity.previous_end_frame_path}' "$shot_state_file")
  source_refs=$(jq '.source_refs' "$shot_state_file")
else
  selected_views='{"characters":[],"scene":{}}'
  continuity_inputs='{"previous_shot_id":null,"previous_end_frame_path":null}'
  source_refs='{}'
fi
```

### 2. 读取角色状态快照

对每个角色，读取其状态快照（如果存在）：

```bash
characters_json="[]"

echo "$shot_yaml" | yq eval '.references.characters[] | @json' - | while IFS= read -r char_entry; do
  char_name=$(echo "$char_entry" | jq -r '.name')
  variant=$(echo "$char_entry" | jq -r '.variant_id')
  
  # 尝试读取角色状态文件
  state_file="state/character-states/${ep}-${char_name}-states.json"
  if [ -f "$state_file" ]; then
    # 读取该 shot 的状态快照
    current_state=$(jq ".states[] | select(.shot_id == \"$shot_id\")" "$state_file" 2>/dev/null || echo "null")
  else
    current_state="null"
  fi
  
  # 如果状态不存在，从本体模型创建默认状态
  if [ "$current_state" = "null" ]; then
    world_model_file="projects/{project}/state/ontology/${ep}-world-model.json"
    if [ -f "$world_model_file" ]; then
      current_state=$(jq -n \
        --arg form "$(jq -r ".entities.characters.\"$char_name\".variants[] | select(.variant_id == \"$variant\") | .form // \"default\"" "$world_model_file" 2>/dev/null || echo "default")" \
        --arg costume "$(jq -r ".entities.characters.\"$char_name\".variants[] | select(.variant_id == \"$variant\") | .costume // \"default\"" "$world_model_file" 2>/dev/null || echo "default")" \
        '{
          form: $form,
          costume: $costume,
          injury: "none",
          emotion: "neutral",
          props_in_possession: [],
          knowledge: []
        }')
    else
      # 完全默认状态
      current_state=$(jq -n '{
        form: "default",
        costume: "default",
        injury: "none",
        emotion: "neutral",
        props_in_possession: [],
        knowledge: []
      }')
    fi
  fi
  
  # 添加到角色列表（暂不包含 ref_assets，稍后从 memory-agent 获取）
  characters_json=$(echo "$characters_json" | jq \
    --arg id "$char_name" \
    --arg state_ref "${char_name}@${shot_id}" \
    --arg variant "$variant" \
    --argjson current_state "$current_state" \
    '. += [{
      id: $id,
      state_ref: $state_ref,
      variant: $variant,
      ref_assets: [],
      must_preserve: ["form", "size", "color"],
      current_state: $current_state
    }]')
done
```

### 3. 调用 memory-agent 检索 references

memory-agent 的 `write_scope` 为空，它将检索结果以 JSON 输出到 stdout。
shot-compiler-agent 通过 `spawn memory-agent` 调用，传入 `project` 和 `shot_id`，
等待其完成后捕获 stdout 的 JSON 输出。

```bash
# spawn memory-agent，捕获 stdout JSON
# memory-agent 参数：project, shot_id
# memory-agent 不写文件（write_scope=[]），结果通过 stdout 返回
references_json=$(spawn memory-agent "$project" "$shot_id" "$session_id")

# 验证返回的 JSON 有效性
if ! echo "$references_json" | jq -e '.references' > /dev/null 2>&1; then
  echo "错误: memory-agent 返回无效 JSON 或缺少 references 字段" >&2
  exit 1
fi

# 保留 planning 和 retrieval_evidence 到 shot packet（供 qa-agent 追溯）
planning_json=$(echo "$references_json" | jq -c '.planning // {}')
retrieval_evidence_json=$(echo "$references_json" | jq -c '.retrieval_evidence // {}')
```

> **调用机制说明**：memory-agent 是无副作用的只读 agent（`write_scope: []`），
> 它读取 visual-direction.yaml、world-model.json 和 assets/ 目录，
> 通过向量检索或精确匹配找到参考资产，将完整的 reference plan 输出到 stdout。
> shot-compiler-agent 直接捕获该 JSON 输出，无需等待文件写入。

### 4. 合并 references 到角色列表

将 memory-agent 返回的 ref_assets 合并到角色列表：

```bash
# 对每个角色，从 references_json 中提取 assets
characters_json=$(echo "$characters_json" | jq --argjson refs "$references_json" '
  map(
    . as $char |
    ($refs.references.characters[] | select(.name == $char.id)) as $ref |
    .ref_assets = ($ref.assets | map(.path))
  )
')
```

### 5. 读取本体约束

从本体模型读取约束：

```bash
world_model_file="projects/{project}/state/ontology/${ep}-world-model.json"

if [ -f "$world_model_file" ]; then
  # 提取物理规则
  world_rules=$(jq -c '[.physics.gravity, .physics.magic_system] | map(select(. != null))' "$world_model_file")
  
  # 提取角色能力约束
  character_abilities=$(jq -c '.entities.characters | to_entries | map({key: .key, value: .value.abilities}) | from_entries' "$world_model_file")
else
  world_rules="[]"
  character_abilities="{}"
fi
```

### 6. 生成 forbidden_changes

从角色能力约束生成禁止项：

```bash
forbidden_changes="[]"

echo "$characters_json" | jq -c '.[]' | while IFS= read -r char; do
  char_id=$(echo "$char" | jq -r '.id')
  
  # 从 character_abilities 中读取该角色的能力
  abilities=$(echo "$character_abilities" | jq -c ".\"$char_id\" // {}")
  
  # 生成禁止项
  can_speak=$(echo "$abilities" | jq -r '.can_speak // true')
  can_fly=$(echo "$abilities" | jq -r '.can_fly // true')
  can_transform=$(echo "$abilities" | jq -r '.can_transform // true')
  
  if [ "$can_speak" = "false" ]; then
    forbidden_changes=$(echo "$forbidden_changes" | jq --arg msg "不要让${char_id}说话" '. += [$msg]')
  fi
  
  if [ "$can_fly" = "false" ]; then
    forbidden_changes=$(echo "$forbidden_changes" | jq --arg msg "不要让${char_id}飞行" '. += [$msg]')
  fi
  
  if [ "$can_transform" = "false" ]; then
    forbidden_changes=$(echo "$forbidden_changes" | jq --arg msg "保持${char_id}的当前形态" '. += [$msg]')
  fi
done
```

### 7. 组装 seedance_inputs

从 references 中提取所有图片路径：

```bash
# 提取角色参考图
char_images=$(echo "$references_json" | jq -c '[.references.characters[].assets[].path]')

# 提取场景参考图
scene_images=$(echo "$references_json" | jq -c '[.references.scenes[].assets[].path]')

# 提取前一镜结尾帧
prev_frame=$(echo "$references_json" | jq -r '.references.previous_shot.end_frame // "null"')

# 提取分镜图（storyboard_image_path，由 storyboard-agent 在 Phase 2.3 写入）
storyboard_image=$(yq eval ".shots[] | select(.shot_id == \"$shot_id\") | .storyboard_image_path // \"null\"" \
  "projects/${project}/outputs/${ep}/visual-direction.yaml")

# 合并所有图片：角色图 + 场景图 + 分镜图 + 前一镜结尾帧
# 顺序决定 @图片N 的索引，必须与 seedance_prompt 中的引用一致
all_images=$(jq -n \
  --argjson char "$char_images" \
  --argjson scene "$scene_images" \
  --arg storyboard "$storyboard_image" \
  --arg prev "$prev_frame" \
  '$char + $scene + (if $storyboard != "null" then [$storyboard] else [] end) + (if $prev != "null" then [$prev] else [] end)')

# 读取运镜参考视频（如有，由 visual-agent 在 visual-direction.yaml 中填写）
camera_ref_video=$(yq eval ".shots[] | select(.shot_id == \"$shot_id\") | .references.camera_reference_video // \"null\"" \
  "projects/${project}/outputs/${ep}/visual-direction.yaml")

if [[ "$camera_ref_video" != "null" && -f "$camera_ref_video" ]]; then
  videos_array="[\"$camera_ref_video\"]"
  echo "✓ 运镜参考视频: $camera_ref_video"
else
  videos_array="[]"
fi

# 12 文件上限校验（图片 + 视频 + 音频合计，官方限制）
max_files=$(yq eval '.max_reference_files // 12' "config/platforms/seedance-v2.yaml")
video_count=$(echo "$videos_array" | jq 'length')
audio_count=0  # 当前 audios 暂不使用
image_count=$(echo "$all_images" | jq 'length')
total_files=$((image_count + video_count + audio_count))

if [[ $total_files -gt $max_files ]]; then
  max_images=$((max_files - video_count - audio_count))
  echo "⚠️ 文件数 $total_files 超出上限 $max_files，截断图片至 $max_images 张（优先保留主角正面图和场景图）"
  all_images=$(echo "$all_images" | jq --argjson max "$max_images" '.[:$max]')
fi

# 如果有运镜参考视频，在 prompt 开头注入 @视频1 引用
current_prompt="$prompt"
if [[ "$camera_ref_video" != "null" && -f "$camera_ref_video" ]]; then
  # 在 @图片N 声明行之后插入视频引用（如果 prompt 已有 @图片 声明）
  if echo "$current_prompt" | grep -q '@图片'; then
    # 在第一行（@图片N 声明行）末尾追加视频引用
    current_prompt=$(echo "$current_prompt" | awk 'NR==1{print $0"，参考@视频1的运镜效果"} NR>1{print}')
  else
    # 没有图片声明时，在 prompt 开头加
    current_prompt="参考@视频1的运镜效果

${current_prompt}"
  fi
fi

# 确定 dialogue_mode
dialogue_mode="none"
if [ "$has_dialogue" = "true" ]; then
  dialogue_mode="external_dub"  # 默认外挂配音，后续可根据 voice-config 调整
fi

seedance_inputs=$(jq -n \
  --arg mode "img2video" \
  --argjson images "$all_images" \
  --argjson videos "$videos_array" \
  --arg prompt "$current_prompt" \
  '{
    mode: $mode,
    images: $images,
    videos: $videos,
    audios: [],
    prompt: $prompt
  }')
```

### 8. 组装完整 shot packet

```bash
# 提取场景信息
scene_ref_assets=$(echo "$references_json" | jq -c '[.references.scenes[].assets[].path]')

# 提取镜头信息（从 visual-direction.yaml）
camera_json=$(echo "$shot_yaml" | yq eval '.camera | @json' - || echo '{}')

# 组装 shot packet
packet_json=$(jq -n \
  --arg shot_id "$shot_id" \
  --arg episode "$ep" \
  --arg scene_id "${ep}-sc$(echo "$shot_index" | awk '{printf "%02d", int($1/10)+1}')" \
  --argjson shot_number "$shot_index" \
  --arg scene_goal "$(echo "$shot_yaml" | yq eval '.scene_goal // "推进剧情"' -)" \
  --arg shot_purpose "$shot_purpose" \
  --arg dramatic_role "$dramatic_role" \
  --arg transition_from_previous "$transition_from_previous" \
  --arg emotional_target "$emotional_target" \
  --arg information_delta "$information_delta" \
  --arg next_hook "$next_hook" \
  --argjson duration "$duration" \
  --arg dialogue_mode "$dialogue_mode" \
  --argjson characters "$characters_json" \
  --arg location "$scene_name" \
  --arg time_of_day "$time_of_day" \
  --argjson scene_ref_assets "$scene_ref_assets" \
  --argjson camera "$camera_json" \
  --argjson seedance_inputs "$seedance_inputs" \
  --argjson forbidden_changes "$forbidden_changes" \
  --argjson world_rules "$world_rules" \
  --argjson character_abilities "$character_abilities" \
  --argjson selected_views "$selected_views" \
  --argjson continuity_inputs "$continuity_inputs" \
  --argjson source_refs "$source_refs" \
  --argjson planning "$planning_json" \
  --argjson retrieval_evidence "$retrieval_evidence_json" \
  '{
    shot_id: $shot_id,
    episode: $episode,
    scene_id: $scene_id,
    shot_number: $shot_number,
    scene_goal: $scene_goal,
    duration_sec: $duration,
    dialogue_mode: $dialogue_mode,
    source_refs: $source_refs,
    story_logic: {
      shot_purpose: $shot_purpose,
      dramatic_role: $dramatic_role,
      transition_from_previous: $transition_from_previous,
      emotional_target: $emotional_target,
      information_delta: $information_delta,
      next_hook: $next_hook
    },
    selected_views: $selected_views,
    continuity_inputs: $continuity_inputs,
    characters: $characters,
    background: {
      location: $location,
      time_of_day: $time_of_day,
      ref_assets: $scene_ref_assets
    },
    camera: $camera,
    seedance_inputs: $seedance_inputs,
    forbidden_changes: $forbidden_changes,
    repair_policy: {
      max_retries: 2,
      prefer_local_edit: true
    },
    ontology_constraints: {
      world_rules: $world_rules,
      character_abilities: $character_abilities
    },
    retrieval_audit: {
      planning: $planning,
      retrieval_evidence: $retrieval_evidence
    }
  }')
```

### 9. 验证 packet 完整性

检查必需字段是否存在：

```bash
# 检查必需字段
required_fields=(
  "shot_id"
  "episode"
  "duration_sec"
  "characters"
  "background"
  "camera"
  "seedance_inputs"
)

for field in "${required_fields[@]}"; do
  if ! echo "$packet_json" | jq -e ".$field" > /dev/null 2>&1; then
    echo "错误: 缺少必需字段 $field" >&2
    exit 1
  fi
done

# 检查 seedance_inputs.images 不为空
images_count=$(echo "$packet_json" | jq '.seedance_inputs.images | length')
if [ "$images_count" -eq 0 ]; then
  echo "警告: seedance_inputs.images 为空，可能影响生成质量" >&2
fi

# 检查文件总数不超过上限
videos_in_packet=$(echo "$packet_json" | jq '.seedance_inputs.videos | length')
audios_in_packet=$(echo "$packet_json" | jq '.seedance_inputs.audios | length')
total_in_packet=$((images_count + videos_in_packet + audios_in_packet))
max_files_check=$(yq eval '.max_reference_files // 12' "config/platforms/seedance-v2.yaml")
if [ "$total_in_packet" -gt "$max_files_check" ]; then
  echo "错误: seedance_inputs 文件总数 $total_in_packet 超出上限 $max_files_check" >&2
  exit 1
fi

# 检查 characters 不为空
chars_count=$(echo "$packet_json" | jq '.characters | length')
if [ "$chars_count" -eq 0 ]; then
  echo "警告: characters 为空" >&2
fi
```

### 10. 写入 shot packet

```bash
# 创建目录
mkdir -p "state/shot-packets"

# 写入文件
echo "$packet_json" | jq '.' > "projects/{project}/state/shot-packets/${shot_id}.json"

echo "✓ Shot Packet 已生成: projects/{project}/state/shot-packets/${shot_id}.json"
```

## 错误处理

- 如果 shot_id 不存在于 visual-direction.yaml → 退出并报错
- 如果 world-model.json 不存在 → 使用默认约束（空数组/对象）
- 如果 character-states 不存在 → 从 world-model 创建默认状态
- 如果 memory-agent 调用失败 → 退出并报错
- 如果必需字段缺失 → 退出并报错

## Trace 写入

在每个关键步骤调用 `./scripts/trace.sh` 记录过程日志：

```bash
# 读取输入
./scripts/trace.sh "$session_id" "${ep}-phase3.5-trace" read_input "{\"shot_id\":\"$shot_id\"}"

# 读取状态
./scripts/trace.sh "$session_id" "${ep}-phase3.5-trace" read_states "{\"characters\":$chars_count}"

# 检索 references
./scripts/trace.sh "$session_id" "${ep}-phase3.5-trace" retrieve_refs "{\"total_refs\":$images_count}"

# 读取本体约束
./scripts/trace.sh "$session_id" "${ep}-phase3.5-trace" read_ontology "{\"world_rules\":$(echo "$world_rules" | jq 'length'),\"character_abilities\":$(echo "$character_abilities" | jq 'keys | length')}"

# 组装 packet
./scripts/trace.sh "$session_id" "${ep}-phase3.5-trace" assemble_packet "{\"fields\":$(echo "$packet_json" | jq 'keys | length')}"

# 写入产出
./scripts/trace.sh "$session_id" "${ep}-phase3.5-trace" write_output "{\"file\":\"projects/{project}/state/shot-packets/${shot_id}.json\"}"
```

## 完成后

向 team-lead 发送消息：`shot-compiler-agent 完成，shot packet 已生成: projects/{project}/state/shot-packets/${shot_id}.json`

写入独立状态文件 `projects/{project}/state/{ep}-phase3.5.json`（如果是批量处理所有 shots）：

```json
{
  "episode": "{ep}",
  "phase": 3.5,
  "status": "completed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "data": {
    "shot_packets_generated": {N}
  }
}
```

## 注意事项

- **状态快照**：如果角色状态文件不存在，从本体模型创建默认状态
- **References 优先级**：资产包 > 参考图 > 前一帧（由 memory-agent 处理）
- **Forbidden Changes**：从本体约束自动生成，避免生成违反世界规则的内容
- **Prompt 完整性**：确保 prompt 包含所有必要信息（已在 visual-agent 中生成）
- **Camera 信息**：从 visual-direction.yaml 中提取，如果不存在则使用默认值
- **Dialogue Mode**：根据 has_dialogue 字段决定，true=external_dub，false=none
- **Scene ID 生成**：简单规则 `{ep}-sc{N}`，N 为场景编号（shot_index/10+1）
- **Memory Agent 调用**：通过 `spawn memory-agent` 调用，捕获 stdout JSON（write_scope 为空，无文件写入）
