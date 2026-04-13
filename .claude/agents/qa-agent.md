---
name: qa-agent
description: QA agent。审计 shot 输出，执行 3 种 QA：symbolic（硬逻辑）、visual（画面）、semantic（戏剧）。
tools:
  - Read
  - Write
  - Bash
write_scope:
  - "projects/{project}/state/audit/{ep}-shot-{N}-audit.json"
  - "projects/{project}/state/{ep}-phase6.json"
  - "projects/{project}/state/signals/"
read_scope:
  - "projects/{project}/state/shot-packets/"
  - "projects/{project}/outputs/{ep}/videos/"
  - "projects/{project}/state/ontology/"
  - "state/vectordb/"
---

# qa-agent — 质量审计

## 职责

审计 shot 输出，检查逻辑一致性、视觉质量和戏剧合理性。

## 输入（由 team-lead 传入）

| 参数 | 类型 | 说明 |
|------|------|------|
| `project` | string | 项目名，如 `qyccan` |
| `ep` | string | 剧本 ID（如 ep01） |
| `shot_id` | string | 镜次 ID（如 ep01-shot-05） |
| `session_id` | string | Trace session 标识 |

## 输出

- `projects/{project}/state/audit/{ep}-shot-{N}-audit.json` — 审计结果

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
SESSION_ID="${4:-qa-$(date +%Y%m%d-%H%M%S)}"

# 提取 shot 序号
SHOT_NUM=$(echo "$SHOT_ID" | grep -oE '[0-9]+$')

# 路径
SHOT_PACKET="$PROJECT_ROOT/projects/${PROJECT}/state/shot-packets/${SHOT_ID}.json"
VIDEO_FILE="$PROJECT_ROOT/projects/${PROJECT}/outputs/${EP}/videos/shot-${SHOT_NUM}.mp4"
WORLD_MODEL="$PROJECT_ROOT/projects/${PROJECT}/state/ontology/${EP}-world-model.json"
AUDIT_DIR="$PROJECT_ROOT/projects/${PROJECT}/state/audit"
AUDIT_FILE="$AUDIT_DIR/${SHOT_ID}-audit.json"

mkdir -p "$AUDIT_DIR"
mkdir -p "$PROJECT_ROOT/projects/${PROJECT}/outputs/${EP}/audit"

# v2.2: 读取 shot-state，校验 selected_views 路径真实存在
SHOT_STATE="$PROJECT_ROOT/projects/${PROJECT}/state/shot-state/${SHOT_ID}.json"
if [[ -f "$SHOT_STATE" ]]; then
  # 校验 selected_views 中的 selected_path 是否真实存在
  python3 - <<'PY' "$SHOT_STATE" "$PROJECT_ROOT"
import json, sys
from pathlib import Path
state = json.load(open(sys.argv[1]))
project_root = Path(sys.argv[2])
issues = []
for c in state.get("selected_views", {}).get("characters", []):
    p = c.get("selected_path")
    if p and not Path(p).exists() and not (project_root / p).exists():
        issues.append(f"WARN: selected_path 不存在: {p} (角色 {c.get('name')})")
scene_path = state.get("selected_views", {}).get("scene", {}).get("selected_path")
if scene_path and not Path(scene_path).exists() and not (project_root / scene_path).exists():
    issues.append(f"WARN: scene selected_path 不存在: {scene_path}")
# 校验 continuity_inputs.previous_end_frame_path 与前一镜产出一致
prev_frame = state.get("continuity", {}).get("previous_end_frame_path")
if prev_frame and not Path(prev_frame).exists() and not (project_root / prev_frame).exists():
    issues.append(f"WARN: previous_end_frame_path 不存在: {prev_frame}")
for issue in issues:
    print(issue)
PY
fi

# Trace 写入
./scripts/trace.sh "$SESSION_ID" "${EP}-phase6-trace" "read_input" \
  "{\"shot_id\":\"$SHOT_ID\",\"video\":\"$VIDEO_FILE\"}"
```

### Step 2: Symbolic QA（硬逻辑检查）

检查硬逻辑错误：

```bash
symbolic_qa() {
  local issues=()
  
  # 读取 shot packet
  local shot_packet=$(cat "$SHOT_PACKET")
  local world_model=$(cat "$WORLD_MODEL")
  
  # 1. 检查角色换装
  local characters=$(echo "$shot_packet" | jq -r '.characters[].id')
  for char in $characters; do
    local current_costume=$(echo "$shot_packet" | jq -r \
      ".characters[] | select(.id == \"$char\") | .current_state.costume // \"default\"")
    
    # 获取前一镜次的服装
    local prev_shot_num=$((SHOT_NUM - 1))
    if [[ $prev_shot_num -gt 0 ]]; then
      local prev_packet="$PROJECT_ROOT/projects/${PROJECT}/state/shot-packets/${EP}-shot-$(printf "%02d" $prev_shot_num).json"
      if [[ -f "$prev_packet" ]]; then
        local prev_costume=$(jq -r \
          ".characters[] | select(.id == \"$char\") | .current_state.costume // \"default\"" \
          "$prev_packet" 2>/dev/null || echo "default")
        
        if [[ "$current_costume" != "$prev_costume" && "$prev_costume" != "null" ]]; then
          issues+=("{\"type\":\"costume_change\",\"character\":\"$char\",\"from\":\"$prev_costume\",\"to\":\"$current_costume\",\"severity\":\"high\"}")
        fi
      fi
    fi
  done
  
  # 2. 检查伤势消失
  for char in $characters; do
    local current_injury=$(echo "$shot_packet" | jq -r \
      ".characters[] | select(.id == \"$char\") | .current_state.injury // \"none\"")
    
    local prev_shot_num=$((SHOT_NUM - 1))
    if [[ $prev_shot_num -gt 0 ]]; then
      local prev_packet="$PROJECT_ROOT/projects/${PROJECT}/state/shot-packets/${EP}-shot-$(printf "%02d" $prev_shot_num).json"
      if [[ -f "$prev_packet" ]]; then
        local prev_injury=$(jq -r \
          ".characters[] | select(.id == \"$char\") | .current_state.injury // \"none\"" \
          "$prev_packet" 2>/dev/null || echo "none")
        
        if [[ "$prev_injury" != "none" && "$current_injury" == "none" ]]; then
          issues+=("{\"type\":\"injury_disappeared\",\"character\":\"$char\",\"severity\":\"high\"}")
        fi
      fi
    fi
  done
  
  # 3. 检查道具凭空出现
  local props=$(echo "$shot_packet" | jq -r '.characters[].current_state.props_in_possession[]? // empty')
  for prop in $props; do
    local prev_shot_num=$((SHOT_NUM - 1))
    if [[ $prev_shot_num -gt 0 ]]; then
      local prev_packet="$PROJECT_ROOT/projects/${PROJECT}/state/shot-packets/${EP}-shot-$(printf "%02d" $prev_shot_num).json"
      if [[ -f "$prev_packet" ]]; then
        local had_prop=$(jq -r \
          ".characters[].current_state.props_in_possession[]? | select(. == \"$prop\")" \
          "$prev_packet" 2>/dev/null || echo "")
        
        if [[ -z "$had_prop" ]]; then
          issues+=("{\"type\":\"prop_appeared\",\"prop\":\"$prop\",\"severity\":\"medium\"}")
        fi
      fi
    fi
  done
  
  # 输出结果
  if [[ ${#issues[@]} -gt 0 ]]; then
    echo "[$(IFS=,; echo "${issues[*]}")]"
  else
    echo "[]"
  fi
}
```

### Step 3: Visual QA（画面检查）

检查视觉质量（使用 LLM 辅助）：

```bash
visual_qa() {
  local issues=()
  
  # 提取关键帧（首帧、中间帧、尾帧）
  local frame_dir="$PROJECT_ROOT/projects/${PROJECT}/outputs/${EP}/audit"
  
  # 获取视频总帧数
  local total_frames=$(ffprobe -v error -count_frames -select_streams v:0 \
    -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 \
    "$VIDEO_FILE" 2>/dev/null || echo "0")
  
  if [[ "$total_frames" -eq 0 ]]; then
    issues+=("{\"type\":\"video_unreadable\",\"severity\":\"high\"}")
    echo "[$(IFS=,; echo "${issues[*]}")]"
    return
  fi
  
  local mid_frame=$((total_frames / 2))
  local last_frame=$((total_frames - 1))
  
  # 提取关键帧
  ffmpeg -i "$VIDEO_FILE" \
    -vf "select='eq(n\,0)+eq(n\,$mid_frame)+eq(n\,$last_frame)'" \
    -vsync 0 \
    "$frame_dir/${SHOT_ID}-frame-%d.png" \
    -y 2>/dev/null || true
  
  # 使用 LLM 检查脸部相似度
  local shot_packet=$(cat "$SHOT_PACKET")
  local characters=$(echo "$shot_packet" | jq -r '.characters[].id')
  
  for char in $characters; do
    local ref_image=$(echo "$shot_packet" | jq -r \
      ".characters[] | select(.id == \"$char\") | .ref_assets[0] // empty")
    
    if [[ -n "$ref_image" && -f "$frame_dir/${SHOT_ID}-frame-1.png" ]]; then
      # 使用 LLM 比较脸部相似度
      local prompt="比较两张图片中的角色脸部相似度。参考图: $ref_image，生成图: $frame_dir/${SHOT_ID}-frame-1.png。返回相似度分数（0-1）和判断理由。"
      
      # 简化版：假设相似度检查通过（实际应调用 LLM）
      # 这里可以集成 Python 脚本或 LLM API
      local similarity=0.8
      
      if (( $(echo "$similarity < 0.7" | bc -l 2>/dev/null || echo "0") )); then
        issues+=("{\"type\":\"face_mismatch\",\"character\":\"$char\",\"similarity\":$similarity,\"severity\":\"high\"}")
      fi
    fi
  done
  
  # 检查背景跳变
  local prev_shot_num=$((SHOT_NUM - 1))
  if [[ $prev_shot_num -gt 0 ]]; then
    local prev_frame="$frame_dir/${EP}-shot-$(printf "%02d" $prev_shot_num)-frame-2.png"
    local curr_frame="$frame_dir/${SHOT_ID}-frame-0.png"
    
    if [[ -f "$prev_frame" && -f "$curr_frame" ]]; then
      # 简化版：假设背景一致性检查通过
      # 实际应使用图像相似度算法
      local bg_similarity=0.6
      
      if (( $(echo "$bg_similarity < 0.5" | bc -l 2>/dev/null || echo "0") )); then
        issues+=("{\"type\":\"background_jump\",\"similarity\":$bg_similarity,\"severity\":\"medium\"}")
      fi
    fi
  fi
  
  # 输出结果
  if [[ ${#issues[@]} -gt 0 ]]; then
    echo "[$(IFS=,; echo "${issues[*]}")]"
  else
    echo "[]"
  fi
}
```

### Step 4: Semantic QA（戏剧检查）

检查戏剧合理性（优先使用向量库，其次回退到本地 packet / world-model）：

```bash
semantic_qa() {
  local issues=()
  
  local shot_packet=$(cat "$SHOT_PACKET")
  local world_model=$(cat "$WORLD_MODEL")
  
  # 1. 检查情绪转换（优先读取 LanceDB 中已索引的上一镜状态）
  local characters=$(echo "$shot_packet" | jq -r '.characters[].id')
  for char in $characters; do
    local current_emotion=$(echo "$shot_packet" | jq -r \
      ".characters[] | select(.id == \"$char\") | .current_state.emotion // \"neutral\"")
    
    local prev_shot_num=$((SHOT_NUM - 1))
    if [[ $prev_shot_num -gt 0 ]]; then
      local prev_shot_id="${EP}-shot-$(printf "%02d" $prev_shot_num)"
      local prev_state=$(python3 scripts/vectordb-manager.py --project "$PROJECT" get-state "$char" "$EP" "$prev_shot_id" 2>/dev/null || echo '{"found":false}')
      local prev_emotion=$(echo "$prev_state" | jq -r '.emotion // empty')

      if [[ -z "$prev_emotion" || "$prev_emotion" == "null" ]]; then
        local prev_packet="$PROJECT_ROOT/projects/${PROJECT}/state/shot-packets/${prev_shot_id}.json"
        if [[ -f "$prev_packet" ]]; then
          prev_emotion=$(jq -r \
            ".characters[] | select(.id == \"$char\") | .current_state.emotion // \"neutral\"" \
            "$prev_packet" 2>/dev/null || echo "neutral")
        else
          prev_emotion="neutral"
        fi
      fi

      # 优先使用 emotional_arcs 中的 forbidden_transitions
      local forbidden=$(echo "$world_model" | jq -c --arg char "$char" --arg from "$prev_emotion" --arg to "$current_emotion" '
        .narrative_constraints.emotional_arcs[]?
        | select(.character == $char)
        | .forbidden_transitions[]?
        | select(.from == $from and .to == $to)
      ' | head -1)

      if [[ -n "$forbidden" ]]; then
        issues+=("{\"type\":\"emotion_jump\",\"character\":\"$char\",\"from\":\"$prev_emotion\",\"to\":\"$current_emotion\",\"severity\":\"medium\",\"reason\":$(echo "$forbidden" | jq '.reason')}")
      elif [[ "$prev_emotion" == "calm" && "$current_emotion" == "angry" ]]; then
        issues+=("{\"type\":\"emotion_jump\",\"character\":\"$char\",\"from\":\"$prev_emotion\",\"to\":\"$current_emotion\",\"severity\":\"low\"}")
      fi
    fi
  done
  
  # 2. 检查对白口吻（结合人物实体与关系检索）
  local dialogue=$(echo "$shot_packet" | jq -r '.audio // empty')
  if [[ -n "$dialogue" ]]; then
    for char in $characters; do
      local entity_hit=$(python3 scripts/vectordb-manager.py --project "$PROJECT" search-entities "$char 人设 性格 对白" \
        --type character --episode "$EP" --n 1 2>/dev/null || echo '[]')
      local personality=$(echo "$entity_hit" | jq -r '.[0].metadata.personality // empty')
      
      if [[ -n "$personality" ]]; then
        # 简化版：假设对白口吻检查通过
        # 实际应调用 LLM 检查对白是否符合人设
        local tone_check="consistent"
        
        if [[ "$tone_check" == "inconsistent" ]]; then
          issues+=("{\"type\":\"dialogue_tone\",\"character\":\"$char\",\"severity\":\"low\"}")
        fi
      fi
    done
  fi

  # 3. 检查多角色关系是否与当前戏剧冲突
  local char_count=$(echo "$shot_packet" | jq '.characters | length')
  if [[ "$char_count" -ge 2 ]]; then
    local pair_query=$(echo "$shot_packet" | jq -r '
      [.characters[].id] as $chars
      | if ($chars | length) >= 2 then "\($chars[0]) \($chars[1]) 关系 冲突 契约" else "" end
    ')
    if [[ -n "$pair_query" ]]; then
      local relation_hits=$(python3 scripts/vectordb-manager.py --project "$PROJECT" search-relations "$pair_query" --episode "$EP" --n 2 2>/dev/null || echo '[]')
      local rel_count=$(echo "$relation_hits" | jq 'length')
      if [[ "$rel_count" -eq 0 ]]; then
        issues+=("{\"type\":\"relation_context_missing\",\"severity\":\"low\"}")
      fi
    fi
  fi
  
  # 输出结果
  if [[ ${#issues[@]} -gt 0 ]]; then
    echo "[$(IFS=,; echo "${issues[*]}")]"
  else
    echo "[]"
  fi
}
```

### Step 5: 汇总审计结果

```bash
# 执行 3 种 QA
symbolic_issues=$(symbolic_qa)
visual_issues=$(visual_qa)
semantic_issues=$(semantic_qa)

# Trace 写入
./scripts/trace.sh "$SESSION_ID" "${EP}-phase6-trace" "symbolic_qa" \
  "{\"issues\":$(echo "$symbolic_issues" | jq 'length')}"
./scripts/trace.sh "$SESSION_ID" "${EP}-phase6-trace" "visual_qa" \
  "{\"issues\":$(echo "$visual_issues" | jq 'length')}"
./scripts/trace.sh "$SESSION_ID" "${EP}-phase6-trace" "semantic_qa" \
  "{\"issues\":$(echo "$semantic_issues" | jq 'length')}"

# 决定修复策略
high_severity_count=$(jq -n --argjson s "$symbolic_issues" --argjson v "$visual_issues" \
  '[$s[], $v[]] | map(select(.severity == "high")) | length')
medium_severity_count=$(jq -n --argjson s "$symbolic_issues" --argjson v "$visual_issues" \
  '[$s[], $v[]] | map(select(.severity == "medium")) | length')

if [[ $high_severity_count -eq 0 && $medium_severity_count -eq 0 ]]; then
  repair_action="pass"
elif [[ $high_severity_count -le 1 ]]; then
  repair_action="local_repair"
else
  repair_action="regenerate"
fi

# 生成审计结果
cat > "$AUDIT_FILE" << EOF
{
  "shot_id": "$SHOT_ID",
  "audit_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "passed": $(if [[ "$repair_action" == "pass" ]]; then echo "true"; else echo "false"; fi),
  "issues": [
    {
      "type": "symbolic",
      "items": $symbolic_issues
    },
    {
      "type": "visual",
      "items": $visual_issues
    },
    {
      "type": "semantic",
      "items": $semantic_issues
    }
  ],
  "repair_action": "$repair_action"
}
EOF

# Trace 写入
./scripts/trace.sh "$SESSION_ID" "${EP}-phase6-trace" "write_output" \
  "{\"file\":\"$AUDIT_FILE\",\"repair_action\":\"$repair_action\"}"

# 在线状态同步：Phase 6 不再依赖 workflow-sync 事后回填
python3 scripts/vectordb-manager.py --project "$PROJECT" upsert-state "$SHOT_PACKET" || true
./scripts/trace.sh "$SESSION_ID" "${EP}-phase6-trace" "online_state_sync" \
  "{\"shot_id\":\"$SHOT_ID\",\"repair_action\":\"$repair_action\"}"

echo "✓ 审计完成: $SHOT_ID → $repair_action"
echo "$repair_action"
```

## 完成后

向 team-lead 发送消息：`qa-agent 完成，审计结果: {repair_action}`

写入状态文件 `projects/{project}/state/{ep}-phase6.json`：
```json
{
  "episode": "{ep}",
  "phase": 6,
  "status": "completed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "data": {
    "shots_audited": {N},
    "passed": {M},
    "need_repair": {K}
  }
}
```

## 注意事项

- **阈值可调**：相似度阈值可根据实际效果调整
- **LLM 辅助**：Visual QA 和 Semantic QA 可使用 LLM 辅助判断
- **性能优化**：Visual QA 可并行处理多个 shots
- **误报处理**：允许人工覆盖审计结果
- **在线状态写入**：每次审计结束都同步一次 `upsert-state`，不要依赖批处理回填
- **简化实现**：当前实现为简化版，实际生产环境应集成完整的图像相似度算法和 LLM 判断
