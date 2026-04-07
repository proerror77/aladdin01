#!/usr/bin/env bash
# tests/test-vectordb-manager.sh — vectordb-manager.py 回归测试

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

DB_PATH="$TMP_DIR/lancedb"
WORLD_MODEL="$TMP_DIR/world-model.json"
SHOT_PACKET="$TMP_DIR/shot-packet.json"

cat > "$WORLD_MODEL" <<'EOF'
{
  "episode": "ep99",
  "entities": {
    "characters": [
      {
        "id": "suye",
        "name": "苏夜",
        "tier": "protagonist",
        "variants": [
          {
            "variant_id": "default",
            "appearance": "青玉蚕形态"
          }
        ],
        "abilities": [
          {
            "name": "吞天口"
          }
        ]
      },
      {
        "id": "yehongyi",
        "name": "叶红衣",
        "tier": "supporting",
        "variants": [
          {
            "variant_id": "default",
            "appearance": "红衣少女"
          }
        ],
        "abilities": []
      }
    ],
    "locations": [
      {
        "id": "heiwu_forest",
        "name": "黑雾森林",
        "temporal_variants": ["night"],
        "atmosphere": "压迫"
      }
    ],
    "skills": [
      {
        "id": "tuntiankou",
        "name": "吞天口",
        "owner": "苏夜",
        "trigger": {
          "type": "active",
          "condition": "濒危反击"
        },
        "cost": {
          "resource": "妖力",
          "side_effect": "体力消耗"
        },
        "constraints": ["必须近距离"],
        "scene_restrictions": ["密林"]
      }
    ]
  },
  "relationships": {
    "social": [
      {
        "from": "suye",
        "to": "yehongyi",
        "relation": "契约"
      }
    ],
    "skill_usage": [
      {
        "from": "suye",
        "to": "tuntiankou",
        "relation": "施展"
      }
    ]
  }
}
EOF

cat > "$SHOT_PACKET" <<'EOF'
{
  "episode": "ep99",
  "shot_id": "ep99-shot-01",
  "characters": [
    {
      "id": "suye",
      "variant": "default",
      "current_state": {
        "form": "青玉蚕",
        "costume": "青玉壳",
        "emotion": "tense",
        "injury": "none",
        "props_in_possession": ["契约印"],
        "knowledge": ["叶红衣在场"]
      }
    },
    {
      "id": "yehongyi",
      "variant": "default",
      "current_state": {
        "form": "human",
        "costume": "红衣",
        "emotion": "calm",
        "injury": "none",
        "props_in_possession": [],
        "knowledge": []
      }
    }
  ]
}
EOF

VECTORDB_PATH="$DB_PATH" "$PYTHON_BIN" "$ROOT_DIR/scripts/vectordb-manager.py" init >/dev/null
VECTORDB_PATH="$DB_PATH" "$PYTHON_BIN" "$ROOT_DIR/scripts/vectordb-manager.py" upsert-world-model "$WORLD_MODEL" >/dev/null

VECTORDB_PATH="$DB_PATH" "$PYTHON_BIN" "$ROOT_DIR/scripts/vectordb-manager.py" search-relations "suye 契约 yehongyi" --episode ep99 --n 3 > "$TMP_DIR/relations.json"
VECTORDB_PATH="$DB_PATH" "$PYTHON_BIN" "$ROOT_DIR/scripts/vectordb-manager.py" search-entities "吞天口 苏夜 active 濒危反击 妖力 体力消耗 必须近距离 密林" --type skill --episode ep99 --n 3 > "$TMP_DIR/skills.json"

VECTORDB_PATH="$DB_PATH" "$PYTHON_BIN" "$ROOT_DIR/scripts/vectordb-manager.py" upsert-state "$SHOT_PACKET" >/dev/null
VECTORDB_PATH="$DB_PATH" "$PYTHON_BIN" "$ROOT_DIR/scripts/vectordb-manager.py" upsert-state "$SHOT_PACKET" >/dev/null
VECTORDB_PATH="$DB_PATH" "$PYTHON_BIN" "$ROOT_DIR/scripts/vectordb-manager.py" get-state suye ep99 ep99-shot-01 > "$TMP_DIR/state.json"
VECTORDB_PATH="$DB_PATH" "$PYTHON_BIN" "$ROOT_DIR/scripts/vectordb-manager.py" stats > "$TMP_DIR/stats.txt"

"$PYTHON_BIN" - <<'PY' "$TMP_DIR" "$DB_PATH"
import json
import sys
from pathlib import Path

import lancedb

tmp_dir = Path(sys.argv[1])
db_path = sys.argv[2]

relations = json.loads((tmp_dir / "relations.json").read_text())
assert relations, relations
assert relations[0]["relation"] == "契约", relations
assert relations[0]["rel_type"] == "social", relations

skills = json.loads((tmp_dir / "skills.json").read_text())
assert skills, skills
assert skills[0]["entity_type"] == "skill", skills
assert skills[0]["name"] == "吞天口", skills

state = json.loads((tmp_dir / "state.json").read_text())
assert state["character_id"] == "suye", state
assert state["shot_id"] == "ep99-shot-01", state
assert state["emotion"] == "tense", state

stats = (tmp_dir / "stats.txt").read_text()
assert db_path in stats, stats
assert "states: 2 条" in stats, stats

db = lancedb.connect(db_path)
assert db.open_table("states").count_rows() == 2
assert db.open_table("relations").count_rows() == 2
PY

echo "PASS: vectordb-manager"
