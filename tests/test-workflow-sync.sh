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

cat > "$FIXTURE_ROOT/projects/demo/outputs/ep01/visual-direction.yaml" <<'EOF'
episode: ep01
total_duration: 24
shots:
  - shot_id: ep01-shot-01
    shot_index: 1
    duration: 12
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
assert all("构图参考@分镜图" in shot["seedance_prompt"] for shot in visual["shots"])

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

archived = root / "projects/demo/state/archive/ep01/ep01-shot-03.json"
assert archived.exists(), archived
PY

echo "PASS: workflow-sync"
