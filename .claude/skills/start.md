# ~start — 单剧本模式

启动单个剧本的完整生产流水线。

## 使用方式

```
~start                                    # 交互式选择专案和剧本
~start qyccan ep01                        # 直接指定专案和集数
~start --auto-approve                     # 跳过人工审核点，自动通过
~start --auto-approve --ab               # 自动通过 + A/B 测试
```

剧本放在 `projects/{project}/script/` 目录下。

## 前置条件

**推荐**：在运行 `~start` 前先运行 `~design` 生成参考图（角色 + 场景）。

- 如果已运行 `~design`：Phase 3 将校验参考图是否完整（纯校验，不生成图）
- 如果未运行 `~design`：Phase 3 会提示缺失的参考图，需手动运行 `~design` 后再继续

**注意**：`~design` 是可选的，但强烈推荐在批量生产前运行，以确保角色/场景一致性。

### 参数

| 参数 | 说明 |
|------|------|
| `--auto-approve` | 跳过 Phase 2/3 的 🔴 人工确认点，自动通过 |
| `--ab` | 启用 A/B 测试模式 |
| `--auto-voice` | 音色自动匹配（不交互询问用户） |

## 执行流程

### 0. 环境变量预检

在开始前验证所有必需的环境变量：
```bash
./scripts/api-caller.sh env-check
```

检查：
- `ARK_API_KEY`
- `IMAGE_GEN_API_URL`
- `IMAGE_GEN_API_KEY`
- `OPENAI_API_KEY`

如果有缺失：
```
❌ 环境变量缺失：
- ARK_API_KEY
- OPENAI_API_KEY

请设置后再运行 ~start
```

### 1. 选择专案和剧本

**Step 1a: 选择专案**

如果命令行已指定专案（如 `~start qyccan ep01`），直接使用。

否则扫描 `projects/` 目录，列出所有专案：
```
发现以下专案：
1. jiuba（80集）
2. qyccan（10集）
请选择专案（输入数字或名称）：
```

设置 `PROJECT=<选择的专案名>`，后续所有路径均以 `projects/{PROJECT}/` 为根。

**Step 1b: 选择剧本**

扫描 `projects/{PROJECT}/script/` 目录，列出所有 `.md` 文件。

如果命令行已指定集数（如 `ep01`），直接使用。

如果有多个文件，询问用户选择哪个：
```
发现以下剧本：
1. ep01.md
2. ep02.md
请选择（输入数字）：
```

如果只有一个文件，直接使用。

如果没有文件：
```
projects/{PROJECT}/script/ 目录下没有找到剧本文件。
请将剧本放入该目录（.md 格式），然后重新运行 ~start
```

### 2. 交互式配置

**选择视觉风格**：
```
请选择视觉风格：
1. 写实电影感（真人短剧）
2. 国风古装
3. 现代都市
4. 动漫风格
5. 其他（请描述）
```

**选择目标媒介**：
```
请选择目标媒介：
1. 竖屏短视频（9:16，抖音/快手）
2. 横屏视频（16:9，YouTube/B站）
3. 方形（1:1，Instagram）
```

**选择生成模式（v1.0 vs v2.0）**：
```
请选择生成模式：
1. v1.0 — 文生视频（text_to_video，快速，无需资产包）
2. v2.0 — 图生视频（img2video，高质量，需要先运行 ~design 生成参考图）
```

根据选择设置：
```bash
# v1.0 模式（默认）
USE_V2="false"

# v2.0 模式
USE_V2="true"
```

也可通过命令行参数直接指定：
```bash
~start qyccan ep01 --v2    # 启用 v2.0 模式
~start qyccan ep01         # 默认 v1.0 模式
```

### 2.5 A/B 测试模式（可选）

如果用户输入 `~start --ab` 或在交互中回答 yes：

```
是否启用 A/B 测试模式？(yes/no，默认 no)
```

如果启用：
1. 扫描 `config/ab-testing/variants/` 目录，列出所有 `.yaml` 文件（读取每个文件的 `id` 和 `name` 字段）
2. 展示可用变体列表，让用户选择变体 A 和变体 B：
   ```
   可用变体：
   1. baseline — 基线（原始提示词）
   2. cinematic-v1 — 电影感增强 v1

   变体 A（默认 baseline）：
   变体 B：
   ```
3. 记录 `variant_a_id` 和 `variant_b_id`，后续 Phase 5 使用
4. 提示：A/B 模式将使 API 调用量翻倍（每镜次 2 个变体）

### 3. 初始化目录和状态

```bash
mkdir -p projects/{PROJECT}/outputs/{ep}/videos
```

生成 session ID（格式：`start-{YYYYMMDD}-{HHMMSS}`）：
```bash
SESSION_ID="start-$(date +%Y%m%d-%H%M%S)"
```

写入 session 开始事件：
```bash
./scripts/trace.sh $SESSION_ID session session_start '{"type":"start","episodes":["{ep}"],"config":{"visual_style":"...","ratio":"...","backend":"..."}}'
```

初始化 `state/progress.json`：
```json
{
  "version": "1.0",
  "episodes": {
    "{ep}": {
      "status": "in_progress",
      "current_phase": 0
    }
  }
}
```

### 3.5 断点检测（自动 resume）

在启动 Phase 1 前，检查已有状态文件：

```
检查断点状态...

[resume] Phase 1-3 已完成，Phase 4: 音色配置完成
[resume] Phase 5: 8/12 镜次已完成

从 Phase 5 继续（跳过已完成的镜次）
```

检测逻辑：
1. 读取 `projects/{project}/state/{ep}-phase{1-4}.json`，确定已完成的阶段
2. 统计 `projects/{project}/state/{ep}-shot-*.json` 中 `status: completed` 的镜次
3. 从最早未完成的阶段继续

断点续传跳过规则：
- Phase X `status: completed` → 跳过该阶段
- 镜次 `status: completed` 且视频文件存在 → 跳过该镜次

### 4. 启动 Agent Team

创建 team，按顺序执行：

**Phase 0 — 本体论构建（v2.0，可选）**

检查是否需要构建本体论（v2.0 模式）：

```
# 条件：用户选择 v2.0 模式，或 projects/{project}/state/ontology/{ep}-world-model.json 不存在
if [[ "$USE_V2" == "true" && ! -f "projects/{project}/state/ontology/{ep}-world-model.json" ]]; then
  spawn ontology-builder-agent
    输入：projects/{project}/script/{ep}.md + 角色/场景档案
    session_id: $SESSION_ID
    trace_file: {ep}-phase0-trace
    输出：projects/{project}/state/ontology/{ep}-world-model.json
    等待完成
else
  echo "[skip] Phase 0: world-model.json 已存在或非 v2.0 模式，跳过"
fi
```

**Phase 1 — 合规预检**
```
spawn comply-agent
  输入：projects/{project}/script/{ep}.md
  session_id: $SESSION_ID
  trace_file: {ep}-phase1-trace
  输出：projects/{project}/outputs/{ep}/render-script.md（合规后的剧本）
  等待完成
```

spawn 前写入 trace：`./scripts/trace.sh $SESSION_ID session spawn '{"agent":"comply-agent","ep":"{ep}","phase":1}'`
完成后写入 trace：`./scripts/trace.sh $SESSION_ID session complete '{"agent":"comply-agent","ep":"{ep}","phase":1,"duration_s":{N},"summary":"..."}'`

**Phase 2 — 视觉指导**
```
spawn visual-agent
  输入：projects/{project}/outputs/{ep}/render-script.md + 视觉风格 + 目标媒介
  session_id: $SESSION_ID
  trace_file: {ep}-phase2-trace
  等待完成
```

**Phase 2.2 — 叙事审查（新增）**
```
spawn narrative-review-agent
  输入：projects/{project}/outputs/{ep}/visual-direction.yaml + projects/{project}/outputs/{ep}/render-script.md
  session_id: $SESSION_ID
  trace_file: {ep}-phase2.2-trace
  输出：projects/{project}/outputs/{ep}/narrative-review.md
  状态：projects/{project}/state/{ep}-phase2.2.json
  等待完成
```

读取 `projects/{project}/state/{ep}-phase2.2.json` 的 `decision` 字段：

- **`auto_pass` 或 `fixed_pass`**：继续 Phase 2.3
- **`reject`**：重新 spawn visual-agent，最多重试 2 次：

```
NARRATIVE_RETRY=0
NARRATIVE_MAX_RETRIES=2

while true:
  读取 {ep}-phase2.2.json 的 decision
  
  if decision in ["auto_pass", "fixed_pass"]:
    break  # 继续 Phase 2.3
  
  if decision == "reject":
    NARRATIVE_RETRY += 1
    if NARRATIVE_RETRY > NARRATIVE_MAX_RETRIES:
      # 超过重试上限，人工介入
      输出：
        ⚠️ {ep} 叙事审查连续 {NARRATIVE_MAX_RETRIES} 次 reject，需人工介入
        审查报告：projects/{project}/outputs/{ep}/narrative-review.md
        请修改剧本或手动调整 visual-direction.yaml 后运行 ~start --resume
      退出流程
    
    # 重新 spawn visual-agent，附带退回原因
    输出：[retry {NARRATIVE_RETRY}/{NARRATIVE_MAX_RETRIES}] 叙事审查 reject，重新生成视觉指导...
    
    spawn visual-agent
      输入：projects/{project}/outputs/{ep}/render-script.md + 视觉风格 + 目标媒介
             + 修改指令：projects/{project}/outputs/{ep}/narrative-review.md（退回原因）
      session_id: $SESSION_ID
      trace_file: {ep}-phase2-retry{NARRATIVE_RETRY}-trace
      等待完成
    
    spawn narrative-review-agent
      输入：projects/{project}/outputs/{ep}/visual-direction.yaml + render-script.md
      session_id: $SESSION_ID
      trace_file: {ep}-phase2.2-retry{NARRATIVE_RETRY}-trace
      等待完成
```

**Phase 2.3 — 分镜图生成（新增）**
```
spawn storyboard-agent
  输入：projects/{project}/outputs/{ep}/visual-direction.yaml
  session_id: $SESSION_ID
  trace_file: {ep}-phase2.3-trace
  输出：projects/{project}/outputs/{ep}/storyboard/shot-{N}.png
  等待完成
```

**Phase 2.5 — 资产工厂（v2.0，可选）**

检查是否需要生成资产包（v2.0 模式且资产包不完整）：

```
if [[ "$USE_V2" == "true" ]]; then
  # 检查资产包是否已存在（幂等：已存在则跳过）
  if [[ ! -d "projects/{project}/assets/packs/characters" || -z "$(ls projects/{project}/assets/packs/characters/*.png 2>/dev/null)" ]]; then
    spawn asset-factory-agent
      输入：角色/场景档案 + projects/{project}/state/ontology/{ep}-world-model.json
      session_id: $SESSION_ID
      trace_file: {ep}-phase2.5-trace
      输出：projects/{project}/assets/packs/characters/ + scenes/ + props/
      等待完成
  else
    echo "[skip] Phase 2.5: 资产包已存在，跳过"
  fi
fi
```

🔴 **人工确认点 1**（`--auto-approve` 时跳过）

如果 `--auto-approve` 启用：直接继续 Phase 3，输出日志 `[auto-approve] 视觉指导/叙事审查/分镜图自动通过`。

否则：
```
视觉指导、叙事审查和分镜图已完成，请查看：
- projects/{project}/outputs/{ep}/visual-direction.yaml
- projects/{project}/outputs/{ep}/narrative-review.md
- projects/{project}/outputs/{ep}/storyboard-preview.md

共 {N} 个镜次，总时长约 {X} 秒。

确认后继续美术校验阶段？(yes/no)
```
- 输入 `yes` → 继续 Phase 3
- 输入 `no` → 进入修改流程（~review revise {ep}）

**Phase 3 — 美术校验（纯文件存在性检查）**
```
spawn design-agent
  输入：visual-direction.yaml + projects/{project}/state/design-lock.json（可选）
  session_id: $SESSION_ID
  trace_file: {ep}-phase3-trace
  输出：art-direction-review.md（校验报告）
  等待完成
```

**重要**：Phase 3 是 **O(1) 级别的文件存在性检查**，不经过 gate-agent，不推飞书审核。design-agent 只检查 visual-direction.yaml 中引用的参考图是否存在：
- 如果 `projects/{project}/state/design-lock.json` 存在：读取已锁定的参考图清单，校验文件是否存在
- 如果 `projects/{project}/state/design-lock.json` 不存在：检查 `projects/{project}/assets/characters/images/` 和 `projects/{project}/assets/scenes/images/` 中是否有对应的参考图
- 如果发现缺失的参考图：提示用户先运行 `~design` 生成参考图，然后再继续

注意：推荐在运行 `~start` 前先运行 `~design` 生成参考图。如果 design-agent 发现缺失的参考图，会提示先运行 `~design`。

🔴 **人工确认点 2**（`--auto-approve` 时跳过）

如果 `--auto-approve` 启用：直接继续 Phase 4，输出日志 `[auto-approve] 美术校验自动通过`。

否则：
```
参考图已生成，请查看：projects/{project}/outputs/{ep}/art-direction-review.md

角色参考图：projects/{project}/assets/characters/images/
场景参考图：projects/{project}/assets/scenes/images/

确认后继续音色配置阶段？(yes/no)
```
- 输入 `yes` → 继续 Phase 4
- 输入 `no` → 进入修改流程

**Phase 3.5 — Shot Packet 编译（v2.0 新增）**

检查是否存在 `projects/{project}/state/ontology/{ep}-world-model.json`：
- 如果存在 → 执行 Phase 3.5
- 如果不存在 → 跳过 Phase 3.5，输出日志 `[skip] Phase 3.5: 未找到 world-model.json，跳过 shot packet 编译`

```
# 读取所有 shot_id
shot_ids=$(yq eval '.shots[].shot_id' projects/{project}/outputs/{ep}/visual-direction.yaml)

# 并行 spawn 所有 shot-compiler-agent（不等待，全部同时启动）
for shot_id in $shot_ids; do
  spawn shot-compiler-agent
    输入：shot_id, visual-direction.yaml, world-model.json
    session_id: $SESSION_ID
    trace_file: {ep}-phase3.5-trace
    输出：projects/{project}/state/shot-packets/{shot_id}.json
done

# 等待所有 shot-compiler-agent 完成
wait_all
```

shot-compiler-agent 内部会调用 memory-agent 检索参考资产。每个 agent 写入独立文件，无并发冲突。

完成后写入 `projects/{project}/state/{ep}-phase3.5.json`：
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

**Phase 4 — 音色配置**
```
spawn voice-agent
  输入：render-script + visual-direction.yaml
  session_id: $SESSION_ID
  trace_file: {ep}-phase4-trace
  auto_voice_match: true（如果 --auto-voice 或 --auto-approve 启用）
  等待完成
```

如果 `--auto-voice` 或 `--auto-approve` 启用，voice-agent 使用自动匹配模式（无交互）。
否则 voice-agent 交互式询问用户。

**Phase 5 — 视频生成**

首先读取 `config/platforms/seedance-v2.yaml` 的 `generation_backend` 字段。

**backend = "api"（默认，并行）**

1. 读取 `projects/{project}/outputs/{ep}/visual-direction.yaml`，提取所有镜次数据
2. 为每个镜次组装 gen-worker 参数：

| 参数 | 来源 | 说明 |
|------|------|------|
| ep | 用户选择 | 剧本 ID |
| shot_id | shots[].shot_id | 镜次完整 ID |
| shot_index | shots[].shot_index | 镜次序号 |
| prompt | shots[].seedance_prompt | 组装好的 Seedance 提示词 |
| duration | shots[].duration | 视频时长（秒） |
| generation_mode | shots[].generation_mode | `text2video` 或 `img2video` |
| reference_images | shot-packets/{shot_id}.json → seedance_inputs.images | 角色图 + 场景图 + 分镜图 + 前一镜结尾帧 |
| dialogue | shots[].audio | 对白内容（唇形同步用） |
| voice_config_path | `projects/{project}/assets/characters/voices/{角色名}/voice-config.yaml` | 音色配置路径（TTS 预留） |

3. 并行 spawn gen-workers：
```
spawn gen-worker (shot-1 params, session_id=$SESSION_ID, trace_file={ep}-shot-01-trace)
spawn gen-worker (shot-2 params, session_id=$SESSION_ID, trace_file={ep}-shot-02-trace)
...
spawn gen-worker (shot-N params, session_id=$SESSION_ID, trace_file={ep}-shot-{N}-trace)
等待所有 worker 完成
```

**backend = "browser"（串行，Seedance 2.0 via 即梦 Web UI）**

1. 读取 `projects/{project}/outputs/{ep}/visual-direction.yaml`，提取所有镜次数据
2. 为每个镜次组装 browser-gen-worker 参数：

| 参数 | 来源 | 说明 |
|------|------|------|
| ep | 用户选择 | 剧本 ID |
| shot_id | shots[].shot_id | 镜次完整 ID |
| shot_index | shots[].shot_index | 镜次序号 |
| prompt | shots[].seedance_prompt | Seedance 提示词（browser-gen-worker 内部转换为 script_text） |
| duration | shots[].duration | 视频时长（4-15 秒） |
| ratio | 用户选择的宽高比 | 如 `9:16` |
| reference_image_paths | shots[].references[].local_path | 参考图本地路径（assets/ 下） |
| audio_paths | `projects/{project}/assets/characters/voices/{角色名}/*.mp3` | 音频文件路径 |
| generate_audio | shots[].has_dialogue | 是否生成音频 |
| dialogue | shots[].audio | 对白内容 |

3. 串行 spawn browser-gen-worker（默认串行，可通过 `browser_backend.concurrency` 配置多标签页并行）：
```
concurrency = 1:
  for each shot in shots:
    spawn browser-gen-worker (shot params, concurrency=1, session_id=$SESSION_ID, trace_file={ep}-shot-{N}-trace)
    等待完成
    等待 wait_between 秒

concurrency > 1:
  spawn browser-gen-worker (所有 shot params, concurrency=N, session_id=$SESSION_ID)
  等待完成
```

注意：browser 模式不支持 A/B 测试（API 调用量翻倍在浏览器模式下不现实）。

**Phase 5 — 视频生成（A/B 模式）**

如果 A/B 模式未启用，执行上述原有逻辑（不变）。

如果 A/B 模式启用：

1. 读取变体 A（`config/ab-testing/variants/{variant_a_id}.yaml`）和变体 B 的配置
2. 对每个镜次 shot：
   a. 获取原始 prompt = `shot.seedance_prompt`
   b. 生成 `variant_a_prompt`：
      - `transform_type: passthrough` → 直接使用原始 prompt
      - `transform_type: llm_rewrite` → 将 `rewrite_instruction`（替换 `{original_prompt}` 占位符）发给 LLM 改写
      - 验证 `len(prompt) <= 2000`，超长则截断至 2000 字符并输出警告
   c. 同理生成 `variant_b_prompt`
   d. spawn gen-worker（变体 A）：
      所有原始参数不变，额外传入：
      `prompt=variant_a_prompt`, `output_suffix="-a"`,
      `variant=variant_a_id`, `variant_prompt=variant_a_prompt`
   e. spawn gen-worker（变体 B）：
      同上，`prompt=variant_b_prompt`, `output_suffix="-b"`,
      `variant=variant_b_id`, `variant_prompt=variant_b_prompt`
3. 等待所有 2×N 个 gen-workers 完成
4. 对每个镜次，读取 `projects/{project}/state/{ep}-shot-{N}-a.json` 和 `projects/{project}/state/{ep}-shot-{N}-b.json`，
   创建 `projects/{project}/state/{ep}-shot-{N}-ab-result.json`：
   ```json
   {
     "episode": "{ep}",
     "shot_id": "{shot_id}",
     "shot_index": {N},
     "variant_a": {
       "id": "{variant_a_id}",
       "video_path": "projects/{project}/outputs/{ep}/videos/shot-{N}-a.mp4",
       "status": "{从 -a.json 读取}",
       "prompt_used": "{variant_a_prompt}"
     },
     "variant_b": {
       "id": "{variant_b_id}",
       "video_path": "projects/{project}/outputs/{ep}/videos/shot-{N}-b.mp4",
       "status": "{从 -b.json 读取}",
       "prompt_used": "{variant_b_prompt}"
     },
     "scoring": { "scored": false }
   }
   ```
5. 输出提示：
   ```
   A/B 视频生成完成！
   共 {N} 个镜次 × 2 变体 = {2N} 个视频
   成功：{S}，失败：{F}

   运行 ~ab-review 进行人工评分
   ```

**Phase 6 — Audit & Repair（v2.0 新增）**

检查是否同时满足：
- `projects/{project}/state/ontology/{ep}-world-model.json` 存在
- `projects/{project}/state/shot-packets/` 目录存在

两个条件都满足 → 执行 Phase 6；否则跳过，输出 `[skip] Phase 6: v2.0 条件不满足，跳过审计和修复`

```
# 读取所有成功生成的 shot_id
shot_ids=$(yq eval '.shots[].shot_id' projects/{project}/outputs/{ep}/visual-direction.yaml)

# 对每个 shot 执行审计和修复
for shot_id in $shot_ids; do
  # 检查视频是否存在
  video_file="projects/{project}/outputs/{ep}/videos/${shot_id}.mp4"
  if [ ! -f "$video_file" ]; then
    echo "[skip] $shot_id: 视频不存在，跳过审计"
    continue
  fi
  
  # Phase 6.1: QA 审计
  spawn qa-agent
    输入：shot_id, shot_packet, video_file, world-model.json
    session_id: $SESSION_ID
    trace_file: {ep}-phase6-trace
    输出：projects/{project}/state/audit/{shot_id}-audit.json
    等待完成
  
  # Phase 6.2: 读取审计结果
  audit_result=$(jq '.repair_action' projects/{project}/state/audit/${shot_id}-audit.json)
  
  # Phase 6.3: 根据审计结果执行修复
  if [ "$audit_result" = "pass" ]; then
    echo "[pass] $shot_id: 审计通过，无需修复"
  elif [ "$audit_result" = "local_repair" ]; then
    spawn repair-agent
      输入：shot_id, audit_result, shot_packet
      session_id: $SESSION_ID
      trace_file: {ep}-phase6-trace
      repair_strategy: local_repair
      等待完成
  elif [ "$audit_result" = "regenerate" ]; then
    spawn repair-agent
      输入：shot_id, audit_result, shot_packet
      session_id: $SESSION_ID
      trace_file: {ep}-phase6-trace
      repair_strategy: regenerate
      max_retries: 3
      等待完成
  fi
done
```

完成后写入 `projects/{project}/state/{ep}-phase6.json`：
```json
{
  "episode": "{ep}",
  "phase": 6,
  "status": "completed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "data": {
    "total_shots": {N},
    "passed": {P},
    "local_repaired": {L},
    "regenerated": {R},
    "failed": {F}
  }
}
```

生成 `projects/{project}/outputs/{ep}/audit-report.md`：
```markdown
# 审计和修复报告 - {ep}

## 总览

- 总镜次：{N}
- 直接通过：{P}
- 局部修复：{L}
- 重新生成：{R}
- 修复失败：{F}

## 审计详情

| 镜次 | 审计结果 | 问题类型 | 修复策略 | 修复状态 |
|------|---------|---------|---------|---------|
| shot-01 | pass | - | - | - |
| shot-02 | local_repair | face_mismatch | repair_face | success |
| shot-03 | regenerate | costume_change, prop_disappeared | regenerate | success |
| shot-04 | regenerate | multiple_high_severity | regenerate | failed |

## 修复失败镜次（需人工处理）

| 镜次 | 问题 | 已尝试策略 |
|------|------|-----------|
| shot-04 | 角色服装突变、道具消失 | regenerate × 3 次 |
```

### 5. 汇总结果

读取所有 `projects/{project}/state/{ep}-shot-*.json` 文件，统计成功/失败镜次。

生成 `projects/{project}/outputs/{ep}/generation-report.md`：

```markdown
# 视频生成报告 - {ep}

## 总览

- 总镜次：{N}
- 成功：{S}
- 失败：{F}
- 生成时间：{timestamp}

## 成功镜次

| 镜次 | 视频文件 | 重试次数 | 改写轮次 |
|------|----------|----------|----------|
| shot-01 | videos/shot-01.mp4 | 0 | 0 |

## 失败镜次（需人工处理）

| 镜次 | 最后使用的提示词 | 失败原因 |
|------|-----------------|----------|
| shot-05 | ... | 3轮改写后仍被拒绝 |

## 输出目录

projects/{project}/outputs/{ep}/videos/
```

输出最终结果给用户。

### 6. Session Trace 收尾

写入 session 结束事件：
```bash
./scripts/trace.sh $SESSION_ID session session_end '{"duration_s":{N},"stats":{"total_shots":{N},"succeeded":{S},"failed":{F}}}'
```

如果配置了 `DEEPSEEK_API_KEY`，自动生成 LLM 摘要：
```bash
./scripts/api-caller.sh trace-summary projects/{project}/state/traces/$SESSION_ID
```

输出 trace 信息：
```
📊 Trace 已记录：projects/{project}/state/traces/$SESSION_ID/
运行 ~trace 查看路径概览和诊断信息
```
