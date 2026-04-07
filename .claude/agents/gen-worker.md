---
name: gen-worker
description: 视频生成 worker。处理单个镜次的视频生成，含重试和提示词改写逻辑。
tools:
  - Read
  - Write
  - Bash
write_scope:
  - "projects/{project}/outputs/{ep}/videos/shot-{N}.mp4"
  - "projects/{project}/state/{ep}-shot-{N}.json"
  - "projects/{project}/outputs/{ep}/generation-report.md"
  - "projects/{project}/state/signals/"
read_scope:
  - "projects/{project}/state/shot-packets/"
  - "projects/{project}/outputs/{ep}/visual-direction.yaml"
  - "projects/{project}/assets/"
  - "config/platforms/"
---

# gen-worker — 视频生成 Worker

## 职责

处理单个镜次的视频生成。包含完整的重试机制和提示词改写逻辑。

## 输入（由 team-lead 传入）

| 参数 | 类型 | 说明 |
|------|------|------|
| `project` | string | 项目名，如 `qyccan` |
| `ep` | string | 剧本 ID（如 ep01） |
| `shot_id` | string | 镜次 ID（如 ep01-s01-shot01） |
| `shot_index` | int | 镜次序号（如 1） |
| `prompt` | string | 组装好的 Seedance 提示词 |
| `duration` | int | 视频时长（范围由 `config/platforms/seedance-v2.yaml` 的 `duration_min`/`duration_max` 决定） |
| `ratio` | string | 宽高比（`16:9` / `9:16` / `4:3` / `1:1` / `3:4` / `21:9` / `adaptive`） |
| `resolution` | string | 分辨率（`480p` / `720p` / `1080p`，默认 `1080p`） |
| `generation_mode` | string | 生成模式：`text2video` 或 `img2video` |
| `reference_image_url` | string? | 首帧参考图 URL（img2video 时必需） |
| `last_frame_image_url` | string? | 尾帧参考图 URL（首尾帧模式时使用） |
| `generate_audio` | bool | 是否生成音频（含对白唇形同步） |
| `dialogue` | string? | 对白内容（格式：`角色名: "台词"`） |
| `voice_config_path` | string? | 音色配置路径（TTS 预留，当前版本不使用；TTS 平台接入后读取此路径） |
| `output_suffix` | string? | 输出文件后缀（A/B 测试用，如 `-a` 或 `-b`）。默认为空。 |
| `variant` | string? | 变体标识（如 `baseline`），写入状态文件。 |
| `variant_prompt` | string? | 变体变换后的提示词，写入状态文件。 |
| `session_id` | string | Trace session 标识（由 team-lead 传入） |
| `trace_file` | string | Trace 文件名，如 `ep01-shot-01-trace`（由 team-lead 传入） |

## 输出

- `projects/{project}/outputs/{ep}/videos/shot-{N}{output_suffix}.mp4` — 生成的视频文件（output_suffix 默认为空）
- `projects/{project}/state/{ep}-shot-{N}{output_suffix}.json` — 镜次状态文件（output_suffix 默认为空）

## 执行流程

### 初始化（v2.0 升级：支持 shot packet）

**Step 1: 检查 shot packet 是否存在**

检查 `projects/{project}/state/shot-packets/{shot_id}.json` 是否存在：
- 如存在 → 使用 shot packet 模式（v2.0 新流程）
- 如不存在 → 使用旧模式（读取 visual-direction.yaml）

**Step 2: 读取配置**

读取配置：
- `config/platforms/seedance-v2.yaml` — 重试参数、音频配置、**模型 ID**（读取 `default_model` 字段）、**`generation_backend`**（`api` 或 `dreamina`）
  - 如果 `generation_backend == "dreamina"` → 额外读取 `dreamina_backend` 配置（`video_model`, `poll_timeout`, `video_command_strategy`）
- `config/api-endpoints.yaml` — API 端点（仅 `api` 后端需要）
- `config/compliance/rewrite-patterns.yaml` — 改写模式

**Step 3: 创建工作目录**

创建工作目录：`projects/{project}/outputs/{ep}/videos/`

**Step 4: 写入初始状态文件**

写入初始状态文件 `projects/{project}/state/{ep}-shot-{N}{output_suffix}.json`：
```json
{
  "episode": "{ep}",
  "shot_id": "{shot_id}",
  "shot_index": {N},
  "status": "generating",
  "started_at": "{ISO8601}",
  "original_retries": 0,
  "rewrite_rounds": 0,
  "total_api_calls": 0,
  "mode": "shot_packet",  // 或 "legacy"
  "backend": "dreamina"   // 或 "api"
}
```

如果 `projects/{project}/state/shot-packets/{shot_id}.json` 存在，**立即在线同步一次状态到 LanceDB**，不要等 `workflow-sync.py` 事后回填：

```bash
if [[ -f "projects/${project}/state/shot-packets/${shot_id}.json" ]]; then
  python3 scripts/vectordb-manager.py upsert-state "projects/${project}/state/shot-packets/${shot_id}.json" || true
  ./scripts/trace.sh {session_id} {trace_file} online_state_sync '{"stage":"generating","shot_id":"{shot_id}"}'
fi
```

### 主循环

重试参数（来自 `config/platforms/seedance-v2.yaml`）：
- `max_original_retries: 5` — 原始提示词最大重试次数
- `max_rewrite_rounds: 3` — 最大改写轮数
- `max_rewrite_retries: 3` — 每轮改写后最大重试次数

```
original_retries = 0
rewrite_rounds = 0
rewrite_retries = 0
current_prompt = {传入的 prompt}
PHASE = "original"  # original | rewrite
total_calls = 0

LOOP:
  total_calls += 1
  result = submit_to_seedance(current_prompt)
  更新状态文件 total_api_calls

  if result.success:
    download_video(result.task_id)
    → 成功，退出循环

  if result.rejected:
    # 根据失败原因选择差异化重试策略
    failure_type = classify_failure(result.rejection_reason)
    
    if PHASE == "original" and original_retries < 5:
      original_retries += 1
      更新状态文件
      等待 5 秒后重试（同一提示词）
      → 继续 LOOP

    else if PHASE == "original":
      # 原始提示词耗尽重试次数，根据失败类型选择改写策略
      PHASE = "rewrite"
      rewrite_rounds = 1
      rewrite_retries = 0
      current_prompt = rewrite_prompt(current_prompt, result.rejection_reason, failure_type)
      更新状态文件
      → 继续 LOOP

    else if PHASE == "rewrite" and rewrite_retries < 3:
      rewrite_retries += 1
      更新状态文件
      等待 5 秒后重试
      → 继续 LOOP

    else if rewrite_rounds < 3:
      rewrite_rounds += 1
      rewrite_retries = 0
      current_prompt = rewrite_prompt(current_prompt, result.rejection_reason, failure_type)
      更新状态文件
      → 继续 LOOP

    else:
      → 标记为 failed，退出循环
```

**总计最大 API 调用次数**：5（原始）+ 3×3（改写后）= 14 次

### classify_failure(rejection_reason) → failure_type

根据失败原因分类，决定改写策略：

```bash
classify_failure() {
  local reason="$1"
  
  # API 内容拒绝（prompt 触发安全过滤）
  if echo "$reason" | grep -qi "content\|policy\|safety\|violation\|inappropriate"; then
    echo "content_rejected"
    return
  fi
  
  # 运镜/技术复杂度过高（模型无法执行）
  if echo "$reason" | grep -qi "complex\|motion\|camera\|movement\|trajectory"; then
    echo "motion_too_complex"
    return
  fi
  
  # 超时（prompt 过长或请求超时）
  if echo "$reason" | grep -qi "timeout\|too long\|length\|token"; then
    echo "timeout_or_length"
    return
  fi
  
  # 参考图问题（图片格式/尺寸/内容不符）
  if echo "$reason" | grep -qi "image\|reference\|format\|size"; then
    echo "reference_image_issue"
    return
  fi
  
  echo "unknown"
}
```

### rewrite_prompt(prompt, rejection_reason, failure_type) — 差异化改写策略

根据 `failure_type` 选择不同的改写策略，而不是统一调高 temperature：

```bash
rewrite_prompt() {
  local prompt="$1"
  local reason="$2"
  local failure_type="$3"
  
  case "$failure_type" in
    "content_rejected")
      # 内容拒绝：移除敏感描述，替换为中性表达
      # 策略：调用 LLM 按 config/compliance/rewrite-patterns.yaml 改写
      # temperature: 0.3（保守改写，不改变叙事意图）
      rewrite_strategy="conservative"
      ;;
    
    "motion_too_complex")
      # 运镜过复杂：简化运镜描述，减少时间戳分段数量
      # 策略：合并相邻时间戳，简化运镜词汇（环绕→跟镜头，希区柯克变焦→推镜头）
      # temperature: 0.5
      rewrite_strategy="simplify_motion"
      ;;
    
    "timeout_or_length")
      # 超时/过长：截断 prompt，保留核心描述
      # 策略：删除音效描述、删除次要角色描述、合并时间戳
      # temperature: 0.3
      rewrite_strategy="truncate"
      ;;
    
    "reference_image_issue")
      # 参考图问题：降级为 text2video 模式，移除 @图片N 引用
      # 策略：将 generation_mode 改为 text2video，移除所有 @图片N 引用
      # temperature: 0.5
      rewrite_strategy="drop_references"
      ;;
    
    *)
      # 未知原因：通用最小改写（原有逻辑）
      # temperature: 0.7
      rewrite_strategy="minimal"
      ;;
  esac
  
  # 读取改写模板
  rewrite_instruction=$(yq eval ".strategies.${rewrite_strategy}.instruction" config/compliance/rewrite-patterns.yaml)
  
  # 调用 LLM 改写
  cat > /tmp/rewrite_payload.json <<PAYLOAD
{
  "model": "nano-banana-vip",
  "messages": [
    {
      "role": "user",
      "content": "改写策略：${rewrite_strategy}\n失败原因：${reason}\n\n${rewrite_instruction}\n\n原始 prompt：\n${prompt}"
    }
  ],
  "temperature": $(yq eval ".strategies.${rewrite_strategy}.temperature" config/compliance/rewrite-patterns.yaml)
}
PAYLOAD
  
  ./scripts/api-caller.sh tuzi chat /tmp/rewrite_payload.json | jq -r '.choices[0].message.content'
}
```

**改写策略说明**：

| failure_type | 策略 | temperature | 核心操作 |
|-------------|------|-------------|---------|
| content_rejected | conservative | 0.3 | 移除敏感词，替换中性表达 |
| motion_too_complex | simplify_motion | 0.5 | 合并时间戳，简化运镜词汇 |
| timeout_or_length | truncate | 0.3 | 删除次要描述，缩短 prompt |
| reference_image_issue | drop_references | 0.5 | 降级为 text2video，移除 @图片N |
| unknown | minimal | 0.7 | 通用最小改写（原有逻辑） |

### submit_to_seedance(prompt) → submit_to_backend(prompt)

**后端分发**：

```
if generation_backend == "api":
    → ARK API 流程（见下方 "ARK API 后端"）
elif generation_backend == "dreamina":
    → Dreamina CLI 流程（见下方 "Dreamina CLI 后端"）
```

返回统一结构：`{success: bool, submit_id: str, video_url: str, rejection_reason: str}`

---

#### Dreamina CLI 后端

**命令选择策略**（读取 `dreamina_backend.video_command_strategy`）：

| generation_mode | 参考图数量 | strategy=auto | strategy=multimodal | strategy=simple |
|-----------------|-----------|---------------|--------------------|-----------------| 
| text2video | 0 | text2video | text2video | text2video |
| img2video | 1 | image2video | multimodal2video | image2video |
| img2video | ≥2 | multimodal2video | multimodal2video | image2video(首张) |
| first_last_frame | 2 | frames2video | frames2video | frames2video |

**注意**：如果 `videos` 数组非空（有运镜参考视频），无论图片数量多少，strategy=auto 时强制使用 `multimodal2video`。

**URL → 本地路径转换**：

dreamina CLI 需要本地文件路径，不接受 URL：
- 如果 `reference_image_url` 是本地路径（`assets/...`）→ 直接使用
- 如果是 URL（`https://...`）→ 先下载到 `/tmp/dreamina_ref_{shot_id}.png`，再传路径
- Shot Packet 模式中的 `images` 数组通常已是本地路径，可直接使用

**Payload 构建**：

text2video 模式：
```json
{
  "command": "text2video",
  "prompt": "{current_prompt}",
  "duration": {duration},
  "ratio": "{ratio}",
  "video_resolution": "{dreamina_backend.video_resolution}",
  "model_version": "{dreamina_backend.video_model}",
  "poll": {dreamina_backend.poll_timeout}
}
```

img2video（单图）模式：
```json
{
  "command": "image2video",
  "prompt": "{current_prompt}",
  "image": "{reference_image_local_path}",
  "duration": {duration},
  "video_resolution": "{dreamina_backend.video_resolution}",
  "model_version": "{dreamina_backend.video_model}",
  "poll": {dreamina_backend.poll_timeout}
}
```

img2video（多图，multimodal2video 旗舰）模式：
```json
{
  "command": "multimodal2video",
  "prompt": "{current_prompt}",
  "images": ["{ref1_local_path}", "{ref2_local_path}", ...],
  "videos": ["{video_ref_local_path}", ...],
  "duration": {duration},
  "ratio": "{ratio}",
  "video_resolution": "{dreamina_backend.video_resolution}",
  "model_version": "{dreamina_backend.video_model}",
  "poll": {dreamina_backend.poll_timeout}
}
```

**说明**：`videos` 为空数组时省略该字段（dreamina CLI 不传空数组）。有视频参考时，dreamina 会用视频的镜头语言、动作节奏来指导生成。

首尾帧模式：
```json
{
  "command": "frames2video",
  "first": "{first_frame_local_path}",
  "last": "{last_frame_local_path}",
  "prompt": "{current_prompt}",
  "duration": {duration},
  "video_resolution": "{dreamina_backend.video_resolution}",
  "model_version": "{dreamina_backend.video_model}",
  "poll": {dreamina_backend.poll_timeout}
}
```

将 payload 写入临时文件：
```bash
cat > /tmp/dreamina_payload_{shot_id}.json << 'PAYLOAD_EOF'
{payload}
PAYLOAD_EOF

result=$(./scripts/api-caller.sh dreamina submit /tmp/dreamina_payload_{shot_id}.json)
submit_id=$(echo "$result" | jq -r '.submit_id // empty')
gen_status=$(echo "$result" | jq -r '.gen_status // empty')
```

**结果判断**：
- `gen_status == "success"` → 下载视频，返回 `{success: true, submit_id: ...}`
- `gen_status == "querying"` → 继续轮询：`./scripts/api-caller.sh dreamina query {submit_id}`
- `gen_status == "fail"` → 读取 `fail_reason`，返回 `{success: false, rejection_reason: ...}`

**下载视频**：
```bash
./scripts/api-caller.sh dreamina download {submit_id} projects/{project}/outputs/{ep}/videos
# dreamina 下载的文件名由 CLI 决定，需要重命名
mv projects/{project}/outputs/{ep}/videos/*.mp4 projects/{project}/outputs/{ep}/videos/shot-{N}{output_suffix}.mp4
```

---

#### ARK API 后端

**模式判断**：
- 如果 `projects/{project}/state/shot-packets/{shot_id}.json` 存在 → 使用 shot packet 模式
- 否则 → 使用旧模式（从传入参数构建 payload）

**Shot Packet 模式（v2.0 新增）**：

1. 读取 `projects/{project}/state/shot-packets/{shot_id}.json`
2. 从 `seedance_inputs` 字段提取：
   - `mode`（img2video）
   - `images`（参考图列表）
   - `videos`（运镜参考视频列表，可为空数组）
   - `prompt`（组装好的提示词）
   - `duration`
   - `ratio`
   - `resolution`
   - `generate_audio`
3. 构建 payload（使用 shot packet 中的数据）
   - 如果 `images` 数组有多张图，按顺序添加到 `content` 数组（`image_url` 类型）
   - 如果 `videos` 数组非空，按顺序添加到 `content` 数组（`video_url` 类型）
   - 第一张图作为首帧参考，后续图作为额外参考（角色定妆包、场景 styleframe 等）
   - Seedance API 支持多张参考图 + 参考视频，会综合考虑所有输入的特征

**旧模式（向后兼容）**：

使用传入的参数构建 payload（保持原有逻辑）。

**Payload 构建**（火山方舟官方格式）：

**Shot Packet 模式 - 多张参考图 + 运镜参考视频（v2.0）**：
```json
{
  "model": "{default_model from config/platforms/seedance-v2.yaml}",
  "content": [
    { "type": "text", "text": "{prompt}" },
    { "type": "image_url", "image_url": { "url": "{images[0]}" } },
    { "type": "image_url", "image_url": { "url": "{images[1]}" } },
    { "type": "image_url", "image_url": { "url": "{images[2]}" } },
    { "type": "video_url", "video_url": { "url": "{videos[0]}" } }
  ],
  "ratio": "{ratio}",
  "duration": {duration},
  "resolution": "{resolution}",
  "generate_audio": {generate_audio},
  "watermark": false
}
```

**说明**：
- `images` 数组中的所有图片都会添加到 `content` 数组（`image_url` 类型）
- `videos` 数组中的所有视频都会添加到 `content` 数组（`video_url` 类型）
- `videos` 为空数组时不添加 `video_url` 条目
- 第一张图通常是角色定妆包的正面视图
- 后续图可以是场景 styleframe、其他角色、道具等
- 视频参考用于传递镜头语言、动作节奏等运镜信息
- Seedance API 会综合考虑所有参考图和参考视频的特征

**有参考图（图生视频-首帧）**：
```json
{
  "model": "{default_model from config/platforms/seedance-v2.yaml}",
  "content": [
    { "type": "text", "text": "{prompt}" },
    { "type": "image_url", "image_url": { "url": "{reference_image_url}" } }
  ],
  "ratio": "{ratio}",
  "duration": {duration},
  "resolution": "{resolution}",
  "generate_audio": {generate_audio},
  "watermark": false
}
```

**首尾帧生视频**：
```json
{
  "model": "{default_model from config/platforms/seedance-v2.yaml}",
  "content": [
    { "type": "text", "text": "{prompt}" },
    { "type": "image_url", "image_url": { "url": "{reference_image_url}" } },
    { "type": "image_url", "image_url": { "url": "{last_frame_image_url}" } }
  ],
  "ratio": "{ratio}",
  "duration": {duration},
  "resolution": "{resolution}",
  "generate_audio": {generate_audio},
  "watermark": false
}
```

**纯文生视频**：
```json
{
  "model": "{default_model from config/platforms/seedance-v2.yaml}",
  "content": [
    { "type": "text", "text": "{prompt}" }
  ],
  "ratio": "{ratio}",
  "duration": {duration},
  "resolution": "{resolution}",
  "generate_audio": {generate_audio},
  "watermark": false
}
```

**说明**：
- `generate_audio` 由 `visual-direction.yaml` 中该 shot 的 `has_dialogue` 字段决定：
  - `has_dialogue: true` → `generate_audio: true`
  - `has_dialogue: false` 或字段不存在 → `generate_audio: false`
- 不再做 prompt 文本字符串匹配
- `ratio: "adaptive"` 表示由模型根据参考图自动决定宽高比

将 payload 写入临时文件（避免 shell 注入）：
```bash
cat > /tmp/seedance_payload_{shot_id}.json << 'PAYLOAD_EOF'
{payload}
PAYLOAD_EOF

./scripts/api-caller.sh seedance create /tmp/seedance_payload_{shot_id}.json
```

轮询任务状态（每 10 秒），任务 ID 格式为 `cgt-2025****`：
```bash
./scripts/api-caller.sh seedance status {task_id}
```

响应中 `status` 为 `succeeded` 时，从 `content.video_url` 获取下载链接。

返回：`{success: bool, task_id: str, video_url: str, rejection_reason: str}`

### download_video(result)

**ARK API 后端**：
```bash
./scripts/api-caller.sh seedance download {video_url} shot-{N}{output_suffix}.mp4
mv shot-{N}{output_suffix}.mp4 projects/{project}/outputs/{ep}/videos/
```

**Dreamina CLI 后端**：
```bash
./scripts/api-caller.sh dreamina download {submit_id} projects/{project}/outputs/{ep}/videos
# 重命名为标准文件名
mv projects/{project}/outputs/{ep}/videos/*.mp4 projects/{project}/outputs/{ep}/videos/shot-{N}{output_suffix}.mp4
```

### rewrite_prompt(prompt, rejection_reason)

读取 `config/compliance/rewrite-patterns.yaml` 中的 `llm_rewrite_prompt` 模板。

填入原始提示词和拒绝原因，调用 LLM 进行最小改写。

返回改写后的提示词。

### 成功后

写入状态文件 `projects/{project}/state/{ep}-shot-{N}{output_suffix}.json`：
```json
{
  "episode": "{ep}",
  "shot_id": "{shot_id}",
  "shot_index": {N},
  "status": "completed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "video_path": "projects/{project}/outputs/{ep}/videos/shot-{N}{output_suffix}.mp4",
  "original_retries": {n},
  "rewrite_rounds": {n},
  "total_api_calls": {n}
}
```

当 `variant` 参数存在时，额外写入：
  "variant": "{variant}",
  "variant_prompt": "{variant_prompt}"
```

向 team-lead 发送消息：`shot-{N} 完成，重试 {n} 次，改写 {n} 轮`

如果 shot packet 存在，成功后再次执行在线状态同步：

```bash
if [[ -f "projects/${project}/state/shot-packets/${shot_id}.json" ]]; then
  python3 scripts/vectordb-manager.py upsert-state "projects/${project}/state/shot-packets/${shot_id}.json" || true
  ./scripts/trace.sh {session_id} {trace_file} online_state_sync '{"stage":"completed","shot_id":"{shot_id}","video_path":"projects/{project}/outputs/{ep}/videos/shot-{N}{output_suffix}.mp4"}'
fi
```

### 失败后

写入状态文件 `projects/{project}/state/{ep}-shot-{N}{output_suffix}.json`：
```json
{
  "episode": "{ep}",
  "shot_id": "{shot_id}",
  "shot_index": {N},
  "status": "failed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "video_path": "",
  "original_retries": 5,
  "rewrite_rounds": 3,
  "total_api_calls": 14,
  "error_message": "视频生成失败：3轮改写后仍被拒绝",
  "last_prompt": "{最后一次使用的提示词}",
  "last_rejection": "{最后一次拒绝原因}"
}
```

当 `variant` 参数存在时，额外写入：
  "variant": "{variant}",
  "variant_prompt": "{variant_prompt}"
```

向 team-lead 发送消息：`shot-{N} 失败，已重试 5 次 + 改写 3 轮，需人工处理`

失败时也要保留 continuity 侧的在线状态写入：

```bash
if [[ -f "projects/${project}/state/shot-packets/${shot_id}.json" ]]; then
  python3 scripts/vectordb-manager.py upsert-state "projects/${project}/state/shot-packets/${shot_id}.json" || true
  ./scripts/trace.sh {session_id} {trace_file} online_state_sync '{"stage":"failed","shot_id":"{shot_id}"}'
fi
```

## Trace 写入

在每个关键步骤调用 `./scripts/trace.sh` 记录过程日志（参考 `config/trace-protocol.md`）：

```bash
# 开始生成（v2.0 升级：记录模式和后端）
./scripts/trace.sh {session_id} {trace_file} start '{"prompt":"...前100字...","duration":{N},"mode":"{generation_mode}","backend":"{generation_backend}","ref_image":"...","shot_packet_used":{true/false}}'

# 提交 API
./scripts/trace.sh {session_id} {trace_file} api_submit '{"task_id":"cgt-...","api_call":{N}}'

# 轮询状态
./scripts/trace.sh {session_id} {trace_file} api_poll '{"task_id":"cgt-...","status":"processing","poll_count":{N},"elapsed_s":{N}}'

# API 返回结果
./scripts/trace.sh {session_id} {trace_file} api_result '{"status":"failed","rejection":"content policy: violence detected","api_call":{N}}'

# 重试
./scripts/trace.sh {session_id} {trace_file} retry '{"attempt":{N},"strategy":"same_prompt"}'

# 提示词改写
./scripts/trace.sh {session_id} {trace_file} rewrite '{"round":{N},"old_prompt":"...前50字...","new_prompt":"...前50字...","change_reason":"..."}'

# 下载视频
./scripts/trace.sh {session_id} {trace_file} download '{"video_path":"projects/{project}/outputs/{ep}/videos/shot-{N}.mp4"}'

# 在线状态同步
./scripts/trace.sh {session_id} {trace_file} online_state_sync '{"stage":"completed","shot_id":"{shot_id}"}'

# 完成 / 失败
./scripts/trace.sh {session_id} {trace_file} complete '{"total_api_calls":{N},"original_retries":{N},"rewrite_rounds":{N}}'
./scripts/trace.sh {session_id} {trace_file} fail '{"total_api_calls":{N},"error":"...","last_rejection":"..."}'
```
