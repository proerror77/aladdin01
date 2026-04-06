# ~batch — 批量剧本模式

批量处理 `script/` 目录下的所有剧本，支持并行和串行混合执行。

## 使用方式

```
~batch                      # 从头开始（或自动检测断点续传）
~batch --resume             # 强制断点续传模式
~batch --mine               # 只跑分配给我的集数（多人协作）
~batch --task task-001      # 只跑指定任务的集数
```

### 参数

| 参数 | 说明 |
|------|------|
| `--resume` | 强制断点续传模式，跳过已完成的阶段 |
| `--mine` | 只处理 `state/task-board.json` 中分配给当前用户的集数 |
| `--task <id>` | 只处理指定任务包含的集数 |

## 执行流程

### 0. 环境变量预检

在开始前验证所有必需的环境变量：
```bash
./scripts/api-caller.sh env-check
```

如果有缺失：
```
❌ 环境变量缺失：
- ARK_API_KEY
- OPENAI_API_KEY

请设置后再运行 ~batch
```

### 1. 扫描剧本

扫描 `script/` 目录下所有 `.md` 文件。

如果没有文件：
```
script/ 目录下没有找到剧本文件。
请将剧本放入 script/ 目录（.md 格式），然后重新运行 ~batch
```

列出发现的剧本：
```
发现 {N} 个剧本：
- ep01.md
- ep02.md
- ep03.md

全部处理？(yes/no)
```

### 2. 全局配置

**选择视觉风格**（全局统一）：
```
请选择视觉风格（所有剧本统一）：
1. 写实电影感（真人短剧）
2. 国风古装
3. 现代都市
4. 动漫风格
5. 其他（请描述）
```

**选择目标媒介**：
```
请选择目标媒介：
1. 竖屏短视频（9:16）
2. 横屏视频（16:9）
3. 方形（1:1）
```

**选择生成模式（v1.0 vs v2.0）**：
```
请选择生成模式：
1. v1.0 — 文生视频（text_to_video，快速，无需资产包）
2. v2.0 — 图生视频（img2video，高质量，需要先运行 ~design 生成参考图）
```

根据选择设置：
```bash
USE_V2="false"   # v1.0（默认）
USE_V2="true"    # v2.0
```

也可通过命令行参数直接指定：
```bash
~batch --v2    # 启用 v2.0 模式
~batch         # 默认 v1.0 模式
```

### 3. 初始化所有剧本目录

```bash
mkdir -p outputs/{ep01}/videos
mkdir -p outputs/{ep02}/videos
...
```

生成 session ID（格式：`batch-{YYYYMMDD}-{HHMMSS}`）：
```bash
SESSION_ID="batch-$(date +%Y%m%d-%H%M%S)"
```

写入 session 开始事件：
```bash
./scripts/trace.sh $SESSION_ID session session_start '{"type":"batch","episodes":["ep01","ep02",...],"config":{"visual_style":"...","ratio":"...","backend":"..."}}'
```

初始化 `state/progress.json`：
```json
{
  "version": "1.0",
  "batch_start": "{ISO8601}",
  "episodes": {
    "ep01": {"status": "pending", "current_phase": 0},
    "ep02": {"status": "pending", "current_phase": 0}
  }
}
```

### 3.5 断点检测（自动 resume）

在开始 Phase 1 前，检查已有状态文件：

```
检查断点状态...

[resume] ep01 Phase 1-4 已完成，Phase 5: 8/12 镜次完成
[resume] ep02 全部完成，跳过
[start] ep03 从 Phase 1 开始
[start] ep04 从 Phase 2 开始

摘要：
- 1 个剧本已全部完成，跳过
- 1 个剧本从 Phase 5 继续
- 1 个剧本从 Phase 1 开始
- 1 个剧本从 Phase 2 开始
```

检测逻辑：
1. 对每个剧本，读取 `projects/{project}/state/{ep}-phase{1-4}.json`
2. Phase 5 进度：统计 `projects/{project}/state/{ep}-shot-*.json` 中 `status: completed` 的数量
3. 确定每个剧本的起始阶段

断点续传跳过规则：
- Phase X `status: completed` → 跳过该阶段
- Phase 5 镜次 `status: completed` 且视频文件存在 → 跳过该镜次

### 3.6 多人协作检测

如果使用 `--mine` 或 `--task`：

**`--mine` 模式**：
1. 读取 `state/task-board.json`
2. 筛选 `assigned_to` 为当前用户的任务
3. 提取任务包含的集数列表
4. 只处理这些集数

**`--task <id>` 模式**：
1. 读取 `state/task-board.json`
2. 查找指定 ID 的任务（如 `task-001`）
3. 如果任务不存在，输出错误并退出：
   ```
   ❌ 任务不存在：task-999
   可用任务：task-001, task-002, task-003
   ```
4. 提取任务包含的集数列表
5. 只处理这些集数

**冲突检测**（两种模式共用）：
检查筛选出的集数是否被其他用户锁定：
   ```
   ⚠️ 冲突检测：
   - ep05 已被 alice 锁定（task-002，进行中）
   - ep06 已被 bob 锁定（task-003，进行中）

   是否继续处理未锁定的剧本？(yes/no)
   ```

### 4. Phase 1+2 并行（合规 + 视觉）

**Phase 0 — 本体论构建（v2.0，可选，在 Phase 1 之前）**

如果使用 v2.0 模式，先为每个剧本构建本体论（可并行）：

```
if [[ "$USE_V2" == "true" ]]; then
  for ep in episodes:
    if [ ! -f "projects/{project}/state/ontology/${ep}-world-model.json" ]; then
      spawn ontology-builder-agent（session_id=$SESSION_ID, trace_file=${ep}-phase0-trace）
    else
      echo "[skip] ${ep} Phase 0: world-model.json 已存在"
    fi
  done
  等待所有 ontology-builder-agent 完成
fi
```

为每个剧本并行 spawn comply-agent 和 visual-agent（comply 完成后才 spawn visual）：

```
[ep01] spawn comply-agent（session_id=$SESSION_ID, trace_file=ep01-phase1-trace） → 完成后 spawn visual-agent（session_id=$SESSION_ID, trace_file=ep01-phase2-trace）
[ep02] spawn comply-agent（session_id=$SESSION_ID, trace_file=ep02-phase1-trace） → 完成后 spawn visual-agent（session_id=$SESSION_ID, trace_file=ep02-phase2-trace）
[ep03] spawn comply-agent（session_id=$SESSION_ID, trace_file=ep03-phase1-trace） → 完成后 spawn visual-agent（session_id=$SESSION_ID, trace_file=ep03-phase2-trace）
等待所有剧本的 visual-agent 完成
```

每个 agent spawn/complete 时写入 session trace：
```bash
./scripts/trace.sh $SESSION_ID session spawn '{"agent":"comply-agent","ep":"{ep}","phase":1}'
./scripts/trace.sh $SESSION_ID session complete '{"agent":"comply-agent","ep":"{ep}","phase":1,"duration_s":{N},"summary":"..."}'
```

每个 agent 完成后写入独立状态文件，避免并发写入冲突。

Phase 2 完成后自动进入叙事审查（批量模式默认 `--auto-approve`），无需人工确认。

输出日志：
```
[auto-approve] 所有剧本视觉指导自动通过
```

### 4.3 Phase 2.2 并行（叙事审查）

在 visual-agent 完成后、storyboard-agent 之前，统一做 narrative review：

```
[ep01] spawn narrative-review-agent（session_id=$SESSION_ID, trace_file=ep01-phase2.2-trace）
[ep02] spawn narrative-review-agent（session_id=$SESSION_ID, trace_file=ep02-phase2.2-trace）
等待所有 narrative-review-agent 完成
```

narrative-review-agent 输出：
- `projects/{project}/outputs/{ep}/narrative-review.md`
- `projects/{project}/state/{ep}-phase2.2.json`

**处理 reject 决策**（批量模式每集独立处理，不阻塞其他集）：

```
for ep in episodes:
  NARRATIVE_RETRY = 0
  NARRATIVE_MAX_RETRIES = 2
  
  while true:
    decision = 读取 projects/{project}/state/{ep}-phase2.2.json 的 decision 字段
    
    if decision in ["auto_pass", "fixed_pass"]:
      break  # 继续该集的 Phase 2.3
    
    if decision == "reject":
      NARRATIVE_RETRY += 1
      if NARRATIVE_RETRY > NARRATIVE_MAX_RETRIES:
        # 超过重试上限，标记该集为 blocked，不阻塞其他集
        输出：⚠️ {ep} 叙事审查连续 {NARRATIVE_MAX_RETRIES} 次 reject，已跳过，需人工介入
        将 {ep} 标记为 blocked，从本次批量任务中排除
        break
      
      输出：[retry {NARRATIVE_RETRY}/{NARRATIVE_MAX_RETRIES}] {ep} 叙事审查 reject，重新生成视觉指导...
      
      spawn visual-agent
        输入：render-script.md + 视觉风格 + 目标媒介
               + 修改指令：projects/{project}/outputs/{ep}/narrative-review.md
        session_id: $SESSION_ID
        trace_file: {ep}-phase2-retry{NARRATIVE_RETRY}-trace
        等待完成
      
      spawn narrative-review-agent
        输入：visual-direction.yaml + render-script.md
        session_id: $SESSION_ID
        trace_file: {ep}-phase2.2-retry{NARRATIVE_RETRY}-trace
        等待完成
```

### 4.5 Phase 2.3 并行（分镜图生成）

在 Phase 2.2 完成后，为每集生成本地 fallback 分镜图或 AI 分镜图，并把 `storyboard_image_path` 注入 `visual-direction.yaml`：

```
[ep01] spawn storyboard-agent（session_id=$SESSION_ID, trace_file=ep01-phase2.3-trace）
[ep02] spawn storyboard-agent（session_id=$SESSION_ID, trace_file=ep02-phase2.3-trace）
等待所有 storyboard-agent 完成
```

### 4.6 Phase 2.5 并行（资产工厂 — v2.0，可选）

如果使用 v2.0 模式，在分镜图生成后、美术校验前，生成资产包（幂等，已存在则跳过）：

```
if [[ "$USE_V2" == "true" ]]; then
  for ep in episodes:
    if [[ ! -d "projects/{project}/assets/packs/characters" || -z "$(ls projects/{project}/assets/packs/characters/*.png 2>/dev/null)" ]]; then
      spawn asset-factory-agent（session_id=$SESSION_ID, trace_file=${ep}-phase2.5-trace）
    else
      echo "[skip] ${ep} Phase 2.5: 资产包已存在"
    fi
  done
  等待所有 asset-factory-agent 完成
fi
```

### 5. Phase 3 并行（美术校验 — 纯文件存在性检查）

所有参考图已由 `~design` 预先生成并锁定到 `projects/{project}/state/design-lock.json`。Phase 3 只做 O(1) 级别的文件存在性检查，不经过 gate-agent，不推飞书审核。

```
[ep01] spawn design-agent（session_id=$SESSION_ID, trace_file=ep01-phase3-trace）
[ep02] spawn design-agent（session_id=$SESSION_ID, trace_file=ep02-phase3-trace）
[ep03] spawn design-agent（session_id=$SESSION_ID, trace_file=ep03-phase3-trace）
等待所有 design-agent 完成
```

如有缺失，design-agent 会列出缺失清单并提示：
```
design-agent 发现 {N} 个缺失的参考图：
- 角色「{角色名}」变体「{variant_id}」缺少参考图
- 场景「{场景名}」时间「{time_of_day}」缺少参考图

请先运行 ~design 补全参考图后再继续。
```

每个 design-agent 完成后写入 `projects/{project}/state/{ep}-phase3.json`。

Phase 3 完成后自动通过（批量模式默认 `--auto-approve`），无需人工确认。

### 5.5 Phase 3.5 并行（Shot Packet 编译 — v2.0 新增）

检查是否存在 `projects/{project}/state/ontology/` 目录：
- 如果存在 → 执行 Phase 3.5
- 如果不存在且 `USE_V2 == "true"` → 输出警告：
  ```
  ⚠️ v2.0 模式已启用，但 ontology/ 目录不存在。
  可能原因：Phase 0（ontology-builder）未执行或失败。
  当前降级为 v1.0 模式（gen-worker 将从 visual-direction.yaml 读取参数）。
  ```
- 如果不存在且 `USE_V2 == "false"` → 正常跳过，输出 `[skip] Phase 3.5: v1.0 模式，跳过 shot packet 编译`

为每个剧本的所有 shots **并行**编译 shot packets（与 Phase 5 gen-worker 相同的并行模式）：

```
for ep in episodes:
  # 检查 world-model 是否存在
  if [ ! -f "projects/{project}/state/ontology/${ep}-world-model.json" ]; then
    echo "[skip] ${ep}: 未找到 world-model.json，跳过 Phase 3.5"
    continue
  fi
  
  # 读取所有 shot_id
  shot_ids=$(yq eval '.shots[].shot_id' projects/{project}/outputs/${ep}/visual-direction.yaml)
  
  # 并行 spawn 所有 shot-compiler-agent（不等待，全部同时启动）
  for shot_id in $shot_ids; do
    spawn shot-compiler-agent
      输入：shot_id, visual-direction.yaml, world-model.json
      session_id: $SESSION_ID
      trace_file: ${ep}-phase3.5-trace
      输出：projects/{project}/state/shot-packets/${shot_id}.json
  done
  
  # 等待该剧本所有 shot-compiler-agent 完成
  wait_all
  
  # 写入状态文件
  echo '{"episode":"'${ep}'","phase":3.5,"status":"completed",...}' > projects/{project}/state/${ep}-phase3.5.json
done
```

**并行安全保证**：每个 shot-compiler-agent 写入独立的 `shot-packets/{shot_id}.json`，无并发冲突。shot-compiler-agent 内部调用 memory-agent 检索参考资产，memory-agent 只读 LanceDB，也无冲突。

### 6. Phase 4 并行（音色配置）

**批量模式默认启用 `auto_voice_match`，无交互，可安全并行。**

```
[ep01] spawn voice-agent（auto_voice_match: true, session_id=$SESSION_ID, trace_file=ep01-phase4-trace）
[ep02] spawn voice-agent（auto_voice_match: true, session_id=$SESSION_ID, trace_file=ep02-phase4-trace）
[ep03] spawn voice-agent（auto_voice_match: true, session_id=$SESSION_ID, trace_file=ep03-phase4-trace）
等待所有 voice-agent 完成
```

并行安全保证：
- 自动匹配模式无用户交互，不会冲突
- 每个 voice-agent 读取 `projects/{project}/assets/characters/voices/` 检查已有音色
- 同一角色的音色由首次遇到的 voice-agent 写入，后续复用

每个 voice-agent 完成后写入 `projects/{project}/state/{ep}-phase4.json`。

### 7. Phase 5 视频生成

首先读取 `config/platforms/seedance-v2.yaml` 的 `generation_backend` 字段。

**backend = "api"（默认，并行）**

读取 `config/platforms/seedance-v2.yaml` 的 `max_concurrent_workers`（默认 30）。所有镜次按此上限分批并行，避免触发 API rate limit：

```
for each batch of max_concurrent_workers shots:
  spawn gen-worker × batch_size（并行）
  等待本批全部完成
  继续下一批
```

所有剧本的所有镜次并行生成：

**参数提取**（每个镜次）：

| 参数 | 来源 | 说明 |
|------|------|------|
| ep | 剧本 ID | 当前剧本 |
| shot_id | shots[].shot_id | 镜次完整 ID |
| shot_index | shots[].shot_index | 镜次序号 |
| prompt | shots[].prompt | Seedance 提示词 |
| duration | shots[].duration | 时长（秒） |
| generation_mode | shots[].generation_mode | 生成模式 |
| reference_image_path | shots[].references[0].image_path | 参考图 |
| dialogue | shots[].audio | 对白内容 |
| voice_config_path | 角色音色配置 | 音色文件路径 |

```
[ep01] spawn gen-worker × N1（每个 worker 传入 session_id=$SESSION_ID, trace_file={ep}-shot-{N}-trace）
[ep02] spawn gen-worker × N2
[ep03] spawn gen-worker × N3
等待所有 worker 完成
```

**backend = "browser"（可配置并行度，Seedance 2.0 via 即梦 Web UI）**

读取 `config/platforms/seedance-v2.yaml` 的 `browser_backend.concurrency` 值（默认 1）：

```
concurrency = 1（串行）:
  for each ep in episodes:
    for each shot in ep.shots:
      spawn browser-gen-worker (shot params, concurrency=1, session_id=$SESSION_ID, trace_file={ep}-shot-{N}-trace)
      等待完成
      等待 wait_between 秒

concurrency > 1（多标签页并行）:
  将所有 shots 分配到 concurrency 个队列
  spawn browser-gen-worker (所有 shot params, concurrency=N, session_id=$SESSION_ID)
  等待完成
```

注意：concurrency > 1 需实测即梦是否有 rate limit，建议从 2 开始。

每个 gen-worker / browser-gen-worker 写入独立状态文件 `projects/{project}/state/{ep}-shot-{N}.json`，无并发冲突。

### 7.5 Phase 6 并行（Audit & Repair — v2.0 新增）

检查是否同时满足：
- `projects/{project}/state/ontology/{ep}-world-model.json` 存在
- `projects/{project}/state/shot-packets/` 目录存在

两个条件都满足 → 执行 Phase 6；否则跳过，输出 `[skip] Phase 6: v2.0 条件不满足，跳过审计和修复`

为每个剧本的所有成功生成的 shots 执行审计和修复（可并行）：

```
for ep in episodes:
  if [ ! -d "projects/{project}/state/shot-packets" ]; then
    echo "[skip] ${ep}: 未找到 shot-packets/，跳过 Phase 6"
    continue
  fi
  
  shot_ids=$(yq eval '.shots[].shot_id' projects/{project}/outputs/${ep}/visual-direction.yaml)
  
  for shot_id in $shot_ids; do
    video_file="outputs/${ep}/videos/${shot_id}.mp4"
    [ ! -f "$video_file" ] && continue
    
    spawn qa-agent (shot_id, session_id=$SESSION_ID, trace_file=${ep}-phase6-trace)
    wait
    
    audit_result=$(jq -r '.repair_action' projects/{project}/state/audit/${shot_id}-audit.json)
    
    if [ "$audit_result" != "pass" ]; then
      spawn repair-agent (shot_id, repair_strategy=$audit_result, max_retries=3, session_id=$SESSION_ID)
    fi
  done
  
  wait
  
  # 写入状态文件和生成审计报告
  write_phase6_state ${ep}
  generate_audit_report ${ep}
done
```

### 8. 批量汇总报告

读取所有 `projects/{project}/state/{ep}-shot-*.json` 文件，生成每个剧本的 `generation-report.md`：

```
批量处理完成！

━━━ 总览 ━━━
处理剧本：{N} 个
总镜次：{T}
成功：{S}
失败：{F}

━━━ 各剧本状态 ━━━
ep01：{S1}/{T1} 成功
ep02：{S2}/{T2} 成功
ep03：{S3}/{T3} 成功

失败镜次详见各剧本的 generation-report.md
```

### 9. Session Trace 收尾

写入 session 结束事件：
```bash
./scripts/trace.sh $SESSION_ID session session_end '{"duration_s":{N},"stats":{"total_shots":{T},"succeeded":{S},"failed":{F}}}'
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

## 并行 vs 串行策略

| 阶段 | 执行方式 | 原因 |
|------|---------|------|
| Phase 1 合规 | 并行 | 独立剧本，无共享资源 |
| Phase 2 视觉 | 并行 | 独立剧本，无共享资源 |
| Phase 3 美术校验 | **并行** | 纯校验：检查参考图是否存在（所有图由 `~design` 预先生成） |
| Phase 4 音色 | **并行** | 自动匹配模式无交互，无冲突 |
| Phase 5 视频 | 并行 | 每个镜次独立状态文件 |

## 单个剧本失败处理

如果某个剧本在某个阶段失败：

```
⚠️ ep03 Phase 2 失败：视觉指导生成错误

选择操作：
1. 跳过 ep03，继续处理其他剧本
2. 终止整个批量任务
```

- 选择 1：跳过失败的剧本，继续处理剩余剧本。失败的剧本状态文件标记为 `failed`，可稍后手动修复后运行 `~batch --resume`
- 选择 2：立即终止批量任务。已完成的剧本产出保留，未开始的剧本跳过。可运行 `~batch --resume` 从断点继续
```
ep02 在 Phase 1 合规检测失败：剧本格式错误

选项：
1. 跳过 ep02，继续处理其他剧本
2. 终止整个批量任务

请选择：
```

选择跳过后，最终报告会标记该剧本为 `skipped`。
