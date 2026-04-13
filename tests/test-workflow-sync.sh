#!/usr/bin/env bash
# tests/test-workflow-sync.sh — workflow-sync.py 回归测试

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

FIXTURE_ROOT="$TMP_DIR/repo"
mkdir -p "$FIXTURE_ROOT/projects/demo/outputs/ep01/videos"
mkdir -p "$FIXTURE_ROOT/projects/demo/state/ontology"
mkdir -p "$FIXTURE_ROOT/projects/demo/assets/characters/images"
mkdir -p "$FIXTURE_ROOT/projects/demo/assets/scenes/images"

cp "$ROOT_DIR/scripts/workflow-sync.py" "$FIXTURE_ROOT/scripts-workflow-sync.py"
cp "$ROOT_DIR/scripts/asset_view_index.py" "$FIXTURE_ROOT/asset_view_index.py"

cat > "$FIXTURE_ROOT/projects/demo/outputs/ep01/visual-direction.yaml" <<'EOF'
episode: ep01
total_duration: 24
shots:
  - shot_id: ep01-shot-01
    shot_index: 1
    duration: 12
    shot_purpose: establish_space
    dramatic_role: establish
    transition_from_previous: cold_open
    emotional_target: 压迫和惊恐
    information_delta: 苏夜发现自己变成了蚕
    next_hook: 为什么会变成蚕
    scene_name: 黑雾森林
    time_of_day: day
    generation_mode: img2video
    camera: |
      0-3秒：大特写主观视角，固定镜头
    audio: |
      苏夜（惊恐）："测试"
    has_dialogue: true
    references:
      characters:
        - name: 苏夜
          variant_id: qingyucan
          image_path: projects/demo/assets/characters/images/苏夜-qingyucan-front.png
      scenes:
        - name: 黑雾森林
          time_of_day: day
          image_path: projects/demo/assets/scenes/images/黑雾森林-day.png
    seedance_prompt: |
      @图片1 作为<苏夜>，场景参考@图片2
      0-3秒：大特写固定镜头，苏夜惊恐
  - shot_id: ep01-shot-02
    shot_index: 2
    duration: 12
    shot_purpose: reveal_change
    dramatic_role: reaction
    transition_from_previous: emotion_push
    emotional_target: 冷静中带一丝不安
    information_delta: 苏夜开始接受当前处境
    next_hook: 下一步行动是什么
    scene_name: 黑雾森林
    time_of_day: day
    generation_mode: img2video
    camera: |
      0-3秒：中景推镜头
    audio: |
      无对白
    has_dialogue: false
    references:
      characters:
        - name: 苏夜
          variant_id: qingyucan
          image_path: projects/demo/assets/characters/images/苏夜-qingyucan-front.png
      scenes:
        - name: 黑雾森林
          time_of_day: day
          image_path: projects/demo/assets/scenes/images/黑雾森林-day.png
    seedance_prompt: |
      @图片1 作为<苏夜>，场景参考@图片2
      0-3秒：中景推镜头，苏夜冷静
EOF

cat > "$FIXTURE_ROOT/projects/demo/state/ontology/ep01-world-model.json" <<'EOF'
{
  "episode": "ep01",
  "entities": {
    "characters": [
      {
        "id": "suye",
        "name": "苏夜",
        "current_variant": "qingyucan",
        "variants": [
          {
            "variant_id": "qingyucan",
            "appearance": "通体碧绿的蚕宝宝"
          }
        ],
        "physical": {
          "form": "青玉蚕",
          "size": "拇指大小"
        },
        "abilities": [
          "吞天口"
        ],
        "constraints": [
          "无法开口说话（蚕形态）",
          "体型极小"
        ]
      }
    ],
    "locations": [
      {
        "id": "heiwu_forest",
        "name": "黑雾森林",
        "functional": {
          "affordances": ["逃跑"]
        }
      }
    ]
  },
  "physics_rules": {
    "gravity": "normal",
    "magic_system": "cultivation",
    "power_scaling": "strict"
  },
  "narrative_constraints": {
    "world_rules": ["灵兽不可突然改变形态"]
  }
}
EOF

touch "$FIXTURE_ROOT/projects/demo/assets/characters/images/苏夜-qingyucan-front.png"
touch "$FIXTURE_ROOT/projects/demo/assets/characters/images/苏夜-qingyucan-side.png"
touch "$FIXTURE_ROOT/projects/demo/assets/scenes/images/黑雾森林-day.png"
touch "$FIXTURE_ROOT/projects/demo/outputs/ep01/videos/shot-01.mp4"
touch "$FIXTURE_ROOT/projects/demo/outputs/ep01/videos/shot-02.mp4"
touch "$FIXTURE_ROOT/projects/demo/outputs/ep01/videos/33e5c7751ecec384.mp4"

# Task 5: stale recovery fixture — shot-03 has video on disk but state says pending
mkdir -p "$FIXTURE_ROOT/projects/demo/state/shot-state"
cat > "$FIXTURE_ROOT/projects/demo/state/shot-state/ep01-shot-03.json" <<'EOF'
{
  "shot_id": "ep01-shot-03",
  "generation_status": { "storyboard": "completed", "video": "pending" },
  "continuity": { "previous_shot_id": "ep01-shot-02", "previous_end_frame_path": null, "recovered_from_outputs": false }
}
EOF
touch "$FIXTURE_ROOT/projects/demo/outputs/ep01/videos/shot-03.mp4"

cat > "$FIXTURE_ROOT/projects/demo/state/ep01-shot-03.json" <<'EOF'
{
  "episode": "ep01",
  "shot_id": "ep01-shot-03",
  "shot_index": 3,
  "status": "completed"
}
EOF

python3 "$FIXTURE_ROOT/scripts-workflow-sync.py" \
  --project-root "$FIXTURE_ROOT" \
  --project demo \
  --episode ep01

python3 - <<'PY' "$FIXTURE_ROOT"
import json
import sys
from pathlib import Path

import yaml

root = Path(sys.argv[1])
visual = yaml.safe_load((root / "projects/demo/outputs/ep01/visual-direction.yaml").read_text())
assert all(shot.get("storyboard_image_path") for shot in visual["shots"])
# 分镜图引用现在是 @图片N（正确的 Seedance 索引格式），不再是 @分镜图
assert all("构图参考@图片" in shot["seedance_prompt"] for shot in visual["shots"]), \
    [shot["seedance_prompt"][-80:] for shot in visual["shots"]]

phase23 = json.loads((root / "projects/demo/state/ep01-phase2.3.json").read_text())
phase35 = json.loads((root / "projects/demo/state/ep01-phase3.5.json").read_text())
phase5 = json.loads((root / "projects/demo/state/ep01-phase5.json").read_text())

assert phase23["status"] == "completed", phase23
assert phase35["status"] == "completed", phase35
assert phase5["status"] == "completed", phase5
assert phase5["data"]["total_shots"] == 2, phase5
assert phase5["data"]["completed"] == 2, phase5

packet = json.loads((root / "projects/demo/state/shot-packets/ep01-shot-01.json").read_text())
assert packet["seedance_inputs"]["prompt"], packet
assert packet["seedance_inputs"]["images"], packet
assert any("storyboard/shot-01.png" in item for item in packet["seedance_inputs"]["images"]), packet
assert packet["story_logic"]["shot_purpose"] == "establish_space", packet
assert packet["story_logic"]["dramatic_role"] == "establish", packet
assert packet["story_logic"]["transition_from_previous"] == "cold_open", packet
assert packet["story_logic"]["emotional_target"] == "压迫和惊恐", packet
assert packet["story_logic"]["information_delta"] == "苏夜发现自己变成了蚕", packet
assert packet["story_logic"]["next_hook"] == "为什么会变成蚕", packet

archived = root / "projects/demo/state/archive/ep01/ep01-shot-03.json"
assert archived.exists(), archived

# Task 1: shot-state 中间层
shot_state = json.loads((root / "projects/demo/state/shot-state/ep01-shot-01.json").read_text())
assert shot_state["shot_id"] == "ep01-shot-01", shot_state
assert shot_state["story_logic"]["shot_purpose"] == "establish_space", shot_state
assert shot_state["camera"]["shot_size"] == "close_up", shot_state
assert shot_state["selected_views"]["characters"][0]["preferred_view"] == "front", shot_state
assert shot_state["continuity"]["previous_shot_id"] is None, shot_state
assert shot_state["generation_status"]["storyboard"] == "completed", shot_state

# Task 2: asset-view-index
view_index = json.loads((root / "projects/demo/state/asset-views/ep01-view-index.json").read_text())
assert view_index["characters"]["苏夜"]["qingyucan"]["front"].endswith("苏夜-qingyucan-front.png"), view_index
assert view_index["characters"]["苏夜"]["qingyucan"]["side"].endswith("苏夜-qingyucan-side.png"), view_index
assert view_index["scenes"]["黑雾森林"]["day"].endswith("黑雾森林-day.png"), view_index

# Human-facing deliverables layer
manifest = json.loads((root / "projects/demo/outputs/ep01/deliverables/manifest.json").read_text())
assert manifest["episode"] == "ep01", manifest
assert manifest["shot_count"] == 2, manifest
assert manifest["final_video"] is None, manifest
assert manifest["shots"][0].endswith("deliverables/shots/shot-01.mp4"), manifest
assert (root / "projects/demo/outputs/ep01/deliverables/shots/shot-01.mp4").exists()
assert (root / "projects/demo/outputs/ep01/deliverables/shots/shot-02.mp4").exists()
assert (root / "projects/demo/outputs/ep01/build/raw-videos/33e5c7751ecec384.mp4").exists()
assert not (root / "projects/demo/outputs/ep01/videos/33e5c7751ecec384.mp4").exists()

# Task 3: shot packet 新增字段
packet = json.loads((root / "projects/demo/state/shot-packets/ep01-shot-01.json").read_text())
assert packet["selected_views"]["characters"][0]["selected_path"].endswith("苏夜-qingyucan-front.png"), packet
assert packet["selected_views"]["scene"]["selected_path"].endswith("黑雾森林-day.png"), packet
assert packet["continuity_inputs"]["previous_shot_id"] is None, packet
assert packet["source_refs"]["storyboard_image_path"].endswith("storyboard/shot-01.png"), packet

# Task 5: stale recovery
recovered = json.loads((root / "projects/demo/state/shot-state/ep01-shot-03.json").read_text())
assert recovered["generation_status"]["video"] == "recovered", recovered
assert recovered["continuity"]["recovered_from_outputs"] is True, recovered
PY

echo "PASS: workflow-sync"
