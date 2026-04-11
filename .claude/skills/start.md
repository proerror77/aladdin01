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
**Scriptwriter 输出检测**：
- 如果 `outputs/scriptwriter/{project}/` 存在且 `projects/{project}/script/` 为空或不存在
- 输出：⚠️ 发现 outputs/scriptwriter/{project}/ 中有剧本，但 projects/{project}/script/ 为空
- 提示：请先运行 ~preprocess 将剧本转换到正确位置，然后再运行 ~start
- 退出（不继续执行）

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
### 4. 主循环（状态机驱动）

Phase 0-4 的流转由 `pipeline-runner.py` 状态机驱动。断点续传自动工作（`next` 跳过已完成 Phase）。

```bash
USE_V2_FLAG=""
[[ "$USE_V2" == "true" ]] && USE_V2_FLAG="--use-v2"

# 显示当前状态
python3 scripts/pipeline-runner.py status --project $PROJECT --ep $EP $USE_V2_FLAG

# 主循环
while true; do
  ACTION=$(python3 scripts/pipeline-runner.py next \
    --project $PROJECT --ep $EP $USE_V2_FLAG)

  action_type=$(echo "$ACTION" | jq -r '.action')
  phase=$(echo "$ACTION" | jq -r '.phase')
  agent=$(echo "$ACTION" | jq -r '.agent')
  phase_name=$(echo "$ACTION" | jq -r '.phase_name')

  case "$action_type" in
    "done")
      echo "✓ 所有 Phase 完成"
      break
      ;;

    "spawn_agent")
      echo ""
      echo "▶ Phase $phase — $phase_name"

      # Phase 5 和 Phase 6 有特殊的并行/信号逻辑，跳出主循环单独处理
      if [[ "$phase" == "5" || "$phase" == "6" ]]; then
        break
      fi

      # 人工确认点（Phase 2 视觉指导完成后 / Phase 3 美术校验完成后）
      if [[ "$phase" == "2.3" || "$phase" == "3" ]] && [[ "$AUTO_APPROVE" != "true" ]]; then
        if [[ "$phase" == "2.3" ]]; then
          echo "视觉指导和叙事审查已完成，请查看："
          echo "- projects/{PROJECT}/outputs/{EP}/visual-direction.yaml"
          echo "- projects/{PROJECT}/outputs/{EP}/narrative-review.md"
        fi
        if [[ "$phase" == "3" ]]; then
          echo "请查看：projects/{PROJECT}/outputs/{EP}/art-direction-review.md"
        fi
        # 推飞书通知（如果配置了 LARK_APP_ID）
        if [[ -n "${LARK_APP_ID:-}" ]]; then
          ./scripts/notify.sh lark-review \
            --project $PROJECT --ep $EP --phase $phase \
            --message "Phase $phase ($phase_name) 需要人工确认"
        fi
        echo "🔴 人工确认点：Phase $phase ($phase_name)"
        echo "   查看产出后输入 yes 继续，no 退出："
        read -r confirm
        if [[ "$confirm" != "yes" ]]; then
          echo "已退出。重新运行 ~start 继续。"
          exit 0
        fi
      fi

      # Phase 2.2 叙事审查：需要处理 reject 重试循环
      if [[ "$phase_name" == "narrative-review" ]]; then
        NARRATIVE_RETRY=0
        NARRATIVE_MAX_RETRIES=2

        spawn $agent
          输入：$(echo "$ACTION" | jq -r '.inputs')
          session_id: $SESSION_ID
          等待完成

        while true; do
          decision=$(jq -r '.decision' projects/$PROJECT/state/${EP}-phase2.2.json)

          if [[ "$decision" == "auto_pass" || "$decision" == "fixed_pass" ]]; then
            break
          fi

          if [[ "$decision" == "reject" ]]; then
            NARRATIVE_RETRY=$((NARRATIVE_RETRY + 1))
            if [[ $NARRATIVE_RETRY -gt $NARRATIVE_MAX_RETRIES ]]; then
              echo "⚠️ ${EP} 叙事审查连续 ${NARRATIVE_MAX_RETRIES} 次 reject，需人工介入"
              echo "审查报告：projects/$PROJECT/outputs/${EP}/narrative-review.md"
              exit 1
            fi

            echo "[retry ${NARRATIVE_RETRY}/${NARRATIVE_MAX_RETRIES}] 叙事审查 reject，重新生成视觉指导..."

            # 重置 Phase 2 让状态机重新 spawn visual-agent
            python3 scripts/pipeline-runner.py reset \
              --project $PROJECT --ep $EP --from-phase 2

            spawn visual-agent
              输入：render-script.md + 修改指令（narrative-review.md）
              session_id: $SESSION_ID
              等待完成

            spawn narrative-review-agent
              输入：visual-direction.yaml + render-script.md
              session_id: $SESSION_ID
              等待完成
          fi
        done

        python3 scripts/pipeline-runner.py complete \
          --project $PROJECT --ep $EP --phase $phase
        continue
      fi

      # 通用 agent spawn
      spawn $agent
        输入：$(echo "$ACTION" | jq -r '.inputs')
        session_id: $SESSION_ID
        等待完成

      # 标记完成
      python3 scripts/pipeline-runner.py complete \
        --project $PROJECT --ep $EP --phase $phase
      ;;

    "error")
      reason=$(echo "$ACTION" | jq -r '.reason')
      echo "❌ 错误：$reason"
      exit 1
      ;;
  esac
done
```
**Phase 5 — 视频生成**

首先读取 `config/platforms/seedance-v2.yaml` 的 `generation_backend` 字段。

**backend = "api"（默认，并行）**

1. 读取 `projects/{PROJECT}/outputs/{EP}/visual-direction.yaml`，提取所有镜次数据
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
| voice_config_path | `projects/{PROJECT}/assets/characters/voices/{角色名}/voice-config.yaml` | 音色配置路径（TTS 预留） |

3. 并行 spawn gen-workers：
```
spawn gen-worker (shot-1 params, session_id=$SESSION_ID, trace_file={ep}-shot-01-trace)
spawn gen-worker (shot-2 params, session_id=$SESSION_ID, trace_file={ep}-shot-02-trace)
...
spawn gen-worker (shot-N params, session_id=$SESSION_ID, trace_file={ep}-shot-{N}-trace)
等待所有 worker 完成
```

**backend = "browser"（串行，Seedance 2.0 via 即梦 Web UI）**

1. 读取 `projects/{PROJECT}/outputs/{EP}/visual-direction.yaml`，提取所有镜次数据
2. 串行 spawn browser-gen-worker（默认串行，可通过 `browser_backend.concurrency` 配置多标签页并行）：
```
concurrency = 1:
  for each shot in shots:
    spawn browser-gen-worker (shot params, concurrency=1, session_id=$SESSION_ID)
    等待完成
    等待 wait_between 秒

concurrency > 1:
  spawn browser-gen-worker (所有 shot params, concurrency=N, session_id=$SESSION_ID)
  等待完成
```

注意：browser 模式不支持 A/B 测试。
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
   d. spawn gen-worker（变体 A）：`prompt=variant_a_prompt`, `output_suffix="-a"`, `variant=variant_a_id`
   e. spawn gen-worker（变体 B）：`prompt=variant_b_prompt`, `output_suffix="-b"`, `variant=variant_b_id`
3. 等待所有 2×N 个 gen-workers 完成
4. 创建 `projects/{PROJECT}/state/{EP}-shot-{N}-ab-result.json`
5. 输出提示：运行 `~ab-review` 进行人工评分

Phase 5 完成后标记状态：
```bash
python3 scripts/pipeline-runner.py complete \
  --project $PROJECT --ep $EP --phase 5
```
**Phase 6 — Audit & Repair（v2.0 新增）**

检查是否同时满足：
- `projects/{PROJECT}/state/ontology/{EP}-world-model.json` 存在
- `projects/{PROJECT}/state/shot-packets/` 目录存在

两个条件都满足 → 执行 Phase 6；否则跳过，输出 `[skip] Phase 6: v2.0 条件不满足，跳过审计和修复`

```
# 读取所有成功生成的 shot_id
shot_ids=$(yq eval '.shots[].shot_id' projects/{PROJECT}/outputs/{EP}/visual-direction.yaml)

# 对每个 shot 执行审计和修复
for shot_id in $shot_ids; do
  # 检查视频是否存在
  video_file="projects/{PROJECT}/outputs/{EP}/videos/${shot_id}.mp4"
  if [ ! -f "$video_file" ]; then
    echo "[skip] $shot_id: 视频不存在，跳过审计"
    continue
  fi

  # Step 1: QA 审计
  spawn qa-agent
    输入：shot_id, shot_packet, video_file, world-model.json
    session_id: $SESSION_ID
    等待完成

  audit_result=$(jq -r '.repair_action' projects/{PROJECT}/state/audit/${shot_id}-audit.json)

  # Step 2: 根据审计结果处理
  if [ "$audit_result" = "pass" ]; then
    echo "[pass] $shot_id: 审计通过"

  elif [ "$audit_result" = "local_repair" ]; then
    spawn repair-agent
      输入：shot_id, audit_result, shot_packet
      signal_mode: false
      repair_strategy: local_repair
      等待完成

  elif [ "$audit_result" = "regenerate" ]; then
    # team-lead 直接编排重试循环（不依赖信号机制）
    for attempt in 1 2 3; do
      echo "  [regenerate] $shot_id 第 $attempt 次尝试"

      # Step 2a: repair-agent 调整 shot packet（不生成视频）
      spawn repair-agent
        输入：shot_id, audit_result, shot_packet
        signal_mode: false
        repair_strategy: adjust_packet
        attempt: $attempt
        等待完成

      # Step 2b: gen-worker 重新生成
      spawn gen-worker
        输入：shot_id（从更新后的 shot packet 读取参数）
        session_id: $SESSION_ID
        等待完成

      # Step 2c: qa-agent 验证
      spawn qa-agent
        输入：shot_id, shot_packet, video_file, world-model.json
        session_id: $SESSION_ID
        等待完成

      new_result=$(jq -r '.repair_action' projects/{PROJECT}/state/audit/${shot_id}-audit.json)
      if [ "$new_result" = "pass" ]; then
        echo "  ✓ $shot_id 修复成功（第 $attempt 次）"
        break
      fi

      if [ $attempt -eq 3 ]; then
        echo "  ✗ $shot_id 修复失败（已尝试 3 次），标记为 failed"
      fi
    done
  fi
done
```

Phase 6 完成后标记状态：
```bash
python3 scripts/pipeline-runner.py complete \
  --project $PROJECT --ep $EP --phase 6
```
### 5. 汇总结果

读取所有 `projects/{PROJECT}/state/{EP}-shot-*.json` 文件，统计成功/失败镜次。

生成 `projects/{PROJECT}/outputs/{EP}/generation-report.md`：

```markdown
# 视频生成报告 - {EP}

## 总览

- 总镜次：{N}
- 成功：{S}
- 失败：{F}
- 生成时间：{timestamp}

## 失败镜次（需人工处理）

| 镜次 | 最后使用的提示词 | 失败原因 |
|------|-----------------|----------|

💡 诊断：~trace --backtrack {EP} shot-05（查看失败链路）
🔄 恢复：修复后运行 ~start {PROJECT} {EP} 从断点继续

## 输出目录

projects/{PROJECT}/outputs/{EP}/videos/
```

输出最终结果给用户。

### 6. Session Trace 收尾

写入 session 结束事件：
```bash
./scripts/trace.sh $SESSION_ID session session_end '{"duration_s":{N},"stats":{"total_shots":{N},"succeeded":{S},"failed":{F}}}'
```

如果配置了 `DEEPSEEK_API_KEY`，自动生成 LLM 摘要：
```bash
./scripts/api-caller.sh trace-summary projects/{PROJECT}/state/traces/$SESSION_ID
```

输出 trace 信息：
```
📊 Trace 已记录：projects/{PROJECT}/state/traces/$SESSION_ID/
运行 ~trace 查看路径概览和诊断信息
```
