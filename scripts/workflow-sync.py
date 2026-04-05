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
    marker = "构图参考@分镜图（仅参考景别和角色位置，不复制细节）"

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
        if marker not in prompt:
            prompt = f"{prompt}\n\n{marker}" if prompt else marker
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

        prev_frame = extract_previous_end_frame(project_root, project, episode, shot_index)
        if prev_frame:
            all_images.append(prev_frame)

        scene_name = str(shot.get("scene_name") or "")
        scene_model = loc_by_name.get(scene_name)
        scene_goal = str(shot.get("scene_goal") or first_nonempty_line(str(shot.get("action") or ""), "推进剧情"))
        prompt = str(shot.get("seedance_prompt") or "")
        generation_mode = str(shot.get("generation_mode") or "text2video")
        audio_lines = [line.strip() for line in str(shot.get("audio") or "").splitlines() if line.strip()]

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


def sync_vectordb(project_root: Path, project: str, episode: str) -> None:
    python_bin = repo_python(project_root)
    world_model = project_root / "projects" / project / "state" / "ontology" / f"{episode}-world-model.json"
    assets_root = project_root / "projects" / project / "assets"
    shot_packets_dir = project_root / "projects" / project / "state" / "shot-packets"

    run([python_bin, "scripts/vectordb-manager.py", "init"], cwd=project_root)
    if world_model.exists():
        run([python_bin, "scripts/vectordb-manager.py", "upsert-world-model", relpath(project_root, world_model)], cwd=project_root)
    if assets_root.exists():
        run([python_bin, "scripts/vectordb-manager.py", "index-assets", relpath(project_root, assets_root)], cwd=project_root)
    for packet in sorted(shot_packets_dir.glob(f"{episode}-shot-*.json")):
        run([python_bin, "scripts/vectordb-manager.py", "upsert-state", relpath(project_root, packet)], cwd=project_root)


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

    generated_storyboards, updated_prompts = ensure_storyboards(project_root, project, episode, visual_data)
    write_yaml(visual_path, visual_data)

    shot_packets_count = compile_shot_packets(project_root, project, episode, visual_data, world_model)
    completed_shots, total_shots = sync_shot_states(project_root, project, episode, visual_data)
    sync_phase_files(project_root, project, episode, visual_data, shot_packets_count, completed_shots, total_shots)
    write_generation_report(project_root, project, episode, visual_data)

    if do_vectordb:
        sync_vectordb(project_root, project, episode)

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
