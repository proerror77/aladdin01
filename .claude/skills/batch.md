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

**design-lock.json 检查**：
- 检查 `projects/{project}/state/design-lock.json` 是否存在
- 如果不存在：输出警告 "⚠️ 未找到 design-lock.json，Phase 3 将报告参考图缺失"
- 询问用户是否继续（yes/no），no 则退出并提示运行 ~design

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

### 3. 初始化

```bash
for ep in $EPISODES; do
  mkdir -p projects/{PROJECT}/outputs/${ep}/videos
done
```

生成 session ID（格式：`batch-{YYYYMMDD}-{HHMMSS}`）：
```bash
SESSION_ID="batch-$(date +%Y%m%d-%H%M%S)"
```

写入 session 开始事件：
```bash
./scripts/trace.sh $SESSION_ID session session_start '{"type":"batch","episodes":[...],"config":{...}}'
```
### 3.5 多人协作检测

如果使用 `--mine` 或 `--task`：

**`--mine` 模式**：
1. 读取 `state/task-board.json`
2. 筛选 `assigned_to` 为当前用户的任务
3. 提取任务包含的集数列表
4. 只处理这些集数

**`--task <id>` 模式**：
1. 读取 `state/task-board.json`
2. 查找指定 ID 的任务
3. 如果任务不存在，输出错误并退出
4. 提取任务包含的集数列表

**冲突检测**（两种模式共用）：
检查筛选出的集数是否被其他用户锁定：
```
⚠️ 冲突检测：
- ep05 已被 alice 锁定（task-002，进行中）

是否继续处理未锁定的剧本？(yes/no)
```

### 4. 并行处理（状态机驱动）

Phase 0-4 的流转由 `pipeline-runner.py` 状态机驱动。断点续传自动工作（`next` 跳过已完成 Phase）。
批量模式默认 `--auto-approve`，无需人工确认。

```bash
USE_V2_FLAG=""
[[ "$USE_V2" == "true" ]] && USE_V2_FLAG="--use-v2"

# 显示所有 episode 的当前状态
for ep in $EPISODES; do
  python3 scripts/pipeline-runner.py status \
    --project $PROJECT --ep $ep $USE_V2_FLAG
done

# 并行处理每个 episode
for ep in $EPISODES; do
  (
    SESSION_ID="batch-$(date +%Y%m%d-%H%M%S)-$ep"

    while true; do
      ACTION=$(python3 scripts/pipeline-runner.py next \
        --project $PROJECT --ep $ep $USE_V2_FLAG)

      action_type=$(echo "$ACTION" | jq -r '.action')
      phase=$(echo "$ACTION" | jq -r '.phase')
      agent=$(echo "$ACTION" | jq -r '.agent')
      phase_name=$(echo "$ACTION" | jq -r '.phase_name')

      case "$action_type" in
        "done")
          echo "[$ep] ✓ 完成"
          break
          ;;

        "spawn_agent")
          echo "[$ep] Phase $phase ($phase_name)..."

          # Phase 5: 并行 gen-worker（见下方 Phase 5 详细逻辑）
          if [[ "$phase" == "5" ]]; then
            # → 跳转到 Phase 5 逻辑
            break
          fi

          # Phase 6: audit-repair（见下方 Phase 6 详细逻辑）
          if [[ "$phase" == "6" ]]; then
            # → 跳转到 Phase 6 逻辑
            break
          fi
          # Phase 2.2 叙事审查：处理 reject 重试（每集独立，不阻塞其他集）
          if [[ "$phase_name" == "narrative-review" ]]; then
            NARRATIVE_RETRY=0
            NARRATIVE_MAX_RETRIES=2

            spawn $agent
              输入：$(echo "$ACTION" | jq -r '.inputs')
              session_id: $SESSION_ID
              等待完成

            while true; do
              decision=$(jq -r '.decision' projects/$PROJECT/state/${ep}-phase2.2.json)

              if [[ "$decision" == "auto_pass" || "$decision" == "fixed_pass" ]]; then
                break
              fi

              if [[ "$decision" == "reject" ]]; then
                NARRATIVE_RETRY=$((NARRATIVE_RETRY + 1))
                if [[ $NARRATIVE_RETRY -gt $NARRATIVE_MAX_RETRIES ]]; then
                  echo "[$ep] ⚠️ 叙事审查连续 ${NARRATIVE_MAX_RETRIES} 次 reject，跳过"
                  # 写入 blocked-episodes.json
                  break
                fi

                echo "[$ep] [retry ${NARRATIVE_RETRY}/${NARRATIVE_MAX_RETRIES}] 重新生成视觉指导..."
                python3 scripts/pipeline-runner.py reset \
                  --project $PROJECT --ep $ep --from-phase 2

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
              --project $PROJECT --ep $ep --phase $phase
            continue
          fi

          # 通用 agent spawn
          spawn $agent
            输入：$(echo "$ACTION" | jq -r '.inputs')
            session_id: $SESSION_ID
            等待完成

          python3 scripts/pipeline-runner.py complete \
            --project $PROJECT --ep $ep --phase $phase
          ;;

        "error")
          echo "[$ep] ❌ $(echo "$ACTION" | jq -r '.reason')"
          break
          ;;
      esac
    done
  ) &
done

wait
```
**Phase 5 — 视频生成（所有 episode 的镜次统一并行）**

首先读取 `config/platforms/seedance-v2.yaml` 的 `generation_backend` 和 `max_concurrent_workers`（默认 30）。

**backend = "api"（默认，并行）**

所有剧本的所有镜次按 `max_concurrent_workers` 上限分批并行：

```
for each batch of max_concurrent_workers shots:
  spawn gen-worker × batch_size（并行）
  等待本批全部完成
  继续下一批
```

每个 gen-worker 写入独立状态文件 `projects/{PROJECT}/state/{ep}-shot-{N}.json`，无并发冲突。

**backend = "browser"（可配置并行度）**

读取 `browser_backend.concurrency` 值（默认 1）：
```
concurrency = 1（串行）:
  for each shot: spawn browser-gen-worker → 等待完成 → 等待 wait_between 秒

concurrency > 1（多标签页并行）:
  spawn browser-gen-worker (所有 shot params, concurrency=N)
  等待完成
```

Phase 5 完成后标记状态：
```bash
for ep in $EPISODES; do
  python3 scripts/pipeline-runner.py complete \
    --project $PROJECT --ep $ep --phase 5
done
```

**Phase 6 — Audit & Repair（v2.0 新增）**

检查是否同时满足：
- `projects/{PROJECT}/state/ontology/{ep}-world-model.json` 存在
- `projects/{PROJECT}/state/shot-packets/` 目录存在

两个条件都满足 → 执行 Phase 6；否则跳过。

为每个剧本的所有成功生成的 shots 执行审计和修复：

```
for ep in $EPISODES:
  for shot_id in shot_ids:
    video_file="projects/{PROJECT}/outputs/${ep}/videos/${shot_id}.mp4"
    [ ! -f "$video_file" ] && continue

    spawn qa-agent (shot_id, session_id=$SESSION_ID)
    wait

    audit_result=$(jq -r '.repair_action' projects/{PROJECT}/state/audit/${shot_id}-audit.json)

    if [ "$audit_result" != "pass" ]; then
      # team-lead 直接编排重试循环（最多 3 次）
      for attempt in 1 2 3; do
        spawn repair-agent (shot_id, repair_strategy=adjust_packet, attempt=$attempt)
        wait
        spawn gen-worker (shot_id)
        wait
        spawn qa-agent (shot_id)
        wait
        new_result=$(jq -r '.repair_action' ...)
        [ "$new_result" = "pass" ] && break
      done
    fi
  done

  python3 scripts/pipeline-runner.py complete \
    --project $PROJECT --ep $ep --phase 6
done
```
### 5. 汇总进度

```bash
for ep in $EPISODES; do
  python3 scripts/pipeline-runner.py status \
    --project $PROJECT --ep $ep $USE_V2_FLAG
done
```

读取所有 `projects/{PROJECT}/state/{ep}-shot-*.json` 文件，生成每个剧本的 `generation-report.md`：

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

失败镜次详见各剧本的 generation-report.md
```

### 6. Session Trace 收尾

写入 session 结束事件：
```bash
./scripts/trace.sh $SESSION_ID session session_end '{"duration_s":{N},"stats":{"total_shots":{T},"succeeded":{S},"failed":{F}}}'
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

## 并行 vs 串行策略

| 阶段 | 执行方式 | 原因 |
|------|---------|------|
| Phase 0-4 | 每集并行（状态机驱动） | 独立剧本，无共享资源 |
| Phase 5 视频 | 所有镜次统一并行（受 max_concurrent_workers 限制） | 每个镜次独立状态文件 |
| Phase 6 审计 | 每集串行审计 | QA→repair→regen 有依赖 |

## 单个剧本失败处理

如果某个剧本在某个阶段失败：

```
⚠️ ep03 Phase 2 失败：视觉指导生成错误

💡 诊断：~trace --backtrack ep03（查看失败链路）
🔄 恢复：修复后运行 ~batch --resume 从断点继续

选择操作：
1. 跳过 ep03，继续处理其他剧本
2. 终止整个批量任务
```

- 选择 1：跳过失败的剧本，继续处理剩余剧本
- 选择 2：立即终止。可运行 `~batch --resume` 从断点继续
