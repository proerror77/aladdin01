---
name: repair-agent
description: Repair agent。根据 QA 结果决定修复策略：pass / local_repair / regenerate。
tools:
  - Read
  - Write
  - Bash
write_scope:
  - "projects/{project}/state/audit/{ep}-shot-{N}-repair-history.json"
  - "projects/{project}/state/shot-packets/{ep}-shot-{N}.json"
  - "projects/{project}/state/{ep}-shot-{N}.json"
  - "projects/{project}/outputs/{ep}/audit/"
  - "projects/{project}/state/signals/"
read_scope:
  - "projects/{project}/state/audit/"
  - "projects/{project}/state/shot-packets/"
  - "projects/{project}/outputs/{ep}/videos/"
  - "projects/{project}/assets/packs/"
---

# repair-agent — 修复决策

## 职责

根据 QA 审计结果决定修复策略，并执行相应的修复操作。

## 输入（由 team-lead 传入）

| 参数 | 类型 | 说明 |
|------|------|------|
| `project` | string | 项目名，如 `qyccan` |
| `ep` | string | 剧本 ID（如 ep01） |
| `shot_id` | string | 镜次 ID（如 ep01-shot-05） |
| `session_id` | string | Trace session 标识 |
| `max_attempts` | int | 最大重试次数（默认 3） |

## 输出

- 修复后的视频（如需修复）
- 更新的审计结果

## 执行流程

### Step 1: 初始化

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 参数
PROJECT="$1"
EP="$2"
SHOT_ID="$3"
SESSION_ID="${4:-repair-$(date +%Y%m%d-%H%M%S)}"
MAX_ATTEMPTS="${5:-3}"

# 提取 shot 序号
SHOT_NUM=$(echo "$SHOT_ID" | grep -oE '[0-9]+$')

# 路径
AUDIT_FILE="$PROJECT_ROOT/projects/${PROJECT}/state/audit/${SHOT_ID}-audit.json"
SHOT_PACKET="$PROJECT_ROOT/projects/${PROJECT}/state/shot-packets/${SHOT_ID}.json"
VIDEO_FILE="$PROJECT_ROOT/projects/${PROJECT}/outputs/${EP}/videos/shot-${SHOT_NUM}.mp4"
REPAIR_HISTORY="$PROJECT_ROOT/projects/${PROJECT}/state/audit/${SHOT_ID}-repair-history.json"

# 读取审计结果
if [[ ! -f "$AUDIT_FILE" ]]; then
  echo "错误: 审计文件不存在: $AUDIT_FILE" >&2
  exit 1
fi

REPAIR_ACTION=$(jq -r '.repair_action' "$AUDIT_FILE")

# Trace 写入
./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "read_input" \
  "{\"shot_id\":\"$SHOT_ID\",\"repair_action\":\"$REPAIR_ACTION\"}"
```

### Step 2: 执行修复策略

#### 策略 1: pass（直接通过）

```bash
if [[ "$REPAIR_ACTION" == "pass" ]]; then
  echo "✓ Shot ${SHOT_ID} 通过审计，无需修复"
  
  # 更新状态
  jq '.status = "completed" | .completed_at = "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"' \
    "$PROJECT_ROOT/projects/${PROJECT}/state/${EP}-shot-${SHOT_NUM}.json" > "$PROJECT_ROOT/projects/${PROJECT}/state/${EP}-shot-${SHOT_NUM}.json.tmp"
  mv "$PROJECT_ROOT/projects/${PROJECT}/state/${EP}-shot-${SHOT_NUM}.json.tmp" "$PROJECT_ROOT/projects/${PROJECT}/state/${EP}-shot-${SHOT_NUM}.json"

  # 在线状态同步：Phase 6 通过后立即写回 LanceDB
  python3 scripts/vectordb-manager.py upsert-state "$SHOT_PACKET" || true
  ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "online_state_sync" \
    "{\"stage\":\"pass\",\"shot_id\":\"$SHOT_ID\"}"
  
  # Trace 写入
  ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "write_output" \
    "{\"result\":\"pass\"}"
  
  exit 0
fi
```

#### 策略 2: local_repair（局部修复）

```bash
local_repair() {
  echo "修复 Shot ${SHOT_ID}（局部修复）..."
  
  local issues=$(jq -c '.issues[].items[]' "$AUDIT_FILE")
  local repair_success=true
  
  while IFS= read -r issue; do
    local issue_type=$(echo "$issue" | jq -r '.type')
    
    case "$issue_type" in
      face_mismatch)
        echo "  修复: 脸部不匹配"
        repair_face_with_nanobanana "$issue" || repair_success=false
        ;;
      costume_change)
        echo "  修复: 服装突变"
        adjust_prompt_and_regenerate "$issue" || repair_success=false
        ;;
      prop_disappeared)
        echo "  修复: 道具消失"
        repair_prop_with_seedance "$issue" || repair_success=false
        ;;
      background_jump)
        echo "  修复: 背景跳变"
        use_prev_frame_as_reference || repair_success=false
        ;;
      *)
        echo "  跳过: 未知问题类型 $issue_type"
        ;;
    esac
  done <<< "$issues"
  
  if [[ "$repair_success" == "true" ]]; then
    # 通过信号文件请求 team-lead 重新调度 qa-agent
    echo "请求重新审计..."
    local signal_file="projects/${PROJECT}/state/signals/repair-needs-qa-${EP}-${SHOT_ID}.json"
    mkdir -p "$(dirname "$signal_file")"
    echo "{\"ep\": \"${EP}\", \"shot_id\": \"${SHOT_ID}\", \"requested_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$signal_file"

    # 等待 qa-agent 完成审计（最多 300 秒）
    local audit_file="projects/${PROJECT}/state/audit/${EP}-shot-${SHOT_ID}-audit.json"
    local wait_count=0
    while [[ ! -f "$audit_file" ]] && (( wait_count < 60 )); do
        sleep 5
        (( wait_count++ ))
    done

    if [[ ! -f "$audit_file" ]]; then
        echo "⚠️ qa-agent 未在 300s 内完成审计，跳过验证"
        return 1
    fi
    
    # 检查是否修复成功
    local new_repair_action=$(jq -r '.repair_action' "$audit_file")
    if [[ "$new_repair_action" == "pass" ]]; then
      echo "✓ 修复成功"
      ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "write_output" \
        "{\"result\":\"local_repair_success\"}"
      return 0
    else
      echo "⚠️  修复失败，尝试重生"
      return 1
    fi
  else
    echo "⚠️  局部修复失败"
    return 1
  fi
}

# 修复方法实现

repair_face_with_nanobanana() {
  local issue="$1"
  local character=$(echo "$issue" | jq -r '.character')
  
  echo "    使用 Nanobanana 修复角色脸部: $character"
  
  # 提取中间帧
  local frame_dir="$PROJECT_ROOT/projects/${PROJECT}/outputs/${EP}/audit"
  local total_frames=$(ffprobe -v error -count_frames -select_streams v:0 \
    -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 \
    "$VIDEO_FILE" 2>/dev/null || echo "0")
  
  if [[ "$total_frames" -eq 0 ]]; then
    echo "    错误: 无法读取视频" >&2
    return 1
  fi
  
  local mid_frame=$((total_frames / 2))
  
  ffmpeg -i "$VIDEO_FILE" \
    -vf "select='eq(n\,$mid_frame)'" \
    -vframes 1 \
    "$frame_dir/${SHOT_ID}-problem-frame.png" \
    -y 2>/dev/null || return 1
  
  # 获取参考图
  local ref_image=$(jq -r \
    ".characters[] | select(.id == \"$character\") | .ref_assets[0] // empty" \
    "$SHOT_PACKET")
  
  if [[ -z "$ref_image" ]]; then
    echo "    错误: 未找到参考图" >&2
    return 1
  fi
  
  # 用 Nanobanana 修复
  local prompt="修复角色脸部，使其与参考图一致，保持其他部分不变"
  
  ./scripts/nanobanana-caller.sh generate \
    "$prompt" \
    "16:9" \
    "1080p" \
    "$frame_dir/${SHOT_ID}-fixed-frame.png" \
    2>/dev/null || return 1
  
  # 用修复后的帧重新生成视频（使用 Seedance img2video）
  regenerate_from_fixed_frame "$frame_dir/${SHOT_ID}-fixed-frame.png" || return 1
  
  return 0
}

adjust_prompt_and_regenerate() {
  local issue="$1"
  local issue_type=$(echo "$issue" | jq -r '.type')
  
  echo "    调整提示词并重新生成"
  
  local shot_packet=$(cat "$SHOT_PACKET")
  local original_prompt=$(echo "$shot_packet" | jq -r '.seedance_inputs.prompt')
  local adjusted_prompt="$original_prompt"
  
  case "$issue_type" in
    costume_change)
      adjusted_prompt="${original_prompt}\n\n特别注意：角色服装必须与参考图完全一致，不要改变服装颜色和款式。"
      ;;
    prop_disappeared)
      local prop=$(echo "$issue" | jq -r '.prop')
      adjusted_prompt="${original_prompt}\n\n特别注意：${prop}必须出现在画面中。"
      ;;
  esac
  
  # 更新 shot packet
  echo "$shot_packet" | jq ".seedance_inputs.prompt = \"$adjusted_prompt\"" > "$SHOT_PACKET"

  # 在线状态同步：shot packet 已被修订
  python3 scripts/vectordb-manager.py upsert-state "$SHOT_PACKET" || true
  ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "online_state_sync" \
    "{\"stage\":\"local_repair_prompt_adjusted\",\"shot_id\":\"$SHOT_ID\"}"
  
  # 调用 gen-worker 重新生成
  # 注意：这里需要调用 gen-worker，但由于是 agent 间调用，需要通过 team-lead
  echo "    需要重新生成视频（调用 gen-worker）"
  
  return 0
}

repair_prop_with_seedance() {
  local issue="$1"
  local prop=$(echo "$issue" | jq -r '.prop')
  
  echo "    使用 Seedance 修复道具: $prop"
  
  # 注意：这需要 Seedance 2.0 的视频编辑 API
  # 如果 API 不支持，则回退到 regenerate
  echo "    Seedance 视频编辑 API 暂未支持，回退到重新生成"
  
  return 1
}

use_prev_frame_as_reference() {
  echo "    使用前一帧作为参考"
  
  # 提取前一镜次的尾帧
  local prev_shot_num=$((SHOT_NUM - 1))
  if [[ $prev_shot_num -le 0 ]]; then
    echo "    错误: 没有前一镜次" >&2
    return 1
  fi
  
  local prev_video="$PROJECT_ROOT/projects/${PROJECT}/outputs/${EP}/videos/shot-${prev_shot_num}.mp4"
  if [[ ! -f "$prev_video" ]]; then
    echo "    错误: 前一镜次视频不存在" >&2
    return 1
  fi
  
  local frame_dir="$PROJECT_ROOT/projects/${PROJECT}/outputs/${EP}/audit"
  
  # 提取前一镜次的尾帧
  ffmpeg -sseof -1 -i "$prev_video" \
    -update 1 \
    -q:v 1 \
    "$frame_dir/${EP}-shot-${prev_shot_num}-last-frame.png" \
    -y 2>/dev/null || return 1
  
  # 用尾帧作为首帧参考重新生成
  regenerate_from_fixed_frame "$frame_dir/${EP}-shot-${prev_shot_num}-last-frame.png" || return 1
  
  return 0
}

regenerate_from_fixed_frame() {
  local reference_frame="$1"
  
  echo "    从固定帧重新生成视频"
  
  # 更新 shot packet，设置为 img2video 模式
  local shot_packet=$(cat "$SHOT_PACKET")
  echo "$shot_packet" | jq \
    ".seedance_inputs.generation_mode = \"img2video\" | \
     .seedance_inputs.reference_image_url = \"$reference_frame\"" > "$SHOT_PACKET"

  # 在线状态同步：参考策略已改变
  python3 scripts/vectordb-manager.py upsert-state "$SHOT_PACKET" || true
  ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "online_state_sync" \
    "{\"stage\":\"reference_reseed\",\"shot_id\":\"$SHOT_ID\"}"
  
  # 调用 gen-worker 重新生成
  echo "    需要重新生成视频（调用 gen-worker）"
  
  return 0
}

if [[ "$REPAIR_ACTION" == "local_repair" ]]; then
  if local_repair; then
    exit 0
  else
    # 局部修复失败，转为重新生成
    REPAIR_ACTION="regenerate"
  fi
fi
```

#### 策略 3: regenerate（重新生成）

```bash
regenerate() {
  echo "重新生成 Shot ${SHOT_ID}..."
  
  # 获取当前尝试次数
  local attempt_number=0
  if [[ -f "$REPAIR_HISTORY" ]]; then
    attempt_number=$(jq 'length' "$REPAIR_HISTORY")
  fi
  
  if [[ $attempt_number -ge $MAX_ATTEMPTS ]]; then
    echo "❌ 已达到最大重试次数（${MAX_ATTEMPTS}次），标记为失败"
    
    # 更新状态
    jq '.status = "failed" | .failed_at = "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"' \
      "$PROJECT_ROOT/projects/${PROJECT}/state/${EP}-shot-${SHOT_NUM}.json" > "$PROJECT_ROOT/projects/${PROJECT}/state/${EP}-shot-${SHOT_NUM}.json.tmp"
    mv "$PROJECT_ROOT/projects/${PROJECT}/state/${EP}-shot-${SHOT_NUM}.json.tmp" "$PROJECT_ROOT/projects/${PROJECT}/state/${EP}-shot-${SHOT_NUM}.json"

    python3 scripts/vectordb-manager.py upsert-state "$SHOT_PACKET" || true
    ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "online_state_sync" \
      "{\"stage\":\"failed\",\"shot_id\":\"$SHOT_ID\"}"
    
    # Trace 写入
    ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "write_output" \
      "{\"result\":\"max_attempts_reached\"}"
    
    return 1
  fi
  
  # 分析失败原因，调整策略
  local adjustment=$(analyze_failure_and_adjust)
  
  echo "  调整策略: $adjustment"
  
  case "$adjustment" in
    change_reference)
      # 换一组参考图
      echo "    换一组参考图"
      # 实现：选择备用参考图
      ;;
    adjust_prompt)
      # 调整 prompt
      echo "    调整提示词"
      local new_prompt=$(adjust_prompt_based_on_issues)
      local shot_packet=$(cat "$SHOT_PACKET")
      echo "$shot_packet" | jq ".seedance_inputs.prompt = \"$new_prompt\"" > "$SHOT_PACKET"
      python3 scripts/vectordb-manager.py upsert-state "$SHOT_PACKET" || true
      ;;
    change_model)
      # 换模型
      echo "    换模型"
      local shot_packet=$(cat "$SHOT_PACKET")
      echo "$shot_packet" | jq '.seedance_inputs.model = "doubao-seedance-2.0"' > "$SHOT_PACKET"
      python3 scripts/vectordb-manager.py upsert-state "$SHOT_PACKET" || true
      ;;
  esac
  
  # 记录修复历史
  local history_entry=$(cat <<EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "attempt": $((attempt_number + 1)),
  "repair_action": "regenerate",
  "adjustment": "$adjustment",
  "issues": $(jq '.issues' "$AUDIT_FILE")
}
EOF
)
  
  if [[ -f "$REPAIR_HISTORY" ]]; then
    jq ". += [$history_entry]" "$REPAIR_HISTORY" > "$REPAIR_HISTORY.tmp"
    mv "$REPAIR_HISTORY.tmp" "$REPAIR_HISTORY"
  else
    echo "[$history_entry]" > "$REPAIR_HISTORY"
  fi
  
  # Trace 写入
  ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "execute_repair" \
    "{\"method\":\"regenerate\",\"attempt\":$((attempt_number + 1)),\"adjustment\":\"$adjustment\"}"
  
  # 通过信号文件请求 team-lead 调度 gen-worker 重新生成
  echo "  请求 gen-worker 重新生成..."
  local gen_signal="projects/${PROJECT}/state/signals/repair-needs-gen-${EP}-${SHOT_ID}.json"
  mkdir -p "$(dirname "$gen_signal")"
  echo "{\"ep\": \"${EP}\", \"shot_id\": \"${SHOT_ID}\", \"adjustment\": \"$adjustment\", \"requested_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$gen_signal"
  
  # 等待 gen-worker 完成（最多 600 秒）
  local video_file="projects/${PROJECT}/outputs/${EP}/videos/shot-${SHOT_ID}.mp4"
  local gen_wait=0
  while [[ -f "$gen_signal" ]] && (( gen_wait < 120 )); do
    sleep 5; (( gen_wait++ ))
  done
  
  # 通过信号文件请求 team-lead 重新调度 qa-agent
  echo "  请求重新审计..."
  local qa_signal="projects/${PROJECT}/state/signals/repair-needs-qa-${EP}-${SHOT_ID}.json"
  echo "{\"ep\": \"${EP}\", \"shot_id\": \"${SHOT_ID}\", \"requested_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$qa_signal"
  
  # 等待 qa-agent 完成审计（最多 300 秒）
  local qa_wait=0
  while [[ ! -f "$AUDIT_FILE" ]] && (( qa_wait < 60 )); do
    sleep 5; (( qa_wait++ ))
  done
  
  if [[ ! -f "$AUDIT_FILE" ]]; then
    echo "⚠️ qa-agent 未在 300s 内完成审计，跳过验证"
    return 1
  fi
  
  local new_repair_action=$(jq -r '.repair_action' "$AUDIT_FILE")
  if [[ "$new_repair_action" == "pass" ]]; then
    echo "✓ 重新生成成功"
    ./scripts/trace.sh "$SESSION_ID" "${EP}-repair-trace" "write_output" \
      "{\"result\":\"regenerate_success\"}"
    return 0
  else
    echo "⚠️  重新生成后仍有问题，可能需要再次修复"
    return 1
  fi
}

analyze_failure_and_adjust() {
  # 分析失败原因，决定调整策略
  local issues=$(jq -c '.issues[].items[]' "$AUDIT_FILE")
  
  # 统计问题类型
  local face_issues=$(echo "$issues" | jq -s 'map(select(.type == "face_mismatch")) | length')
  local costume_issues=$(echo "$issues" | jq -s 'map(select(.type == "costume_change")) | length')
  local prop_issues=$(echo "$issues" | jq -s 'map(select(.type | startswith("prop_"))) | length')
  
  # 决策逻辑
  if [[ $face_issues -gt 0 ]]; then
    echo "change_reference"
  elif [[ $costume_issues -gt 0 || $prop_issues -gt 0 ]]; then
    echo "adjust_prompt"
  else
    echo "change_model"
  fi
}

adjust_prompt_based_on_issues() {
  local shot_packet=$(cat "$SHOT_PACKET")
  local original_prompt=$(echo "$shot_packet" | jq -r '.seedance_inputs.prompt')
  local issues=$(jq -c '.issues[].items[]' "$AUDIT_FILE")
  
  local adjustments=""
  
  while IFS= read -r issue; do
    local issue_type=$(echo "$issue" | jq -r '.type')
    
    case "$issue_type" in
      face_mismatch)
        adjustments="${adjustments}\n角色脸部必须与参考图完全一致。"
        ;;
      costume_change)
        adjustments="${adjustments}\n角色服装必须与参考图完全一致。"
        ;;
      prop_appeared|prop_disappeared)
        local prop=$(echo "$issue" | jq -r '.prop // "道具"')
        adjustments="${adjustments}\n${prop}的出现和消失必须符合逻辑。"
        ;;
    esac
  done <<< "$issues"
  
  echo "${original_prompt}${adjustments}"
}

if [[ "$REPAIR_ACTION" == "regenerate" ]]; then
  regenerate
  exit $?
fi
```

## 完成后

写入完成信号，再向 team-lead 发送消息：

```bash
# 写入完成信号（team-lead 通过 watch signals/ 目录感知，无需轮询）
./scripts/signal.sh "$PROJECT" "$SESSION_ID" "repair-agent" "$EP" "$RESULT" \
  "{\"shot_id\":\"$SHOT_ID\"}"

# 通知 team-lead
echo "repair-agent 完成，修复结果: $RESULT，shot: $SHOT_ID"
```

额外要求：

- 只要 shot packet 被修改，就立刻调用 `python3 scripts/vectordb-manager.py upsert-state`
- 所有在线同步都写 trace 事件 `online_state_sync`
- 不要依赖 `workflow-sync.py --sync-vectordb` 事后回填 repair 阶段状态
- `RESULT` 取值：`completed`（pass/修复成功）或 `failed`（达到最大重试次数）

## 修复决策树

```
audit_result.repair_action
├─ pass
│  └─ 直接通过，无需修复
├─ local_repair
│  ├─ face_mismatch → repair_face_with_nanobanana
│  ├─ costume_change → adjust_prompt_and_regenerate
│  ├─ prop_disappeared → repair_prop_with_seedance
│  ├─ background_jump → use_prev_frame_as_reference
│  └─ 修复后重新审计
│     ├─ passed → 完成
│     └─ failed → 转 regenerate
└─ regenerate
   ├─ attempt < max_attempts
   │  ├─ analyze_failure
   │  ├─ adjust_strategy
   │  │  ├─ change_reference
   │  │  ├─ adjust_prompt
   │  │  └─ change_model
   │  ├─ gen-worker (重新生成)
   │  └─ qa-agent (重新审计)
   └─ attempt >= max_attempts
      └─ 标记为 failed
```

## 注意事项

- **最大重试次数**：默认 3 次，可配置
- **修复成本**：local_repair 成本低于 regenerate
- **失败分析**：记录失败原因，用于优化策略
- **人工介入**：严重失败可触发人工审核
- **Agent 间调用**：repair-agent 通过信号文件（`state/signals/repair-needs-qa-*.json` / `repair-needs-gen-*.json`）请求 team-lead 调度 qa-agent 和 gen-worker，不直接 shell 调用其他 agent
- **简化实现**：当前实现为简化版，实际生产环境应完善各修复方法的实现
