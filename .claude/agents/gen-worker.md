---
name: gen-worker
description: 视频生成 worker。处理单个镜次的视频生成，含重试和提示词改写逻辑。
tools:
  - Read
  - Write
  - Bash
---

# gen-worker — 视频生成 Worker

## 职责

处理单个镜次的视频生成。包含完整的重试机制和提示词改写逻辑。

## 输入（由 team-lead 传入）

| 参数 | 类型 | 说明 |
|------|------|------|
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
| `voice_config_path` | string? | 音色配置路径（TTS 预留） |
| `output_suffix` | string? | 输出文件后缀（A/B 测试用，如 `-a` 或 `-b`）。默认为空。 |
| `variant` | string? | 变体标识（如 `baseline`），写入状态文件。 |
| `variant_prompt` | string? | 变体变换后的提示词，写入状态文件。 |
| `session_id` | string | Trace session 标识（由 team-lead 传入） |
| `trace_file` | string | Trace 文件名，如 `ep01-shot-01-trace`（由 team-lead 传入） |

## 输出

- `outputs/{ep}/videos/shot-{N}{output_suffix}.mp4` — 生成的视频文件（output_suffix 默认为空）
- `state/{ep}-shot-{N}{output_suffix}.json` — 镜次状态文件（output_suffix 默认为空）

## 执行流程

### 初始化（v2.0 升级：支持 shot packet）

**Step 1: 检查 shot packet 是否存在**

检查 `state/shot-packets/{shot_id}.json` 是否存在：
- 如存在 → 使用 shot packet 模式（v2.0 新流程）
- 如不存在 → 使用旧模式（读取 visual-direction.yaml）

**Step 2: 读取配置**

读取配置：
- `config/platforms/seedance-v2.yaml` — 重试参数、音频配置、**模型 ID**（读取 `default_model` 字段）、**`generation_backend`**（`api` 或 `dreamina`）
  - 如果 `generation_backend == "dreamina"` → 额外读取 `dreamina_backend` 配置（`video_model`, `poll_timeout`, `video_command_strategy`）
- `config/api-endpoints.yaml` — API 端点（仅 `api` 后端需要）
- `config/compliance/rewrite-patterns.yaml` — 改写模式

**Step 3: 创建工作目录**

创建工作目录：`outputs/{ep}/videos/`

**Step 4: 写入初始状态文件**

写入初始状态文件 `state/{ep}-shot-{N}{output_suffix}.json`：
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
    if PHASE == "original" and original_retries < 5:
      original_retries += 1
      更新状态文件
      等待 5 秒后重试（同一提示词）
      → 继续 LOOP

    else if PHASE == "original":
      # 原始提示词耗尽重试次数，进入改写阶段
      PHASE = "rewrite"
      rewrite_rounds = 1
      rewrite_retries = 0
      current_prompt = rewrite_prompt(current_prompt, result.rejection_reason)
      更新状态文件
      → 继续 LOOP

    else if PHASE == "rewrite" and rewrite_retries < 3:
      rewrite_retries += 1
      更新状态文件
      等待 5 秒后重试
      → 继续 LOOP

    else if rewrite_rounds < 3:
      # 当前改写版本耗尽重试次数，进行新一轮改写
      rewrite_rounds += 1
      rewrite_retries = 0
      current_prompt = rewrite_prompt(current_prompt, result.rejection_reason)
      更新状态文件
      → 继续 LOOP

    else:
      → 标记为 failed，退出循环
```

**总计最大 API 调用次数**：5（原始）+ 3×3（改写后）= 14 次

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
  "duration": {duration},
  "ratio": "{ratio}",
  "video_resolution": "{dreamina_backend.video_resolution}",
  "model_version": "{dreamina_backend.video_model}",
  "poll": {dreamina_backend.poll_timeout}
}
```

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
./scripts/api-caller.sh dreamina download {submit_id} outputs/{ep}/videos
# dreamina 下载的文件名由 CLI 决定，需要重命名
mv outputs/{ep}/videos/*.mp4 outputs/{ep}/videos/shot-{N}{output_suffix}.mp4
```

---

#### ARK API 后端

**模式判断**：
- 如果 `state/shot-packets/{shot_id}.json` 存在 → 使用 shot packet 模式
- 否则 → 使用旧模式（从传入参数构建 payload）

**Shot Packet 模式（v2.0 新增）**：

1. 读取 `state/shot-packets/{shot_id}.json`
2. 从 `seedance_inputs` 字段提取：
   - `mode`（img2video）
   - `images`（参考图列表）
   - `prompt`（组装好的提示词）
   - `duration`
   - `ratio`
   - `resolution`
   - `generate_audio`
3. 构建 payload（使用 shot packet 中的数据）
   - 如果 `images` 数组有多张图，按顺序添加到 `content` 数组
   - 第一张图作为首帧参考，后续图作为额外参考（角色定妆包、场景 styleframe 等）
   - Seedance API 支持多张参考图，会综合考虑所有参考图的特征

**旧模式（向后兼容）**：

使用传入的参数构建 payload（保持原有逻辑）。

**Payload 构建**（火山方舟官方格式）：

**Shot Packet 模式 - 多张参考图（v2.0）**：
```json
{
  "model": "{default_model from config/platforms/seedance-v2.yaml}",
  "content": [
    { "type": "text", "text": "{prompt}" },
    { "type": "image_url", "image_url": { "url": "{images[0]}" } },
    { "type": "image_url", "image_url": { "url": "{images[1]}" } },
    { "type": "image_url", "image_url": { "url": "{images[2]}" } }
  ],
  "ratio": "{ratio}",
  "duration": {duration},
  "resolution": "{resolution}",
  "generate_audio": {generate_audio},
  "watermark": false
}
```

**说明**：
- `images` 数组中的所有图片都会添加到 `content` 数组
- 第一张图通常是角色定妆包的正面视图
- 后续图可以是场景 styleframe、其他角色、道具等
- Seedance API 会综合考虑所有参考图的特征

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
mv shot-{N}{output_suffix}.mp4 outputs/{ep}/videos/
```

**Dreamina CLI 后端**：
```bash
./scripts/api-caller.sh dreamina download {submit_id} outputs/{ep}/videos
# 重命名为标准文件名
mv outputs/{ep}/videos/*.mp4 outputs/{ep}/videos/shot-{N}{output_suffix}.mp4
```

### rewrite_prompt(prompt, rejection_reason)

读取 `config/compliance/rewrite-patterns.yaml` 中的 `llm_rewrite_prompt` 模板。

填入原始提示词和拒绝原因，调用 LLM 进行最小改写。

返回改写后的提示词。

### 成功后

写入状态文件 `state/{ep}-shot-{N}{output_suffix}.json`：
```json
{
  "episode": "{ep}",
  "shot_id": "{shot_id}",
  "shot_index": {N},
  "status": "completed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "video_path": "outputs/{ep}/videos/shot-{N}{output_suffix}.mp4",
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

### 失败后

写入状态文件 `state/{ep}-shot-{N}{output_suffix}.json`：
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
./scripts/trace.sh {session_id} {trace_file} download '{"video_path":"outputs/{ep}/videos/shot-{N}.mp4"}'

# 完成 / 失败
./scripts/trace.sh {session_id} {trace_file} complete '{"total_api_calls":{N},"original_retries":{N},"rewrite_rounds":{N}}'
./scripts/trace.sh {session_id} {trace_file} fail '{"total_api_calls":{N},"error":"...","last_rejection":"..."}'
```