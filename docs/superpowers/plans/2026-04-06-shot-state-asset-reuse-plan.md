# Shot State And Asset Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable `shot-state` intermediate artifact, an `asset-view-index` selector layer, and filesystem-based recovery so our ontology-first pipeline gains the same reference-image and shot continuity leverage that `nanshanai-animata` gets from its internal asset graph.

**Architecture:** Keep `ontology` and `shot-packet` as the truth layers. Insert `shot-state` between `visual-direction.yaml` and `shot-packets/` so camera intent, continuity inputs, and preferred reference views become explicit, persisted artifacts instead of being recomputed ad hoc. Add a small helper module to index available character and scene views from asset packs, then let `workflow-sync.py` consume that index to enrich shot packets and recover stale generation state from files already on disk.

**Tech Stack:** Python 3, YAML, JSON, shell regression tests, Claude agent markdown contracts

---

## Scope Check

This plan intentionally excludes any new UI. It is one backend vertical slice:

- `shot-state` as the normalized per-shot intermediate model
- `asset-view-index` as deterministic reference selection
- recovery/status sync from files already produced by the pipeline
- agent contract changes so the new artifacts are actually consumed

If you later want browser tooling or a richer operator console, write a separate plan on top of these artifacts instead of mixing UI work into this rollout.

## File Structure

**Create**

- `config/shot-state/shot-state-schema.yaml`
- `scripts/asset_view_index.py`
- `docs/superpowers/plans/2026-04-06-shot-state-asset-reuse-plan.md`

**Modify**

- `scripts/workflow-sync.py`
- `config/shot-packet/shot-packet-schema.yaml`
- `tests/test-workflow-sync.sh`
- `tests/test-agent-workflow-contracts.sh`
- `.claude/agents/memory-agent.md`
- `.claude/agents/shot-compiler-agent.md`
- `.claude/agents/qa-agent.md`
- `README.md`
- `CLAUDE.md`
- `docs/design-workflow-status.md`

**Responsibilities**

- `config/shot-state/shot-state-schema.yaml`: canonical shape of the new intermediate artifact
- `scripts/asset_view_index.py`: pure helper functions for scanning available asset views and selecting best-fit references
- `scripts/workflow-sync.py`: emit `shot-state`, compile `selected_views` into shot packets, and recover stale generation state from filesystem outputs
- `config/shot-packet/shot-packet-schema.yaml`: document new optional packet sections without breaking existing consumers
- `tests/test-workflow-sync.sh`: regression coverage for artifact emission, view selection, and recovery
- `tests/test-agent-workflow-contracts.sh`: ensure agent prompts mention the new artifact and fields
- `.claude/agents/*.md`: teach the agent chain to read `shot-state` before retrieval and validate selected views after generation
- `README.md`, `CLAUDE.md`, `docs/design-workflow-status.md`: keep the documented workflow aligned with shipped behavior

## Target Data Model

`projects/{project}/state/shot-state/{episode}-shot-{N}.json`

```json
{
  "shot_id": "ep01-shot-01",
  "episode": "ep01",
  "scene_id": "ep01-sc01",
  "source_refs": {
    "visual_direction_path": "projects/demo/outputs/ep01/visual-direction.yaml",
    "world_model_path": "projects/demo/state/ontology/ep01-world-model.json",
    "storyboard_image_path": "projects/demo/outputs/ep01/storyboard/shot-01.png"
  },
  "story_logic": {
    "shot_purpose": "establish_space",
    "dramatic_role": "establish",
    "transition_from_previous": "cold_open",
    "emotional_target": "压迫和惊恐",
    "information_delta": "苏夜发现自己变成了蚕",
    "next_hook": "为什么会变成蚕"
  },
  "camera": {
    "raw": "0-3秒：大特写主观视角，固定镜头",
    "shot_size": "close_up",
    "movement": "static",
    "angle": "subjective"
  },
  "selected_views": {
    "characters": [
      {
        "id": "suye",
        "name": "苏夜",
        "variant_id": "qingyucan",
        "preferred_view": "front",
        "selected_path": "projects/demo/assets/characters/images/苏夜-qingyucan-front.png",
        "fallback_order": ["front", "side", "back"]
      }
    ],
    "scene": {
      "name": "黑雾森林",
      "preferred_view": "day",
      "selected_path": "projects/demo/assets/scenes/images/黑雾森林-day.png"
    }
  },
  "continuity": {
    "previous_shot_id": null,
    "previous_end_frame_path": null,
    "recovered_from_outputs": false
  },
  "generation_status": {
    "storyboard": "completed",
    "video": "pending"
  }
}
```

## Task 1: Define And Emit `shot-state`

**Files:**

- Create: `config/shot-state/shot-state-schema.yaml`
- Modify: `scripts/workflow-sync.py`
- Test: `tests/test-workflow-sync.sh`

- [ ] **Step 1: Write the failing regression assertions**

Add these assertions near the existing shot packet checks in `tests/test-workflow-sync.sh`:

```python
shot_state = json.loads((root / "projects/demo/state/shot-state/ep01-shot-01.json").read_text())
assert shot_state["shot_id"] == "ep01-shot-01", shot_state
assert shot_state["story_logic"]["shot_purpose"] == "establish_space", shot_state
assert shot_state["camera"]["shot_size"] == "close_up", shot_state
assert shot_state["selected_views"]["characters"][0]["preferred_view"] == "front", shot_state
assert shot_state["continuity"]["previous_shot_id"] is None, shot_state
```

- [ ] **Step 2: Run the sync regression to verify it fails**

Run:

```bash
bash tests/test-workflow-sync.sh
```

Expected:

```text
Traceback ... FileNotFoundError: .../state/shot-state/ep01-shot-01.json
```

- [ ] **Step 3: Add the schema and emit the new artifact from `workflow-sync.py`**

Create `config/shot-state/shot-state-schema.yaml` with the normalized fields:

```yaml
version: "1.0"
required_fields:
  - shot_id
  - episode
  - scene_id
  - source_refs
  - story_logic
  - camera
  - selected_views
  - continuity
  - generation_status
schema:
  shot_id: string
  episode: string
  scene_id: string
  source_refs: object
  story_logic: object
  camera: object
  selected_views: object
  continuity: object
  generation_status: object
```

In `scripts/workflow-sync.py`, add a focused builder and write path:

```python
def build_shot_state_record(
    episode: str,
    shot: dict[str, Any],
    scene_id: str,
    visual_direction_path: Path,
    world_model_path: Path,
    selected_views: dict[str, Any],
    previous_shot_id: str | None,
    previous_end_frame_path: str | None,
) -> dict[str, Any]:
    return {
        "shot_id": shot["shot_id"],
        "episode": episode,
        "scene_id": scene_id,
        "source_refs": {
            "visual_direction_path": str(visual_direction_path),
            "world_model_path": str(world_model_path),
            "storyboard_image_path": shot.get("storyboard_image_path"),
        },
        "story_logic": {
            "shot_purpose": shot.get("shot_purpose"),
            "dramatic_role": shot.get("dramatic_role"),
            "transition_from_previous": shot.get("transition_from_previous"),
            "emotional_target": infer_emotional_target(shot),
            "information_delta": infer_information_delta(shot),
            "next_hook": infer_next_hook(shot, shot.get("shot_index", 0), 0),
        },
        "camera": {
            "raw": shot.get("camera", ""),
            "shot_size": parse_camera_shot_size(shot.get("camera", "")),
            "movement": parse_camera_movement(shot.get("camera", "")),
            "angle": parse_camera_angle(shot.get("camera", "")),
        },
        "selected_views": selected_views,
        "continuity": {
            "previous_shot_id": previous_shot_id,
            "previous_end_frame_path": previous_end_frame_path,
            "recovered_from_outputs": False,
        },
        "generation_status": {
            "storyboard": "completed" if shot.get("storyboard_image_path") else "pending",
            "video": "pending",
        },
    }
```

- [ ] **Step 4: Run the regression again**

Run:

```bash
bash tests/test-workflow-sync.sh
```

Expected:

```text
PASS: workflow-sync
```

- [ ] **Step 5: Commit**

```bash
git add config/shot-state/shot-state-schema.yaml scripts/workflow-sync.py tests/test-workflow-sync.sh
git commit -m "feat: emit normalized shot state artifacts"
```

## Task 2: Add Deterministic Asset View Indexing

**Files:**

- Create: `scripts/asset_view_index.py`
- Modify: `scripts/workflow-sync.py`
- Modify: `tests/test-workflow-sync.sh`

- [ ] **Step 1: Add a failing assertion for indexed views**

Extend `tests/test-workflow-sync.sh` with:

```python
view_index = json.loads((root / "projects/demo/state/asset-views/ep01-view-index.json").read_text())
assert view_index["characters"]["苏夜"]["qingyucan"]["front"].endswith("苏夜-qingyucan-front.png"), view_index
assert view_index["characters"]["苏夜"]["qingyucan"]["side"].endswith("苏夜-qingyucan-side.png"), view_index
assert view_index["scenes"]["黑雾森林"]["day"].endswith("黑雾森林-day.png"), view_index
```

- [ ] **Step 2: Run the regression to confirm the missing index**

Run:

```bash
bash tests/test-workflow-sync.sh
```

Expected:

```text
Traceback ... FileNotFoundError: .../state/asset-views/ep01-view-index.json
```

- [ ] **Step 3: Implement `scripts/asset_view_index.py` and wire it into `workflow-sync.py`**

Create the helper:

```python
from pathlib import Path

CHARACTER_VIEW_SUFFIXES = ("front", "side", "back")

def build_asset_view_index(project_root: Path, project: str) -> dict:
    base = project_root / "projects" / project / "assets"
    index = {"characters": {}, "scenes": {}, "props": {}}
    for image_path in (base / "characters" / "images").glob("*.png"):
        stem = image_path.stem
        if "-" not in stem:
            continue
        name, variant_id, view = stem.rsplit("-", 2)
        index["characters"].setdefault(name, {}).setdefault(variant_id, {})[view] = str(image_path)
    for image_path in (base / "scenes" / "images").glob("*.png"):
        stem = image_path.stem
        if "-" not in stem:
            continue
        scene_name, time_of_day = stem.rsplit("-", 1)
        index["scenes"].setdefault(scene_name, {})[time_of_day] = str(image_path)
    return index
```

In `scripts/workflow-sync.py`, import it through the script directory and persist:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from asset_view_index import build_asset_view_index

asset_view_index = build_asset_view_index(project_root, project)
write_json(asset_views_dir / f"{episode}-view-index.json", asset_view_index)
```

- [ ] **Step 4: Run the regression**

Run:

```bash
bash tests/test-workflow-sync.sh
```

Expected:

```text
PASS: workflow-sync
```

- [ ] **Step 5: Commit**

```bash
git add scripts/asset_view_index.py scripts/workflow-sync.py tests/test-workflow-sync.sh
git commit -m "feat: index character and scene asset views"
```

## Task 3: Enrich Shot Packets With Selected Views And Continuity Inputs

**Files:**

- Modify: `scripts/workflow-sync.py`
- Modify: `config/shot-packet/shot-packet-schema.yaml`
- Modify: `tests/test-workflow-sync.sh`

- [ ] **Step 1: Add failing assertions for packet enrichment**

Extend `tests/test-workflow-sync.sh`:

```python
packet = json.loads((root / "projects/demo/state/shot-packets/ep01-shot-01.json").read_text())
assert packet["selected_views"]["characters"][0]["selected_path"].endswith("苏夜-qingyucan-front.png"), packet
assert packet["selected_views"]["scene"]["selected_path"].endswith("黑雾森林-day.png"), packet
assert packet["continuity_inputs"]["previous_shot_id"] is None, packet
assert packet["source_refs"]["storyboard_image_path"].endswith("storyboard/shot-01.png"), packet
```

- [ ] **Step 2: Run the sync regression and capture the failure**

Run:

```bash
bash tests/test-workflow-sync.sh
```

Expected:

```text
KeyError: 'selected_views'
```

- [ ] **Step 3: Add the packet fields and fill them from `shot-state`**

Update `config/shot-packet/shot-packet-schema.yaml`:

```yaml
optional_fields:
  - source_refs
  - selected_views
  - continuity_inputs
  - forbidden_changes
  - repair_policy
  - ontology_constraints
```

Add these sections to the compiled packet in `scripts/workflow-sync.py`:

```python
packet["source_refs"] = shot_state["source_refs"]
packet["selected_views"] = shot_state["selected_views"]
packet["continuity_inputs"] = {
    "previous_shot_id": shot_state["continuity"]["previous_shot_id"],
    "previous_end_frame_path": shot_state["continuity"]["previous_end_frame_path"],
}
```

Use deterministic fallback order when selecting character views:

```python
fallback_order = ["front", "side", "back"]
selected_path = None
for candidate in fallback_order:
    selected_path = char_views.get(candidate)
    if selected_path:
        preferred_view = candidate
        break
```

- [ ] **Step 4: Run the sync regression again**

Run:

```bash
bash tests/test-workflow-sync.sh
```

Expected:

```text
PASS: workflow-sync
```

- [ ] **Step 5: Commit**

```bash
git add scripts/workflow-sync.py config/shot-packet/shot-packet-schema.yaml tests/test-workflow-sync.sh
git commit -m "feat: compile selected views into shot packets"
```

## Task 4: Teach Agents To Read `shot-state` Before Retrieval

**Files:**

- Modify: `.claude/agents/memory-agent.md`
- Modify: `.claude/agents/shot-compiler-agent.md`
- Modify: `.claude/agents/qa-agent.md`
- Modify: `tests/test-agent-workflow-contracts.sh`

- [ ] **Step 1: Add failing contract checks**

Append these checks in `tests/test-agent-workflow-contracts.sh`:

```bash
assert_contains "memory-agent 读取 shot-state" 'shot-state' "$ROOT_DIR/.claude/agents/memory-agent.md"
assert_contains "memory-agent 使用 preferred_view" 'preferred_view|selected_views' "$ROOT_DIR/.claude/agents/memory-agent.md"
assert_contains "shot-compiler-agent 写入 selected_views" 'selected_views' "$ROOT_DIR/.claude/agents/shot-compiler-agent.md"
assert_contains "shot-compiler-agent 写入 continuity_inputs" 'continuity_inputs' "$ROOT_DIR/.claude/agents/shot-compiler-agent.md"
assert_contains "qa-agent 校验 selected_views" 'selected_views|preferred_view' "$ROOT_DIR/.claude/agents/qa-agent.md"
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run:

```bash
bash tests/test-agent-workflow-contracts.sh
```

Expected:

```text
FAIL: memory-agent 读取 shot-state
FAIL: shot-compiler-agent 写入 selected_views
```

- [ ] **Step 3: Update the agent contracts**

In `.claude/agents/memory-agent.md`, add an explicit read-before-search step:

```markdown
0. 先读取 `projects/{project}/state/shot-state/{episode}-shot-{N}.json`
1. 用 `selected_views.characters[*].preferred_view` 和 `selected_views.scene.preferred_view` 规划 reference 检索
2. 再执行 `search-entities` / `get-state` / `search-relations` / `search-assets`
```

In `.claude/agents/shot-compiler-agent.md`, make the new fields mandatory:

```markdown
- 将 `source_refs`、`selected_views`、`continuity_inputs` 写入 shot packet
- 若 `previous_end_frame_path` 存在，必须进入 `seedance_inputs.images`
```

In `.claude/agents/qa-agent.md`, add validation rules:

```markdown
- 校验 `selected_views` 中的 `selected_path` 是否真实存在
- 校验 packet 中 `continuity_inputs.previous_end_frame_path` 与前一镜产出一致
```

- [ ] **Step 4: Run the contract test**

Run:

```bash
bash tests/test-agent-workflow-contracts.sh
```

Expected:

```text
全部通过 ✓
```

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/memory-agent.md .claude/agents/shot-compiler-agent.md .claude/agents/qa-agent.md tests/test-agent-workflow-contracts.sh
git commit -m "feat: wire shot state into agent contracts"
```

## Task 5: Recover Stale Generation State From Filesystem Outputs

**Files:**

- Modify: `scripts/workflow-sync.py`
- Modify: `tests/test-workflow-sync.sh`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/design-workflow-status.md`

- [ ] **Step 1: Add a failing recovery assertion**

In `tests/test-workflow-sync.sh`, seed a stale state file:

```bash
mkdir -p "$FIXTURE_ROOT/projects/demo/state/shot-state"
cat > "$FIXTURE_ROOT/projects/demo/state/shot-state/ep01-shot-02.json" <<'EOF'
{
  "shot_id": "ep01-shot-02",
  "generation_status": {
    "storyboard": "completed",
    "video": "pending"
  },
  "continuity": {
    "previous_shot_id": "ep01-shot-01",
    "previous_end_frame_path": null,
    "recovered_from_outputs": false
  }
}
EOF
```

Then assert after sync:

```python
recovered_state = json.loads((root / "projects/demo/state/shot-state/ep01-shot-02.json").read_text())
assert recovered_state["generation_status"]["video"] == "recovered", recovered_state
assert recovered_state["continuity"]["recovered_from_outputs"] is True, recovered_state
```

- [ ] **Step 2: Run the sync regression and verify recovery is missing**

Run:

```bash
bash tests/test-workflow-sync.sh
```

Expected:

```text
AssertionError: {'video': 'pending', ...}
```

- [ ] **Step 3: Implement recovery in `workflow-sync.py`**

Add a recovery helper:

```python
def recover_generation_status(shot_state: dict[str, Any], output_video: Path, end_frame: Path | None) -> dict[str, Any]:
    if output_video.exists():
        shot_state["generation_status"]["video"] = "recovered"
        shot_state["continuity"]["recovered_from_outputs"] = True
    if end_frame and end_frame.exists():
        shot_state["continuity"]["previous_end_frame_path"] = str(end_frame)
    return shot_state
```

Call it while iterating shots, using:

```python
video_path = outputs_dir / "videos" / f"shot-{shot_index:02d}.mp4"
end_frame_path = outputs_dir / "storyboard" / f"{episode}-shot-{shot_index:02d}-end-frame.png"
shot_state = recover_generation_status(shot_state, video_path, end_frame_path)
```

- [ ] **Step 4: Update the docs to describe the new artifacts**

Add short sections to:

```markdown
README.md
- `state/shot-state/` — 规范化分镜中间层
- `state/asset-views/` — 资产视角索引

CLAUDE.md
- Phase 3.5 先读取 `shot-state` 再做 memory-agent 检索
- `workflow-sync.py` 会从现有视频和 end-frame 恢复 stale state

docs/design-workflow-status.md
- 记录 `shot-state -> shot-packet -> video` 的状态流转
```

- [ ] **Step 5: Run the full regression set**

Run:

```bash
bash tests/test-workflow-sync.sh
bash tests/test-agent-workflow-contracts.sh
```

Expected:

```text
PASS: workflow-sync
全部通过 ✓
```

- [ ] **Step 6: Commit**

```bash
git add scripts/workflow-sync.py tests/test-workflow-sync.sh README.md CLAUDE.md docs/design-workflow-status.md
git commit -m "feat: recover stale shot generation state from outputs"
```

## Self-Review

**Spec coverage**

- `人物关系` 没有被降级成字符串图谱；仍然依赖现有 ontology 和 `search-relations`
- `图片` 增加了视角索引与 deterministic selection
- `分镜表` 增加了显式 `shot-state` 中间层
- `恢复逻辑` 通过 `workflow-sync.py` 从已有产物反推状态
- `agent 消费链路` 通过 contract test 强制接入

**Placeholder scan**

- No `TODO`
- No unspecified file paths
- No “write tests” without concrete assertions

**Type consistency**

- Artifact names are consistent: `shot-state`, `asset-views`, `selected_views`, `continuity_inputs`, `source_refs`
- Recovery status uses one explicit value: `recovered`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-06-shot-state-asset-reuse-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
