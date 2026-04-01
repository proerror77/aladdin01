---
name: memory-agent
description: 为每个 shot 检索最相关的参考资产（角色图、场景图、前一镜结尾帧），按优先级排序
tools:
  - Read
  - Bash
---

# memory-agent — 参考资产检索

## 职责

为每个 shot 检索最相关的 references，按优先级排序：
1. `assets/packs/` （最高优先级，NanoBanana 生成的多视角资产）
2. `assets/characters/images/` 或 `assets/scenes/images/` （单视角参考图）
3. 前一镜结尾帧（连续性参考）

## 输入

- `shot_id` — 镜次 ID（如 `ep01-shot-05`）
- `outputs/{ep}/visual-direction.yaml` — 镜次定义
- `assets/packs/` — 多视角资产包
- `assets/characters/images/` — 角色参考图
- `assets/scenes/images/` — 场景参考图
- `outputs/{ep}/videos/` — 已生成的视频（用于提取前一镜结尾帧）
- `session_id` — Trace session 标识（可选）

## 输出

JSON 格式的 references 列表，输出到 stdout：

```json
{
  "shot_id": "ep01-shot-05",
  "references": {
    "characters": [
      {
        "name": "苏夜",
        "variant": "qingyu_silkworm",
        "assets": [
          {
            "path": "assets/packs/characters/苏夜-qingyu_silkworm-front.png",
            "type": "pack",
            "priority": 1
          },
          {
            "path": "assets/packs/characters/苏夜-qingyu_silkworm-side.png",
            "type": "pack",
            "priority": 1
          }
        ]
      }
    ],
    "scenes": [
      {
        "name": "叶红衣闺房",
        "time_of_day": "night",
        "assets": [
          {
            "path": "assets/packs/scenes/叶红衣闺房-night-styleframe.png",
            "type": "pack",
            "priority": 1
          }
        ]
      }
    ],
    "previous_shot": {
      "shot_id": "ep01-shot-04",
      "end_frame": "outputs/ep01/storyboard/ep01-shot-04-end-frame.png"
    }
  }
}
```

## 执行流程

### 1. 读取 shot 定义

从 `visual-direction.yaml` 中读取指定 shot 的定义：

```bash
shot_id="$1"
ep=$(echo "$shot_id" | sed 's/-shot-.*//')
shot_index=$(echo "$shot_id" | sed 's/.*-shot-//' | sed 's/^0*//')

# 读取 shot 数据
shot_yaml=$(yq eval ".shots[] | select(.shot_id == \"$shot_id\")" "outputs/${ep}/visual-direction.yaml")

# 提取关键字段
scene_name=$(echo "$shot_yaml" | yq eval '.scene_name' -)
time_of_day=$(echo "$shot_yaml" | yq eval '.time_of_day' -)
```

### 2. 检索角色资产

对每个角色，按优先级检索：

**优先级 1: assets/packs/characters/**

检查以下文件是否存在：
- `{角色名}-{variant}-front.png`
- `{角色名}-{variant}-side.png`
- `{角色名}-{variant}-back.png`
- `{角色名}-{variant}-3quarter.png`

**优先级 2: assets/characters/images/**

如果 packs 不存在，检查：
- `{角色名}-{variant}-front.png`
- `{角色名}-{variant}.png`（无 variant 后缀）

**降级策略**:

如果指定 variant 不存在，尝试 `default` 变体：
- `{角色名}-default-front.png`
- `{角色名}-front.png`

**实现示例**:

```bash
characters_json="[]"

# 读取角色列表
echo "$shot_yaml" | yq eval '.references.characters[] | @json' - | while IFS= read -r char_entry; do
  char_name=$(echo "$char_entry" | jq -r '.name')
  variant=$(echo "$char_entry" | jq -r '.variant_id')
  
  assets="[]"
  
  # 优先级 1: packs（多视角）
  for view in front side back 3quarter; do
    pack_path="assets/packs/characters/${char_name}-${variant}-${view}.png"
    if [ -f "$pack_path" ]; then
      assets=$(echo "$assets" | jq --arg path "$pack_path" '. += [{"path": $path, "type": "pack", "priority": 1}]')
    fi
  done
  
  # 优先级 2: images（如果 packs 为空）
  if [ "$(echo "$assets" | jq 'length')" -eq 0 ]; then
    for suffix in "${variant}-front" "${variant}" "default-front" "front"; do
      img_path="assets/characters/images/${char_name}-${suffix}.png"
      if [ -f "$img_path" ]; then
        assets=$(echo "$assets" | jq --arg path "$img_path" '. += [{"path": $path, "type": "image", "priority": 2}]')
        break
      fi
    done
  fi
  
  characters_json=$(echo "$characters_json" | jq \
    --arg name "$char_name" \
    --arg variant "$variant" \
    --argjson assets "$assets" \
    '. += [{"name": $name, "variant": $variant, "assets": $assets}]')
done
```

### 3. 检索场景资产

**优先级 1: assets/packs/scenes/**

检查：
- `{场景名}-{time_of_day}-styleframe.png`
- `{场景名}-{time_of_day}-wide.png`

**优先级 2: assets/scenes/images/**

检查：
- `{场景名}-{time_of_day}.png`

**降级策略**:

如果指定时段不存在，尝试其他时段（按相似度排序）：
- night → dusk → day → dawn
- day → dawn → dusk → night
- dusk → night → dawn → day
- dawn → day → dusk → night

**实现示例**:

```bash
scenes_json="[]"
assets="[]"

# 优先级 1: packs
for suffix in styleframe wide; do
  pack_path="assets/packs/scenes/${scene_name}-${time_of_day}-${suffix}.png"
  if [ -f "$pack_path" ]; then
    assets=$(echo "$assets" | jq --arg path "$pack_path" '. += [{"path": $path, "type": "pack", "priority": 1}]')
  fi
done

# 优先级 2: images（如果 packs 为空）
if [ "$(echo "$assets" | jq 'length')" -eq 0 ]; then
  img_path="assets/scenes/images/${scene_name}-${time_of_day}.png"
  if [ -f "$img_path" ]; then
    assets=$(echo "$assets" | jq --arg path "$img_path" '. += [{"path": $path, "type": "image", "priority": 2}]')
  else
    # 降级：尝试其他时段
    for fallback_time in dusk day dawn night; do
      [ "$fallback_time" = "$time_of_day" ] && continue
      img_path="assets/scenes/images/${scene_name}-${fallback_time}.png"
      if [ -f "$img_path" ]; then
        assets=$(echo "$assets" | jq --arg path "$img_path" '. += [{"path": $path, "type": "image", "priority": 3}]')
        break
      fi
    done
  fi
fi

scenes_json=$(jq -n \
  --arg name "$scene_name" \
  --arg time "$time_of_day" \
  --argjson assets "$assets" \
  '[{"name": $name, "time_of_day": $time, "assets": $assets}]')
```

### 4. 提取前一镜结尾帧

如果 shot_index > 1，提取前一镜的最后一帧：

```bash
prev_shot_json="null"

if [ "$shot_index" -gt 1 ]; then
  prev_shot_num=$(printf '%02d' $((shot_index - 1)))
  prev_shot_id="${ep}-shot-${prev_shot_num}"
  prev_video="outputs/${ep}/videos/shot-${prev_shot_num}.mp4"
  
  if [ -f "$prev_video" ]; then
    mkdir -p "outputs/${ep}/storyboard"
    end_frame="outputs/${ep}/storyboard/${prev_shot_id}-end-frame.png"
    
    # 提取最后一帧（使用 sseof 从结尾倒数）
    ffmpeg -sseof -1 -i "$prev_video" -update 1 -q:v 1 "$end_frame" -y 2>/dev/null
    
    if [ -f "$end_frame" ]; then
      prev_shot_json=$(jq -n \
        --arg shot_id "$prev_shot_id" \
        --arg frame "$end_frame" \
        '{"shot_id": $shot_id, "end_frame": $frame}')
    fi
  fi
fi
```

### 5. 排序和过滤

按优先级排序：
1. pack 资产（priority=1）
2. 单视角资产（priority=2）
3. 降级资产（priority=3）

对于每个角色/场景，最多保留 top-K 个资产（K=3）。

```bash
# 在 jq 中排序和限制数量
characters_json=$(echo "$characters_json" | jq '[.[] | .assets |= (sort_by(.priority) | .[0:3])]')
scenes_json=$(echo "$scenes_json" | jq '[.[] | .assets |= (sort_by(.priority) | .[0:3])]')
```

### 6. 输出 JSON

使用 `jq` 组装最终 JSON 输出：

```bash
jq -n \
  --arg shot_id "$shot_id" \
  --argjson characters "$characters_json" \
  --argjson scenes "$scenes_json" \
  --argjson prev_shot "$prev_shot_json" \
  '{
    shot_id: $shot_id,
    references: {
      characters: $characters,
      scenes: $scenes,
      previous_shot: $prev_shot
    }
  }'
```

## 错误处理

- 如果 shot_id 不存在于 visual-direction.yaml → 退出并报错
- 如果所有优先级都找不到资产 → 记录警告，返回空数组
- 如果 ffmpeg 提取失败 → 记录警告，跳过前一镜结尾帧
- 如果 visual-direction.yaml 格式错误 → 退出并报错

## Trace 写入

在每个关键步骤调用 `./scripts/trace.sh` 记录过程日志：

```bash
# 读取输入
./scripts/trace.sh "$session_id" "${ep}-memory-trace" read_input "{\"shot_id\":\"$shot_id\"}"

# 检索角色
./scripts/trace.sh "$session_id" "${ep}-memory-trace" retrieve_characters "{\"count\":$char_count,\"found\":$found_count}"

# 检索场景
./scripts/trace.sh "$session_id" "${ep}-memory-trace" retrieve_scene "{\"found\":true}"

# 检索前一帧
./scripts/trace.sh "$session_id" "${ep}-memory-trace" retrieve_prev_frame "{\"found\":true}"

# 输出结果
./scripts/trace.sh "$session_id" "${ep}-memory-trace" output_refs "{\"total_refs\":$total_refs}"
```

## 完成后

输出 JSON 到 stdout，供 shot-compiler-agent 使用。

不需要向 team-lead 发送消息（memory-agent 是内部工具，由 shot-compiler-agent 调用）。

## 注意事项

- **缓存机制**：相同 shot 的检索结果可缓存（可选优化）
- **Fallback 策略**：优先使用 packs，不存在则使用 images，最后降级到其他变体/时段
- **前一帧提取**：需要 ffmpeg 工具，使用 `-sseof -1` 从结尾倒数提取
- **相关性评分**：通过 priority 字段标记，1=最高，3=降级
- **Top-K 限制**：每个角色/场景最多保留 3 个资产，避免过多参考图

