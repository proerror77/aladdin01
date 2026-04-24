#!/usr/bin/env bash
# tests/test-ad-workflow.sh — 广告片工作流契约测试

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

python3 "$ROOT_DIR/scripts/ad-workflow.py" init \
  --project-root "$TMP_DIR" \
  --project demo \
  --ad launch15 \
  --product "AI广告助手" \
  --brand "Aladdin Ads" \
  --duration 15 \
  --ratio 9:16 \
  --selling-point "先搭广告结构" \
  --selling-point "一张图生成可拍 storyboard" \
  --proof "同一个人物贯穿全片" \
  --cta "现在生成第一条广告"

STRUCTURE="$TMP_DIR/projects/demo/outputs/ads/launch15/ad-structure.yaml"
python3 "$ROOT_DIR/scripts/ad-workflow.py" validate --structure "$STRUCTURE"

python3 - <<'PY' "$STRUCTURE" "$TMP_DIR"
import json
import sys
from pathlib import Path

import yaml

structure_path = Path(sys.argv[1])
root = Path(sys.argv[2])
data = yaml.safe_load(structure_path.read_text())

assert data["target_duration_sec"] == 15, data
assert [beat["role"] for beat in data["beats"]] == ["hook", "product", "function", "trust", "cta"], data["beats"]
assert sum(beat["duration_sec"] for beat in data["beats"]) == 15, data["beats"]
assert len(data["seedance"]["segments"]) == 1, data["seedance"]["segments"]
assert data["seedance"]["segments"][0]["duration_sec"] == 15, data["seedance"]["segments"]
assert data["storyboard"]["panel_count"] == 5, data["storyboard"]

prompt = (root / data["storyboard"]["prompt_path"]).read_text()
for token in ["5 个", "时间轴", "人物动作", "字幕/台词", "品牌"]:
    assert token in prompt, prompt

payload_path = root / data["seedance"]["segments"][0]["payload_path"]
payload = json.loads(payload_path.read_text())
assert payload["command"] == "multimodal2video", payload
assert payload["duration"] == 15, payload
assert payload["images"][0].endswith("ad-storyboard.png"), payload

state = yaml.safe_load((root / "projects/demo/state/ads/launch15-phase1.json").read_text())
assert state["status"] == "completed", state
PY

python3 "$ROOT_DIR/scripts/ad-workflow.py" init \
  --project-root "$TMP_DIR" \
  --project demo \
  --ad launch60 \
  --product "AI广告助手" \
  --duration 60 \
  --cta "预约演示"

python3 - <<'PY' "$TMP_DIR/projects/demo/outputs/ads/launch60/ad-structure.yaml"
import sys
from pathlib import Path

import yaml

data = yaml.safe_load(Path(sys.argv[1]).read_text())
segments = data["seedance"]["segments"]
assert len(segments) == 4, segments
assert [s["duration_sec"] for s in segments] == [15, 15, 15, 15], segments
assert sum(s["duration_sec"] for s in segments) == 60, segments
assert all(s["beat_roles"] for s in segments), segments
PY

echo "ad-workflow tests passed"
