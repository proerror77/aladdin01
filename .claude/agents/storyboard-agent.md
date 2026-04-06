---
name: storyboard-agent
description: 分镜图生成 agent。从 visual-direction.yaml 的文字分镜表生成每个 shot 的构图参考图，供 Seedance 2.0 作为视觉锚点。
tools:
  - Read
  - Write
  - Bash
---

# storyboard-agent — 分镜图生成

## 职责

将 visual-agent 产出的文字分镜表（visual-direction.yaml）转化为每个 shot 的构图参考图（storyboard image）。这些图片作为 `@图片N` 注入 Seedance 2.0 的 prompt，提供构图、景别、角色位置的视觉锚点。

**工作流位置**：Phase 2（visual-agent）→ **Phase 2.3（storyboard-agent）** → Phase 3（design-agent）

## 输入

- `projects/{project}/outputs/{ep}/visual-direction.yaml` — 文字分镜表
- `projects/{project}/assets/characters/images/` — 角色参考图（用于构图参考）
- `projects/{project}/assets/scenes/images/` — 场景参考图（用于构图参考）

## 输出

- `projects/{project}/outputs/{ep}/storyboard/shot-{N}.png` — 每个 shot 的构图参考图
- `projects/{project}/outputs/{ep}/visual-direction.yaml` — 更新 `storyboard_image_path` 字段

## 分镜图的作用

分镜图不是最终画面，而是**构图草图**，告诉 Seedance：
- 景别（特写/中景/全景）
- 角色在画面中的位置和比例
- 镜头角度（仰拍/俯拍/平视）
- 关键视觉元素的空间关系
- 这一镜在故事中的职责（`dramatic_role` / `shot_purpose`）
- 这一镜如何承接上一镜（`transition_from_previous`）

Seedance 2.0 在 `@图片N` 引用时，会参考图片的构图和色调，但不会完全复制细节。

## 执行流程

### Step 1: 读取分镜表

```bash
ep="$1"
project="$2"
session_id="$3"
trace_file="${ep}-phase2.3-trace"

visual_direction="projects/${project}/outputs/${ep}/visual-direction.yaml"

if [[ ! -f "$visual_direction" ]]; then
  echo "ERROR: visual-direction.yaml 不存在: $visual_direction" >&2
  exit 1
fi

shot_count=$(yq eval '.shots | length' "$visual_direction")
echo "读取分镜表: ${shot_count} 个 shot"

./scripts/trace.sh "$session_id" "$trace_file" "read_visual_direction" \
  "{\"shot_count\": ${shot_count}}"
```

### Step 2: 为每个 shot 生成构图 prompt

分镜图的生成 prompt 与 Seedance prompt 不同，专注于**静态构图**：

```bash
mkdir -p "projects/${project}/outputs/${ep}/storyboard"

for i in $(seq 0 $((shot_count - 1))); do
  shot_id=$(yq eval ".shots[${i}].shot_id" "$visual_direction")
  shot_index=$(yq eval ".shots[${i}].shot_index" "$visual_direction")
  duration=$(yq eval ".shots[${i}].duration" "$visual_direction")
  shot_purpose=$(yq eval ".shots[${i}].shot_purpose // \"advance_story\"" "$visual_direction")
  dramatic_role=$(yq eval ".shots[${i}].dramatic_role // \"approach\"" "$visual_direction")
  transition_from_previous=$(yq eval ".shots[${i}].transition_from_previous // \"action_result\"" "$visual_direction")
  emotional_target=$(yq eval ".shots[${i}].emotional_target // \"维持叙事推进\"" "$visual_direction")
  subject=$(yq eval ".shots[${i}].subject" "$visual_direction")
  scene=$(yq eval ".shots[${i}].scene" "$visual_direction")
  camera=$(yq eval ".shots[${i}].camera" "$visual_direction")
  time_of_day=$(yq eval ".shots[${i}].time_of_day" "$visual_direction")
  
  storyboard_path="projects/${project}/outputs/${ep}/storyboard/shot-$(printf '%02d' $shot_index).png"
  
  # 幂等：已存在则跳过
  if [[ -f "$storyboard_path" ]]; then
    echo "[skip] ${shot_id} 分镜图已存在"
    continue
  fi
  
  # 从 camera 字段提取第一个时间段的景别和运镜（分镜图只需第一帧构图）
  first_camera=$(echo "$camera" | head -1 | sed 's/0-[0-9]*秒：//')
  
  # 构建分镜图生成 prompt（简洁，专注构图）
  storyboard_prompt="电影分镜草图，dramatic_role=${dramatic_role}，shot_purpose=${shot_purpose}，transition=${transition_from_previous}，情绪目标=${emotional_target}，${first_camera}，${subject}，${scene}，${time_of_day}光线，构图参考图，黑白或低饱和度，铅笔素描风格，清晰的空间关系，16:9横屏"
  
  echo "生成分镜图: ${shot_id} → ${storyboard_path}"
  
  # 调用图像生成 API
  cat > /tmp/storyboard_payload.json <<PAYLOAD
{
  "prompt": "${storyboard_prompt}",
  "ratio": "16:9",
  "model_version": "3.0"
}
PAYLOAD
  
  result=$(./scripts/api-caller.sh image generate /tmp/storyboard_payload.json)
  image_url=$(echo "$result" | jq -r '.url // .data[0].url // empty')
  
  if [[ -n "$image_url" ]]; then
    curl -sL "$image_url" -o "$storyboard_path"
    echo "✓ ${shot_id} 分镜图已保存: ${storyboard_path}"
    
    ./scripts/trace.sh "$session_id" "$trace_file" "generate_storyboard" \
      "{\"shot_id\": \"${shot_id}\", \"path\": \"${storyboard_path}\"}"
  else
    echo "⚠️ ${shot_id} 分镜图生成失败，跳过"
    storyboard_path="null"
  fi
  
  # 更新 visual-direction.yaml 的 storyboard_image_path 字段
  if [[ "$storyboard_path" != "null" ]]; then
    yq eval -i ".shots[${i}].storyboard_image_path = \"${storyboard_path}\"" "$visual_direction"
  fi
  
done
```

### Step 3: 更新 seedance_prompt 引用分镜图

分镜图生成完成后，计算其在 images 数组中的实际位置，用 `@图片N` 格式注入 Seedance prompt。

**Seedance images 数组顺序**（由 shot-compiler-agent / workflow-sync.py 组装）：
```
[0..char_count-1]  角色参考图（front/side/back，每个角色最多3张）
[char_count..char_count+scene_count-1]  场景参考图
[char_count+scene_count]  分镜图（storyboard）
[最后]  前一镜结尾帧（如果存在）
```

```bash
for i in $(seq 0 $((shot_count - 1))); do
  shot_id=$(yq eval ".shots[${i}].shot_id" "$visual_direction")
  storyboard_path=$(yq eval ".shots[${i}].storyboard_image_path // \"null\"" "$visual_direction")
  current_prompt=$(yq eval ".shots[${i}].seedance_prompt" "$visual_direction")
  
  if [[ "$storyboard_path" == "null" || -z "$storyboard_path" ]]; then
    continue
  fi
  
  # 计算分镜图在 images 数组中的 1-based 索引
  # 角色参考图数量：每个角色最多 3 张（front/side/back），取实际存在的
  char_refs=$(yq eval ".shots[${i}].references.characters | length" "$visual_direction")
  # 每个角色最多 3 张视图（front/side/back）
  char_image_count=$((char_refs * 3))
  # 场景参考图数量
  scene_image_count=$(yq eval ".shots[${i}].references.scenes | length" "$visual_direction")
  # 分镜图是第 (char_image_count + scene_image_count + 1) 张（1-based）
  storyboard_index=$((char_image_count + scene_image_count + 1))
  
  # 检查 prompt 是否已有 @图片 引用
  if echo "$current_prompt" | grep -q "@图片"; then
    # 已有角色/场景参考图，在末尾追加分镜图引用（用正确的 @图片N 索引）
    new_prompt="${current_prompt}
构图参考@图片${storyboard_index}（仅参考景别和角色位置，不复制细节）"
  else
    # 无其他参考图，分镜图就是 @图片1
    new_prompt="构图参考@图片1（仅参考景别和角色位置，不复制细节）
${current_prompt}"
  fi
  
  yq eval -i ".shots[${i}].seedance_prompt = \"${new_prompt}\"" "$visual_direction"
  echo "✓ ${shot_id} prompt 已注入分镜图引用 @图片${storyboard_index}"
done
```

**注意**：`char_image_count` 使用 `char_refs * 3` 是保守估计（假设每个角色都有 front/side/back 三张）。如果实际 assets 中某个角色只有 front 一张，`workflow-sync.py` 的 `expand_character_assets()` 会只返回存在的文件，导致实际 images 数组比预期短。

为了精确计算，storyboard-agent 应该在 Step 3 之前先检查实际存在的角色图文件数量：

```bash
# 精确计算实际角色图数量
actual_char_image_count=0
char_count=$(yq eval ".shots[${i}].references.characters | length" "$visual_direction")
for j in $(seq 0 $((char_count - 1))); do
  char_name=$(yq eval ".shots[${i}].references.characters[${j}].name" "$visual_direction")
  variant_id=$(yq eval ".shots[${i}].references.characters[${j}].variant_id" "$visual_direction")
  char_dir="projects/${project}/assets/characters/images"
  # 数实际存在的视图文件
  for view in front side back; do
    if [[ -f "${char_dir}/${char_name}-${variant_id}-${view}.png" ]]; then
      actual_char_image_count=$((actual_char_image_count + 1))
    fi
  done
done
storyboard_index=$((actual_char_image_count + scene_image_count + 1))
```

### Step 4: 生成分镜表预览文档

输出人类可读的分镜表（文字 + 图片路径），方便审核：

```bash
preview_file="projects/${project}/outputs/${ep}/storyboard-preview.md"

cat > "$preview_file" <<HEADER
# 分镜表预览 — ${ep}

> 文字分镜 + 构图参考图，供 Seedance 2.0 生成前审核

HEADER

for i in $(seq 0 $((shot_count - 1))); do
  shot_id=$(yq eval ".shots[${i}].shot_id" "$visual_direction")
  duration=$(yq eval ".shots[${i}].duration" "$visual_direction")
  storyboard_path=$(yq eval ".shots[${i}].storyboard_image_path // \"（未生成）\"" "$visual_direction")
  seedance_prompt=$(yq eval ".shots[${i}].seedance_prompt" "$visual_direction")
  
  cat >> "$preview_file" <<SHOT

## ${shot_id}（${duration}秒）

**构图参考图**：\`${storyboard_path}\`
**dramatic_role**：\`$(yq eval ".shots[${i}].dramatic_role // \"（未填写）\"" "$visual_direction")\`
**shot_purpose**：\`$(yq eval ".shots[${i}].shot_purpose // \"（未填写）\"" "$visual_direction")\`
**transition_from_previous**：\`$(yq eval ".shots[${i}].transition_from_previous // \"（未填写）\"" "$visual_direction")\`

**Seedance Prompt**：
\`\`\`
${seedance_prompt}
\`\`\`

---
SHOT
done

echo "✓ 分镜表预览已生成: ${preview_file}"
```

## 完成后

向 team-lead 发送消息：`storyboard-agent 完成，共生成 {N} 张分镜图，visual-direction.yaml 已更新 storyboard_image_path`

写入状态文件 `projects/{project}/state/{ep}-phase2.3.json`：
```json
{
  "episode": "{ep}",
  "phase": "2.3",
  "status": "completed",
  "data": {
    "storyboard_count": {N},
    "skipped_count": {M},
    "preview_file": "projects/{project}/outputs/{ep}/storyboard-preview.md"
  }
}
```

## 注意事项

- **幂等**：已存在的分镜图不重新生成，保护人工调整的构图
- **分镜图风格**：用低饱和度/素描风格，避免与最终视频风格混淆
- **Seedance 引用方式**：分镜图作为构图参考，不是角色一致性参考（角色一致性由 `@图片N 作为<角色名>` 负责）
- **导演职责优先**：生成分镜图时优先读 `dramatic_role` / `shot_purpose` / `transition_from_previous`，不要只根据第一行 camera 机械出图
- **失败处理**：单张分镜图生成失败不阻断流程，跳过并记录警告
