#!/usr/bin/env python3
"""
workflow-sync.py - 修复并同步项目工作流产物、阶段状态和向量库。

用途：
1. 为 visual-direction.yaml 补齐 storyboard_image_path，并生成本地 fallback 分镜图
2. 从 visual-direction.yaml + world-model.json 编译 shot packets
3. 修复 phase / shot 状态文件，使其与现有产物一致
4. 可选：将 world model / assets / shot states 同步到 LanceDB

示例：
  python3 scripts/workflow-sync.py --project qyccan --episode ep01
  python3 scripts/workflow-sync.py --project qyccan --episode ep01 --sync-vectordb
  python3 scripts/workflow-sync.py --project qyccan --all-output-episodes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from asset_view_index import build_asset_view_index, select_character_view, select_scene_view
    _ASSET_VIEW_INDEX_AVAILABLE = True
except ImportError:
    _ASSET_VIEW_INDEX_AVAILABLE = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML 顶层必须是 object: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            data,
            fh,
            allow_unicode=True,
            sort_keys=False,
            width=120,
            default_flow_style=False,
        )


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def relpath(project_root: Path, path: Path) -> str:
    return path.relative_to(project_root).as_posix()


def run(cmd: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
    )


def repo_python(project_root: Path) -> str:
    venv_python = project_root / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def canonical_character_id(name: str, world_char: dict[str, Any] | None) -> str:
    if world_char and world_char.get("id"):
        return str(world_char["id"])
    return re.sub(r"[^a-z0-9]+", "_", name.lower()) or name


def parse_camera_block(camera_text: str) -> dict[str, str]:
    line = (camera_text or "").splitlines()[0].strip()
    shot_size = "medium"
    movement = "static"
    lens_style = "cinematic"

    if any(token in line for token in ("大特写", "特写", "近景")):
        shot_size = "close_up"
    elif any(token in line for token in ("中景",)):
        shot_size = "medium"
    elif any(token in line for token in ("全景", "远景", "大远景")):
        shot_size = "wide"
    elif any(token in line for token in ("大全景",)):
        shot_size = "wide"

    if any(token in line for token in ("推镜头", "拉镜头", "跟镜头", "环绕", "希区柯克变焦")):
        movement = "dolly"
    elif "摇镜头" in line:
        movement = "pan"
    elif "升降" in line:
        movement = "crane"
    elif "手持" in line:
        movement = "dolly"
        lens_style = "documentary"

    return {
        "shot_size": shot_size,
        "movement": movement,
        "lens_style": lens_style,
        "raw": camera_text.strip(),
    }


def infer_emotion(shot: dict[str, Any]) -> str:
    audio = str(shot.get("audio") or "")
    action = str(shot.get("action") or "")
    text = f"{audio}\n{action}"
    for keyword, emotion in [
        ("崩溃", "panicked"),
        ("惊恐", "panicked"),
        ("愤怒", "angry"),
        ("怒", "angry"),
        ("绝望", "despair"),
        ("震惊", "shocked"),
        ("期待", "hopeful"),
        ("得意", "triumphant"),
        ("冷静", "calm"),
    ]:
        if keyword in text:
            return emotion
    return "neutral"


def first_nonempty_line(text: str, default: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return default


def infer_dramatic_role(shot: dict[str, Any], shot_index: int, total_shots: int) -> str:
    explicit = str(shot.get("dramatic_role") or "").strip()
    if explicit:
        return explicit

    action_text = f"{shot.get('action') or ''}\n{shot.get('audio') or ''}"
    if shot_index == 1:
        return "establish"
    if shot_index >= total_shots:
        return "resolution"
    if any(token in action_text for token in ("特写", "细节", "契约", "道具")):
        return "detail"
    if any(token in action_text for token in ("震惊", "崩溃", "反应", "沉默")):
        return "reaction"
    return "approach"


def infer_shot_purpose(shot: dict[str, Any], dramatic_role: str) -> str:
    explicit = str(shot.get("shot_purpose") or "").strip()
    if explicit:
        return explicit

    mapping = {
        "establish": "establish_space",
        "approach": "introduce_subject",
        "detail": "reveal_change",
        "reaction": "land_reaction",
        "resolution": "land_result",
    }
    return mapping.get(dramatic_role, "advance_story")


def infer_transition_from_previous(shot: dict[str, Any], shot_index: int) -> str:
    explicit = str(shot.get("transition_from_previous") or "").strip()
    if explicit:
        return explicit

    transition = str(shot.get("transition") or "").strip()
    camera = str(shot.get("camera") or "")
    if shot_index == 1:
        return "cold_open"
    if any(token in transition for token in ("叠化", "淡入", "淡出")):
        return "dissolve"
    if "看向" in camera or "视线" in camera:
        return "gaze_cut"
    if any(token in camera for token in ("推镜头", "缓慢推近", "急速推近")):
        return "push_in"
    if any(token in camera for token in ("拉镜头", "拉远")):
        return "pull_back"
    return "action_result"


def infer_emotional_target_text(shot: dict[str, Any]) -> str:
    explicit = str(shot.get("emotional_target") or "").strip()
    if explicit:
        return explicit

    mapping = {
        "panicked": "惊恐和失控",
        "angry": "威胁和怒意",
        "despair": "绝望和下坠",
        "shocked": "震惊和停顿",
        "hopeful": "期待和拉升",
        "triumphant": "反差和得意",
        "calm": "压抑中的冷静",
        "neutral": "维持叙事推进",
    }
    return mapping.get(infer_emotion(shot), "维持叙事推进")


def infer_information_delta(shot: dict[str, Any]) -> str:
    explicit = str(shot.get("information_delta") or "").strip()
    if explicit:
        return explicit
    return first_nonempty_line(str(shot.get("action") or ""), "推进剧情信息")


def infer_next_hook(shot: dict[str, Any], shot_index: int, total_shots: int) -> str:
    explicit = str(shot.get("next_hook") or "").strip()
    if explicit:
        return explicit
    if shot_index >= total_shots:
        return "情绪收束"
    return "推动观众进入下一镜"


def collect_world_rules(world_model: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    physics = world_model.get("physics") or world_model.get("physics_rules") or {}
    if isinstance(physics, dict):
        gravity = physics.get("gravity")
        magic = physics.get("magic_system")
        scaling = physics.get("power_scaling")
        if gravity:
            rules.append(f"gravity={gravity}")
        if magic:
            rules.append(f"magic_system={magic}")
        if scaling:
            rules.append(f"power_scaling={scaling}")
        notes = physics.get("notes")
        if notes:
            rules.append(str(notes))

    narrative = world_model.get("narrative_constraints") or {}
    if isinstance(narrative, dict):
        narrative_rules = narrative.get("world_rules") or []
        if isinstance(narrative_rules, list):
            rules.extend(str(item) for item in narrative_rules if item)

    return dedupe_keep_order(rules)


def character_variant_record(world_char: dict[str, Any] | None, variant_id: str) -> dict[str, Any]:
    if not world_char:
        return {}
    variants = world_char.get("variants") or []
    if isinstance(variants, dict):
        if variant_id in variants:
            record = variants[variant_id]
            if isinstance(record, dict):
                return record
            return {"appearance": str(record)}
    elif isinstance(variants, list):
        for variant in variants:
            if str(variant.get("variant_id")) == variant_id:
                return variant
    return {}


def infer_forbidden_changes(name: str, variant_id: str, world_char: dict[str, Any] | None) -> list[str]:
    forbidden = [f"保持{name}的当前形态（{variant_id}）"]
    if not world_char:
        return forbidden

    constraints = world_char.get("constraints") or []
    for item in constraints:
        text = str(item)
        if "说话" in text and any(flag in text for flag in ("无法", "不能", "不会")):
            forbidden.append(f"不要让{name}说话")
        if "飞" in text and any(flag in text for flag in ("无法", "不能", "不会")):
            forbidden.append(f"不要让{name}飞行")
        if "体型" in text or "拇指" in text:
            forbidden.append(f"保持{name}的体型比例")
    return dedupe_keep_order(forbidden)


def expand_character_assets(project_root: Path, image_path: str | None) -> list[str]:
    if not image_path:
        return []
    source = project_root / image_path
    if not source.exists():
        return []
    items = [image_path]
    stem = source.stem
    suffix = source.suffix
    if stem.endswith("-front"):
        prefix = stem[:-6]
        for extra in ("side", "back"):
            candidate = source.with_name(f"{prefix}-{extra}{suffix}")
            if candidate.exists():
                items.append(relpath(project_root, candidate))
    return dedupe_keep_order(items)


def generate_storyboard_image(project_root: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg 不可用，无法生成 fallback 分镜图")

    filter_graph = (
        "drawgrid=w=160:h=90:t=1:c=0x8a8a8a,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x202020:t=6"
    )
    cmd = [
        ffmpeg,
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=0xeeeeee:s=1280x720",
        "-vf",
        filter_graph,
        "-frames:v",
        "1",
        "-y",
        str(target),
    ]
    run(cmd, cwd=project_root)


def storyboard_image_index(shot: dict[str, Any], project_root: Path) -> int:
    """计算分镜图在 images 数组中的 1-based 索引。
    images 顺序：角色图（front/side/back，按实际存在文件数）+ 场景图 + 分镜图
    """
    references = shot.get("references") or {}
    char_image_count = 0
    for ref in references.get("characters") or []:
        image_path = ref.get("image_path")
        if not image_path:
            continue
        source = project_root / image_path
        if not source.exists():
            continue
        char_image_count += 1  # front（已验证存在）
        stem = source.stem
        suffix = source.suffix
        if stem.endswith("-front"):
            prefix = stem[:-6]
            for extra in ("side", "back"):
                if source.with_name(f"{prefix}-{extra}{suffix}").exists():
                    char_image_count += 1
    scene_image_count = sum(
        1 for ref in (references.get("scenes") or [])
        if ref.get("image_path") and (project_root / ref["image_path"]).exists()
    )
    return char_image_count + scene_image_count + 1  # 1-based


def ensure_storyboards(
    project_root: Path,
    project: str,
    episode: str,
    visual_data: dict[str, Any],
) -> tuple[int, int]:
    shots = visual_data.get("shots") or []
    storyboard_dir = project_root / "projects" / project / "outputs" / episode / "storyboard"
    storyboard_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    prompt_updates = 0

    for shot in shots:
        shot_index = int(shot["shot_index"])
        rel_output = f"projects/{project}/outputs/{episode}/storyboard/shot-{shot_index:02d}.png"
        output = project_root / rel_output
        if not output.exists():
            generate_storyboard_image(project_root, output)
            generated += 1

        if shot.get("storyboard_image_path") != rel_output:
            shot["storyboard_image_path"] = rel_output

        prompt = str(shot.get("seedance_prompt") or "").rstrip()

        # 计算分镜图在 images 数组中的正确 @图片N 索引
        sb_index = storyboard_image_index(shot, project_root)
        old_marker = "构图参考@分镜图（仅参考景别和角色位置，不复制细节）"
        new_marker = f"构图参考@图片{sb_index}（仅参考景别和角色位置，不复制细节）"

        # 替换旧的 @分镜图 引用（如果存在）
        if old_marker in prompt:
            prompt = prompt.replace(old_marker, new_marker)
            shot["seedance_prompt"] = prompt
            prompt_updates += 1
        elif new_marker not in prompt:
            # 尚未注入，追加
            prompt = f"{prompt}\n\n{new_marker}" if prompt else new_marker
            shot["seedance_prompt"] = prompt
            prompt_updates += 1

    preview_lines = [f"# 分镜预览 - {episode}", ""]
    for shot in shots:
        preview_lines.extend(
            [
                f"## {shot['shot_id']}",
                "",
                f"- 构图图：`{shot.get('storyboard_image_path', '（未生成）')}`",
                f"- 场景：{shot.get('scene_name', '')} / {shot.get('time_of_day', '')}",
                f"- 镜头：{str(shot.get('camera', '')).splitlines()[0] if shot.get('camera') else ''}",
                "",
            ]
        )

    preview_path = project_root / "projects" / project / "outputs" / episode / "storyboard-preview.md"
    preview_path.write_text("\n".join(preview_lines), encoding="utf-8")
    return generated, prompt_updates


def extract_previous_end_frame(
    project_root: Path,
    project: str,
    episode: str,
    shot_index: int,
) -> str | None:
    if shot_index <= 1:
        return None
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None

    prev_num = shot_index - 1
    video_path = project_root / "projects" / project / "outputs" / episode / "videos" / f"shot-{prev_num:02d}.mp4"
    if not video_path.exists():
        return None

    output = project_root / "projects" / project / "outputs" / episode / "storyboard" / f"{episode}-shot-{prev_num:02d}-end-frame.png"
    if not output.exists():
        cmd = [
            ffmpeg,
            "-loglevel",
            "error",
            "-sseof",
            "-0.1",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-y",
            str(output),
        ]
        run(cmd, cwd=project_root, check=False)
    return relpath(project_root, output) if output.exists() else None


def compile_shot_packets(
    project_root: Path,
    project: str,
    episode: str,
    visual_data: dict[str, Any],
    world_model: dict[str, Any],
    view_index: dict | None = None,
) -> int:
    shots = visual_data.get("shots") or []
    shot_packets_dir = project_root / "projects" / project / "state" / "shot-packets"
    shot_packets_dir.mkdir(parents=True, exist_ok=True)

    entities = world_model.get("entities") or {}
    world_characters = entities.get("characters") or []
    world_locations = entities.get("locations") or []
    world_skills = entities.get("skills") or []

    char_by_name = {
        str(item.get("name")): item
        for item in world_characters
        if isinstance(item, dict) and item.get("name")
    }
    loc_by_name = {
        str(item.get("name")): item
        for item in world_locations
        if isinstance(item, dict) and item.get("name")
    }
    world_rules = collect_world_rules(world_model)

    count = 0
    total_shots = len(shots)

    # 预提取所有需要的 end-frame（避免重复 ffmpeg 进程）
    end_frames_cache: dict[int, str | None] = {}
    for shot in shots:
        si = int(shot["shot_index"])
        if si > 1 and si not in end_frames_cache:
            end_frames_cache[si] = extract_previous_end_frame(project_root, project, episode, si)

    for shot in shots:
        shot_id = str(shot["shot_id"])
        shot_index = int(shot["shot_index"])
        characters = []
        all_images: list[str] = []
        character_constraints: dict[str, Any] = {}
        forbidden_changes: list[str] = []

        references = shot.get("references") or {}
        for ref in references.get("characters") or []:
            name = str(ref.get("name"))
            variant_id = str(ref.get("variant_id") or "default")
            image_path = ref.get("image_path")
            world_char = char_by_name.get(name)
            variant_record = character_variant_record(world_char, variant_id)
            char_id = canonical_character_id(name, world_char)
            ref_assets = expand_character_assets(project_root, image_path)
            all_images.extend(ref_assets)

            current_state = {
                "form": str(
                    variant_record.get("appearance")
                    or (world_char or {}).get("physical", {}).get("form")
                    or variant_id
                ),
                "costume": str(variant_record.get("costume") or "default"),
                "injury": str((world_char or {}).get("status", {}).get("injury") or "none"),
                "emotion": infer_emotion(shot),
                "props_in_possession": list((world_char or {}).get("status", {}).get("props", []) or []),
                "knowledge": list((world_char or {}).get("status", {}).get("knowledge", []) or []),
            }

            must_preserve = ["form", "size", "color", "costume"]
            visual_signature = (world_char or {}).get("visual_signature") or {}
            if visual_signature.get("must_preserve_across_shots"):
                must_preserve.extend(visual_signature["must_preserve_across_shots"])

            characters.append(
                {
                    "id": char_id,
                    "name": name,
                    "state_ref": f"{char_id}@{shot_id}",
                    "variant": variant_id,
                    "ref_assets": dedupe_keep_order(ref_assets),
                    "must_preserve": dedupe_keep_order(must_preserve),
                    "current_state": current_state,
                }
            )
            character_constraints[char_id] = {
                "abilities": list((world_char or {}).get("abilities", []) or []),
                "constraints": list((world_char or {}).get("constraints", []) or []),
                "camera_preference": (world_char or {}).get("camera_preference", {}),
            }
            forbidden_changes.extend(infer_forbidden_changes(name, variant_id, world_char))

        scene_refs = []
        for ref in references.get("scenes") or []:
            image_path = ref.get("image_path")
            if image_path and (project_root / image_path).exists():
                scene_refs.append(str(image_path))
                all_images.append(str(image_path))

        storyboard_path = shot.get("storyboard_image_path")
        if storyboard_path and (project_root / storyboard_path).exists():
            all_images.append(str(storyboard_path))

        prev_frame = end_frames_cache.get(shot_index)
        if prev_frame:
            all_images.append(prev_frame)

        scene_name = str(shot.get("scene_name") or "")
        scene_model = loc_by_name.get(scene_name)
        scene_goal = str(shot.get("scene_goal") or first_nonempty_line(str(shot.get("action") or ""), "推进剧情"))
        prompt = str(shot.get("seedance_prompt") or "")
        generation_mode = str(shot.get("generation_mode") or "text2video")
        audio_lines = [line.strip() for line in str(shot.get("audio") or "").splitlines() if line.strip()]
        dramatic_role = infer_dramatic_role(shot, shot_index, total_shots)
        shot_purpose = infer_shot_purpose(shot, dramatic_role)
        transition_from_previous = infer_transition_from_previous(shot, shot_index)
        emotional_target = infer_emotional_target_text(shot)
        information_delta = infer_information_delta(shot)
        next_hook = infer_next_hook(shot, shot_index, total_shots)

        matching_skills = []
        if world_skills:
            for skill in world_skills:
                owner = str(skill.get("owner") or "")
                if any(owner == char["id"] for char in characters):
                    matching_skills.append(skill)

        packet = {
            "shot_id": shot_id,
            "episode": episode,
            "scene_id": str(scene_model.get("id") if scene_model else f"{episode}-sc{shot_index:02d}"),
            "shot_number": shot_index,
            "scene_goal": scene_goal,
            "duration_sec": int(shot.get("duration") or 0),
            "dialogue_mode": "external_dub" if shot.get("has_dialogue") else "none",
            "source_refs": {
                "visual_direction_path": str(project_root / "projects" / project / "outputs" / episode / "visual-direction.yaml"),
                "world_model_path": str(project_root / "projects" / project / "state" / "ontology" / f"{episode}-world-model.json"),
                "storyboard_image_path": shot.get("storyboard_image_path"),
            },
            "story_logic": {
                "shot_purpose": shot_purpose,
                "dramatic_role": dramatic_role,
                "transition_from_previous": transition_from_previous,
                "emotional_target": emotional_target,
                "information_delta": information_delta,
                "next_hook": next_hook,
            },
            "selected_views": build_selected_views(project_root, shot, view_index or {}),
            "continuity_inputs": {
                "previous_shot_id": shots[shot_index - 2]["shot_id"] if shot_index > 1 else None,
                "previous_end_frame_path": end_frames_cache.get(shot_index),
            },
            "characters": characters,
            "background": {
                "location": scene_name,
                "time_of_day": str(shot.get("time_of_day") or ""),
                "ref_assets": dedupe_keep_order(scene_refs),
                "lighting_note": str(shot.get("lighting_note") or ""),
                "functional": (scene_model or {}).get("functional", {}),
            },
            "camera": parse_camera_block(str(shot.get("camera") or "")),
            "seedance_inputs": {
                "mode": generation_mode,
                "images": dedupe_keep_order(all_images) if generation_mode == "img2video" else [],
                "videos": [],
                "audios": [],
                "prompt": prompt,
            },
            "forbidden_changes": dedupe_keep_order(forbidden_changes),
            "repair_policy": {
                "max_retries": 2,
                "prefer_local_edit": True,
            },
            "ontology_constraints": {
                "world_rules": world_rules,
                "character_abilities": character_constraints,
                "scene_restrictions": {
                    skill.get("id", ""): skill.get("scene_restrictions", [])
                    for skill in matching_skills
                    if skill.get("scene_restrictions")
                },
                "skills": matching_skills,
                "emotional_arcs": [
                    item
                    for item in (world_model.get("narrative_constraints") or {}).get("emotional_arcs", []) or []
                    if item.get("episode") == episode
                ],
            },
            "audio": audio_lines,
        }

        output = shot_packets_dir / f"{shot_id}.json"
        write_json(output, packet)
        count += 1

    return count


def archive_stale_shot_states(
    project_root: Path,
    project: str,
    episode: str,
    valid_shot_ids: set[str],
) -> list[str]:
    state_dir = project_root / "projects" / project / "state"
    archive_dir = state_dir / "archive" / episode
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived: list[str] = []

    for path in sorted(state_dir.glob(f"{episode}-shot-*.json")):
        if path.name.startswith(f"{episode}-shot-") is False:
            continue
        data = read_json(path)
        shot_id = str(data.get("shot_id") or path.stem)
        if shot_id not in valid_shot_ids:
            target = archive_dir / path.name
            shutil.move(str(path), str(target))
            archived.append(relpath(project_root, target))
    return archived


def sync_shot_states(
    project_root: Path,
    project: str,
    episode: str,
    visual_data: dict[str, Any],
) -> tuple[int, int]:
    shots = visual_data.get("shots") or []
    valid_shot_ids = {str(shot["shot_id"]) for shot in shots}
    archive_stale_shot_states(project_root, project, episode, valid_shot_ids)

    state_dir = project_root / "projects" / project / "state"
    videos_dir = project_root / "projects" / project / "outputs" / episode / "videos"

    completed = 0
    total = len(shots)
    for shot in shots:
        shot_index = int(shot["shot_index"])
        shot_id = str(shot["shot_id"])
        state_path = state_dir / f"{episode}-shot-{shot_index:02d}.json"
        video_path = videos_dir / f"shot-{shot_index:02d}.mp4"
        existing = read_json(state_path) if state_path.exists() else {}

        if video_path.exists():
            status = "completed"
            completed += 1
            completed_at = existing.get("completed_at") or utc_now()
        else:
            status = existing.get("status") or "pending"
            completed_at = existing.get("completed_at")

        payload = {
            "episode": episode,
            "shot_id": shot_id,
            "shot_index": shot_index,
            "status": status,
            "backend": existing.get("backend") or "unknown",
            "started_at": existing.get("started_at") or utc_now(),
            "completed_at": completed_at,
            "video_path": relpath(project_root, video_path) if video_path.exists() else "",
        }
        if existing.get("submit_id"):
            payload["submit_id"] = existing["submit_id"]
        write_json(state_path, payload)

    return completed, total


def upsert_phase_file(
    project_root: Path,
    project: str,
    episode: str,
    phase_name: str,
    phase_value: int | float,
    status: str,
    data: dict[str, Any],
) -> None:
    phase_path = project_root / "projects" / project / "state" / f"{episode}-phase{phase_name}.json"
    existing = read_json(phase_path) if phase_path.exists() else {}
    payload = {
        "episode": episode,
        "phase": phase_value,
        "status": status,
        "started_at": existing.get("started_at") or utc_now(),
        "completed_at": utc_now() if status == "completed" else existing.get("completed_at"),
        "data": data,
    }
    write_json(phase_path, payload)


def sync_phase_files(
    project_root: Path,
    project: str,
    episode: str,
    visual_data: dict[str, Any],
    shot_packets_count: int,
    completed_shots: int,
    total_shots: int,
) -> None:
    outputs_dir = project_root / "projects" / project / "outputs" / episode
    state_dir = project_root / "projects" / project / "state"
    shots = visual_data.get("shots") or []
    ui_paths = human_facing_paths(project_root, project, episode)

    phase2_path = state_dir / f"{episode}-phase2.json"
    if phase2_path.exists():
        phase2 = read_json(phase2_path)
        if phase2.get("status") == "awaiting_review":
            phase2["status"] = "completed"
            phase2["completed_at"] = phase2.get("completed_at") or utc_now()
            phase2.setdefault("data", {})
            phase2["data"]["shot_count"] = len(shots)
            phase2["data"]["total_duration"] = visual_data.get("total_duration", 0)
            write_json(phase2_path, phase2)

    storyboard_ready = all(
        shot.get("storyboard_image_path")
        and (project_root / str(shot["storyboard_image_path"])).exists()
        for shot in shots
    )
    upsert_phase_file(
        project_root,
        project,
        episode,
        "2.3",
        2.3,
        "completed" if storyboard_ready else "pending",
        {
            "storyboard_count": len(shots) if storyboard_ready else 0,
            "preview_file": f"projects/{project}/outputs/{episode}/storyboard-preview.md",
            "review_preview_file": ui_paths["review_preview"],
        },
    )

    if (outputs_dir / "art-direction-review.md").exists():
        upsert_phase_file(
            project_root,
            project,
            episode,
            "3",
            3,
            "completed",
            {
                "character_refs": sum(len((shot.get("references") or {}).get("characters") or []) for shot in shots),
                "scene_refs": sum(len((shot.get("references") or {}).get("scenes") or []) for shot in shots),
                "missing": 0,
            },
        )

    upsert_phase_file(
        project_root,
        project,
        episode,
        "3.5",
        3.5,
        "completed" if shot_packets_count == len(shots) else "pending",
        {
            "shot_packets_generated": shot_packets_count,
            "state_snapshot_indexed": shot_packets_count,
        },
    )

    if (outputs_dir / "voice-assignment.md").exists():
        voice_dir = project_root / "projects" / project / "assets" / "characters" / "voices"
        voice_count = len(list(voice_dir.glob("*/voice-config.yaml"))) if voice_dir.exists() else 0
        upsert_phase_file(
            project_root,
            project,
            episode,
            "4",
            4,
            "completed",
            {"voice_count": voice_count},
        )

    phase5_status = "completed" if completed_shots == total_shots else "in_progress"
    total_size_mb = 0.0
    videos_dir = outputs_dir / "videos"
    for shot in shots:
        video_path = videos_dir / f"shot-{int(shot['shot_index']):02d}.mp4"
        if video_path.exists():
            total_size_mb += video_path.stat().st_size / (1024 * 1024)

    upsert_phase_file(
        project_root,
        project,
        episode,
        "5",
        5,
        phase5_status,
        {
            "total_shots": total_shots,
            "completed": completed_shots,
            "failed": total_shots - completed_shots,
            "backend": (read_json(state_dir / f"{episode}-phase5.json").get("data", {}).get("backend", "unknown")
                        if (state_dir / f"{episode}-phase5.json").exists() else "unknown"),
            "total_size_mb": round(total_size_mb, 2),
            "deliverables_manifest": ui_paths["deliverables_manifest"],
            "deliverables_final_video": ui_paths["deliverables_final_video"],
            "deliverables_shots_dir": ui_paths["deliverables_shots_dir"],
            "review_dir": ui_paths["review_dir"],
        },
    )

    audit_dir = state_dir / "audit"
    audit_count = len(list(audit_dir.glob(f"{episode}-shot-*-audit.json"))) if audit_dir.exists() else 0
    phase6_status = "completed" if audit_count == total_shots and total_shots > 0 else "pending"
    upsert_phase_file(
        project_root,
        project,
        episode,
        "6",
        6,
        phase6_status,
        {
            "audited_shots": audit_count,
            "total_shots": total_shots,
        },
    )


def write_generation_report(
    project_root: Path,
    project: str,
    episode: str,
    visual_data: dict[str, Any],
) -> None:
    state_dir = project_root / "projects" / project / "state"
    outputs_dir = project_root / "projects" / project / "outputs" / episode
    deliverables_dir = outputs_dir / "deliverables"
    final_video = deliverables_dir / "final.mp4"
    manifest_path = deliverables_dir / "manifest.json"
    review_dir = outputs_dir / "review"
    lines = [f"# 视频生成报告 - {episode}", "", "## 总览", ""]

    shots = visual_data.get("shots") or []
    success = 0
    failed = 0
    for shot in shots:
        shot_index = int(shot["shot_index"])
        state_path = state_dir / f"{episode}-shot-{shot_index:02d}.json"
        state = read_json(state_path) if state_path.exists() else {}
        if state.get("status") == "completed":
            success += 1
        else:
            failed += 1

    lines.extend(
        [
            f"- 总镜次：{len(shots)}",
            f"- 成功：{success}",
            f"- 失败：{failed}",
            f"- 最终成片：{relpath(project_root, final_video) if final_video.exists() else '（尚未生成）'}",
            f"- 交付清单：{relpath(project_root, manifest_path) if manifest_path.exists() else '（尚未生成）'}",
            f"- 审阅入口：{relpath(project_root, review_dir) if review_dir.exists() else '（尚未生成）'}",
            f"- 生成时间：{utc_now()}",
            "",
            "## 明细",
            "",
            "| 镜次 | 状态 | 视频文件 |",
            "|------|------|----------|",
        ]
    )

    for shot in shots:
        shot_index = int(shot["shot_index"])
        state_path = state_dir / f"{episode}-shot-{shot_index:02d}.json"
        state = read_json(state_path) if state_path.exists() else {}
        video_path = state.get("video_path") or ""
        lines.append(f"| {shot['shot_id']} | {state.get('status', 'missing')} | {video_path} |")

    report_path = outputs_dir / "generation-report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def human_facing_paths(project_root: Path, project: str, episode: str) -> dict[str, str]:
    outputs_dir = project_root / "projects" / project / "outputs" / episode
    deliverables_dir = outputs_dir / "deliverables"
    return {
        "deliverables_dir": relpath(project_root, deliverables_dir),
        "deliverables_manifest": relpath(project_root, deliverables_dir / "manifest.json"),
        "deliverables_final_video": relpath(project_root, deliverables_dir / "final.mp4"),
        "deliverables_shots_dir": relpath(project_root, deliverables_dir / "shots"),
        "review_dir": relpath(project_root, outputs_dir / "review"),
        "review_preview": relpath(project_root, outputs_dir / "review" / "storyboard-preview.md"),
        "build_raw_videos_dir": relpath(project_root, outputs_dir / "build" / "raw-videos"),
    }


def mirror_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            if (
                target.stat().st_size == source.stat().st_size
                and int(target.stat().st_mtime) == int(source.stat().st_mtime)
            ):
                return
        except FileNotFoundError:
            pass
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def choose_latest_final_video(outputs_dir: Path, episode: str) -> Path | None:
    candidates = [path for path in outputs_dir.glob(f"{episode}-final*.mp4") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def sync_human_facing_outputs(
    project_root: Path,
    project: str,
    episode: str,
    visual_data: dict[str, Any],
) -> None:
    outputs_dir = project_root / "projects" / project / "outputs" / episode
    videos_dir = outputs_dir / "videos"
    deliverables_dir = outputs_dir / "deliverables"
    deliverables_shots_dir = deliverables_dir / "shots"
    build_raw_videos_dir = outputs_dir / "build" / "raw-videos"
    review_dir = outputs_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)

    raw_video_pattern = re.compile(r"[0-9a-f]{16}\.mp4$", re.IGNORECASE)
    raw_video_paths: list[str] = []
    if videos_dir.exists():
        for candidate in sorted(videos_dir.glob("*.mp4")):
            if raw_video_pattern.fullmatch(candidate.name):
                target = build_raw_videos_dir / candidate.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target.unlink()
                shutil.move(str(candidate), str(target))

    if build_raw_videos_dir.exists():
        raw_video_paths = [
            relpath(project_root, path)
            for path in sorted(build_raw_videos_dir.glob("*.mp4"))
            if path.is_file()
        ]

    shots = visual_data.get("shots") or []
    keep_shot_names: set[str] = set()
    deliverable_shots: list[str] = []
    for shot in shots:
        shot_index = int(shot["shot_index"])
        shot_name = f"shot-{shot_index:02d}.mp4"
        source = videos_dir / shot_name
        if not source.exists():
            continue
        target = deliverables_shots_dir / shot_name
        mirror_file(source, target)
        keep_shot_names.add(shot_name)
        deliverable_shots.append(relpath(project_root, target))

    if deliverables_shots_dir.exists():
        for stale in deliverables_shots_dir.glob("shot-*.mp4"):
            if stale.name not in keep_shot_names:
                stale.unlink()

    final_video_rel: str | None = None
    latest_final = choose_latest_final_video(outputs_dir, episode)
    final_target = deliverables_dir / "final.mp4"
    if latest_final is not None:
        mirror_file(latest_final, final_target)
        final_video_rel = relpath(project_root, final_target)
    elif final_target.exists():
        final_video_rel = relpath(project_root, final_target)

    preview_source = outputs_dir / "storyboard-preview.md"
    review_preview_rel: str | None = None
    if preview_source.exists():
        review_preview = review_dir / "storyboard-preview.md"
        mirror_file(preview_source, review_preview)
        review_preview_rel = relpath(project_root, review_preview)

    review_readme = review_dir / "README.md"
    review_lines = [
        f"# Review Bundle - {episode}",
        "",
        f"- Storyboard preview: `{review_preview_rel or '（未生成）'}`",
        f"- Storyboard images: `projects/{project}/outputs/{episode}/storyboard/`",
        "",
        "此目录是给人查看的入口；流水线内部文件仍保留在原始目录。",
    ]
    review_readme.write_text("\n".join(review_lines) + "\n", encoding="utf-8")

    manifest = {
        "project": project,
        "episode": episode,
        "shot_count": len(shots),
        "completed_shots": len(deliverable_shots),
        "shots": deliverable_shots,
        "final_video": final_video_rel,
        "raw_videos": raw_video_paths,
        "review_preview": review_preview_rel,
        "updated_at": utc_now(),
    }
    write_json(deliverables_dir / "manifest.json", manifest)

    summary_lines = [
        f"# Deliverables - {episode}",
        "",
        f"- Final video: `{final_video_rel or '（尚未拼接）'}`",
        f"- Shot videos: `{relpath(project_root, deliverables_shots_dir)}`",
        f"- Review bundle: `projects/{project}/outputs/{episode}/review/`",
        f"- Raw downloads: `projects/{project}/outputs/{episode}/build/raw-videos/`",
    ]
    (deliverables_dir / "README.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def sync_vectordb(project_root: Path, project: str, episode: str) -> None:
    python_bin = repo_python(project_root)
    world_model = project_root / "projects" / project / "state" / "ontology" / f"{episode}-world-model.json"
    assets_root = project_root / "projects" / project / "assets"
    shot_packets_dir = project_root / "projects" / project / "state" / "shot-packets"

    run([python_bin, "scripts/vectordb-manager.py", "--project", project, "init"], cwd=project_root)
    if world_model.exists():
        run([python_bin, "scripts/vectordb-manager.py", "--project", project, "upsert-world-model", relpath(project_root, world_model)], cwd=project_root)
    if assets_root.exists():
        run([python_bin, "scripts/vectordb-manager.py", "--project", project, "index-assets", relpath(project_root, assets_root)], cwd=project_root)
    for packet in sorted(shot_packets_dir.glob(f"{episode}-shot-*.json")):
        run([python_bin, "scripts/vectordb-manager.py", "--project", project, "upsert-state", relpath(project_root, packet)], cwd=project_root)


# ──────────────────────────────────────────────
# Task 1+2+3+5: shot-state / asset-view-index / packet enrichment / recovery
# ──────────────────────────────────────────────

def parse_camera_angle(camera_text: str) -> str:
    line = (camera_text or "").splitlines()[0].lower()
    if any(t in line for t in ("主观", "第一人称", "pov")):
        return "subjective"
    if any(t in line for t in ("仰拍", "仰视", "低角度")):
        return "low"
    if any(t in line for t in ("俯拍", "俯视", "高角度", "鸟瞰")):
        return "high"
    return "normal"


def build_selected_views(
    project_root: Path,
    shot: dict[str, Any],
    view_index: dict,
) -> dict[str, Any]:
    """从 asset-view-index 为本镜选择最合适的角色/场景参考图。"""
    selected: dict[str, Any] = {"characters": [], "scene": {}}

    references = shot.get("references") or {}
    for ref in references.get("characters") or []:
        name = str(ref.get("name") or "")
        variant_id = str(ref.get("variant_id") or "default")
        if _ASSET_VIEW_INDEX_AVAILABLE:
            selected_path, actual_view = select_character_view(view_index, name, variant_id, "front")
        else:
            image_path = ref.get("image_path")
            selected_path = str(image_path) if image_path and (project_root / str(image_path)).exists() else None
            actual_view = "front"
        selected["characters"].append({
            "id": re.sub(r"[^a-z0-9]+", "_", name.lower()) or name,
            "name": name,
            "variant_id": variant_id,
            "preferred_view": actual_view or "front",
            "selected_path": selected_path or str(ref.get("image_path") or ""),
            "fallback_order": ["front", "side", "back"],
        })

    for ref in references.get("scenes") or []:
        scene_name = str(ref.get("name") or "")
        time_of_day = str(shot.get("time_of_day") or ref.get("time_of_day") or "day")
        if _ASSET_VIEW_INDEX_AVAILABLE:
            selected_path = select_scene_view(view_index, scene_name, time_of_day)
        else:
            image_path = ref.get("image_path")
            selected_path = str(image_path) if image_path and (project_root / str(image_path)).exists() else None
        selected["scene"] = {
            "name": scene_name,
            "preferred_view": time_of_day,
            "selected_path": selected_path or str(ref.get("image_path") or ""),
        }
        break  # 每镜只取第一个场景

    return selected


def build_shot_state(
    episode: str,
    shot: dict[str, Any],
    visual_direction_path: Path,
    world_model_path: Path,
    selected_views: dict[str, Any],
    previous_shot_id: str | None,
    previous_end_frame_path: str | None,
    total_shots: int,
) -> dict[str, Any]:
    shot_index = int(shot["shot_index"])
    camera_text = str(shot.get("camera") or "")
    camera_parsed = parse_camera_block(camera_text)

    return {
        "shot_id": str(shot["shot_id"]),
        "episode": episode,
        "scene_id": str(shot.get("scene_name") or f"{episode}-sc{shot_index:02d}"),
        "source_refs": {
            "visual_direction_path": str(visual_direction_path),
            "world_model_path": str(world_model_path),
            "storyboard_image_path": shot.get("storyboard_image_path"),
        },
        "story_logic": {
            "shot_purpose": infer_shot_purpose(shot, infer_dramatic_role(shot, shot_index, total_shots)),
            "dramatic_role": infer_dramatic_role(shot, shot_index, total_shots),
            "transition_from_previous": infer_transition_from_previous(shot, shot_index),
            "emotional_target": infer_emotional_target_text(shot),
            "information_delta": infer_information_delta(shot),
            "next_hook": infer_next_hook(shot, shot_index, total_shots),
        },
        "camera": {
            "raw": camera_text.strip(),
            "shot_size": camera_parsed["shot_size"],
            "movement": camera_parsed["movement"],
            "angle": parse_camera_angle(camera_text),
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


def recover_stale_shot_states(
    project_root: Path,
    project: str,
    episode: str,
    valid_shot_ids: set[str],
) -> None:
    """扫描 state/shot-state/ 中已有的 JSON，若对应视频存在则标记为 recovered。"""
    shot_state_dir = project_root / "projects" / project / "state" / "shot-state"
    if not shot_state_dir.exists():
        return
    videos_dir = project_root / "projects" / project / "outputs" / episode / "videos"

    for path in sorted(shot_state_dir.glob(f"{episode}-shot-*.json")):
        try:
            data = read_json(path)
        except Exception:
            continue
        shot_id = str(data.get("shot_id") or path.stem)
        if shot_id in valid_shot_ids:
            continue  # 会被正常重写，跳过
        # 孤立的 stale shot-state：检查视频是否存在
        shot_index_match = re.search(r"-shot-(\d+)$", path.stem)
        if not shot_index_match:
            continue
        shot_index = int(shot_index_match.group(1))
        video_path = videos_dir / f"shot-{shot_index:02d}.mp4"
        if video_path.exists():
            data.setdefault("generation_status", {})["video"] = "recovered"
            data.setdefault("continuity", {})["recovered_from_outputs"] = True
            write_json(path, data)


def emit_shot_states(
    project_root: Path,
    project: str,
    episode: str,
    visual_data: dict[str, Any],
    visual_path: Path,
    world_model_path: Path,
    view_index: dict,
) -> None:
    shots = visual_data.get("shots") or []
    shot_state_dir = project_root / "projects" / project / "state" / "shot-state"
    shot_state_dir.mkdir(parents=True, exist_ok=True)
    total_shots = len(shots)
    valid_shot_ids = {str(s["shot_id"]) for s in shots}

    # 先处理 stale（孤立的旧 shot-state）
    recover_stale_shot_states(project_root, project, episode, valid_shot_ids)

    # 预提取所有需要的 end-frame（避免重复 ffmpeg 进程）
    end_frames_cache: dict[int, str | None] = {}
    for shot in shots:
        si = int(shot["shot_index"])
        if si > 1 and si not in end_frames_cache:
            end_frames_cache[si] = extract_previous_end_frame(project_root, project, episode, si)

    previous_shot_id: str | None = None
    for shot in shots:
        shot_index = int(shot["shot_index"])
        shot_id = str(shot["shot_id"])
        prev_frame = end_frames_cache.get(shot_index)
        selected_views = build_selected_views(project_root, shot, view_index)
        state = build_shot_state(
            episode, shot, visual_path, world_model_path,
            selected_views, previous_shot_id, prev_frame, total_shots,
        )
        write_json(shot_state_dir / f"{shot_id}.json", state)
        previous_shot_id = shot_id


def emit_asset_view_index(
    project_root: Path,
    project: str,
    episode: str,
    view_index: dict,
) -> None:
    asset_views_dir = project_root / "projects" / project / "state" / "asset-views"
    asset_views_dir.mkdir(parents=True, exist_ok=True)
    write_json(asset_views_dir / f"{episode}-view-index.json", view_index)


def resolve_episodes(project_root: Path, project: str, episode: str | None, all_output_episodes: bool) -> list[str]:
    if episode:
        return [episode]
    if not all_output_episodes:
        raise SystemExit("请提供 --episode 或使用 --all-output-episodes")

    outputs_root = project_root / "projects" / project / "outputs"
    episodes = sorted(path.name for path in outputs_root.iterdir() if path.is_dir())
    if not episodes:
        raise SystemExit(f"未找到 outputs 集数目录: {outputs_root}")
    return episodes


def process_episode(project_root: Path, project: str, episode: str, do_vectordb: bool) -> None:
    visual_path = project_root / "projects" / project / "outputs" / episode / "visual-direction.yaml"
    world_model_path = project_root / "projects" / project / "state" / "ontology" / f"{episode}-world-model.json"

    if not visual_path.exists():
        raise FileNotFoundError(f"visual-direction.yaml 不存在: {visual_path}")
    if not world_model_path.exists():
        raise FileNotFoundError(f"world-model.json 不存在: {world_model_path}")

    visual_data = read_yaml(visual_path)
    world_model = read_json(world_model_path)

    # Build asset view index (Task 2)
    if _ASSET_VIEW_INDEX_AVAILABLE:
        view_index = build_asset_view_index(project_root, project)
    else:
        view_index = {"characters": {}, "scenes": {}, "props": {}}
    emit_asset_view_index(project_root, project, episode, view_index)

    generated_storyboards, updated_prompts = ensure_storyboards(project_root, project, episode, visual_data)
    write_yaml(visual_path, visual_data)

    # Emit shot-state intermediate artifacts (Task 1 + 5)
    emit_shot_states(project_root, project, episode, visual_data, visual_path, world_model_path, view_index)

    shot_packets_count = compile_shot_packets(project_root, project, episode, visual_data, world_model, view_index)
    completed_shots, total_shots = sync_shot_states(project_root, project, episode, visual_data)
    sync_human_facing_outputs(project_root, project, episode, visual_data)
    sync_phase_files(project_root, project, episode, visual_data, shot_packets_count, completed_shots, total_shots)
    write_generation_report(project_root, project, episode, visual_data)

    if do_vectordb:
        sync_vectordb(project_root, project, episode)

    ui_paths = human_facing_paths(project_root, project, episode)

    print(
        json.dumps(
            {
                "project": project,
                "episode": episode,
                "storyboards_generated": generated_storyboards,
                "prompts_updated": updated_prompts,
                "shot_packets": shot_packets_count,
                "completed_shots": completed_shots,
                "total_shots": total_shots,
                "vectordb_synced": do_vectordb,
                **ui_paths,
            },
            ensure_ascii=False,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步工作流产物、状态和向量库")
    parser.add_argument("--project-root", default=".", help="仓库根目录")
    parser.add_argument("--project", required=True, help="projects/{project} 名称")
    parser.add_argument("--episode", help="集数，如 ep01")
    parser.add_argument("--all-output-episodes", action="store_true", help="同步 outputs/ 下所有已有集数")
    parser.add_argument("--sync-vectordb", action="store_true", help="同步 LanceDB（可能较慢）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    episodes = resolve_episodes(project_root, args.project, args.episode, args.all_output_episodes)

    for episode in episodes:
        process_episode(project_root, args.project, episode, args.sync_vectordb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
