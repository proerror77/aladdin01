#!/usr/bin/env python3
"""Local Studio UI server.

Serves the static console, repository data, and a guarded local action API
without extra dependencies. Actions run only through the explicit registry.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = Path(__file__).resolve().parent
PROJECTS_ROOT = REPO_ROOT / "projects"

EPISODE_RE = re.compile(r"ep\d+", re.IGNORECASE)
SHOT_RE = re.compile(r"(?:ep\d+-)?shot[-_]?(\d+)", re.IGNORECASE)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

UI_STATE_ROOT = REPO_ROOT / "state" / "ui-actions"
JOBS_ROOT = UI_STATE_ROOT / "jobs"
REQUESTS_ROOT = UI_STATE_ROOT / "requests"
MAX_LOG_TAIL = 16000

ACTION_REGISTRY = {
    "env_check": {
        "id": "env_check",
        "label": "环境检查",
        "description": "检查生成链路需要的本地环境变量，不调用外部模型。",
        "scope": "repo",
        "risk": "read",
        "mutates": False,
        "requires_confirmation": False,
        "button": "运行检查",
    },
    "workflow_sync": {
        "id": "workflow_sync",
        "label": "同步项目状态",
        "description": "运行 workflow-sync，修复/同步分镜、shot packet、phase 和产物状态。",
        "scope": "project",
        "risk": "write",
        "mutates": True,
        "requires_confirmation": True,
        "button": "确认同步",
    },
    "request_resume": {
        "id": "request_resume",
        "label": "提交继续生成请求",
        "description": "写入 Agent 继续请求；若配置了 Remote Trigger，会尝试触发远端 Agent。",
        "scope": "project",
        "risk": "agent",
        "mutates": True,
        "requires_confirmation": True,
        "button": "提交请求",
    },
    "trace_summary": {
        "id": "trace_summary",
        "label": "生成 Trace 摘要",
        "description": "对最新 trace session 生成摘要。需要 DEEPSEEK_API_KEY 或 TUZI_API_KEY。",
        "scope": "repo",
        "risk": "external",
        "mutates": True,
        "requires_confirmation": True,
        "button": "生成摘要",
    },
}


def json_response(handler: SimpleHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def read_request_json(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def error_response(handler: SimpleHTTPRequestHandler, status: HTTPStatus, message: str) -> None:
    json_response(handler, {"error": message}, status.value)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def text_sample(path: Path, limit: int = 2400) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n..."


def simple_yaml(path: Path) -> dict:
    """Parse the flat top-level fields used by Aladdin profile YAML files."""
    data: dict[str, object] = {}
    current_key = ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return data

    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith((" ", "\t")) and ":" in raw_line:
            key, value = raw_line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            if value:
                if value == "[]":
                    data[current_key] = []
                else:
                    data[current_key] = value.strip("\"'")
            else:
                data[current_key] = []
            continue
        if raw_line.lstrip().startswith("- ") and isinstance(data.get(current_key), list):
            data[current_key].append(raw_line.lstrip()[2:].strip().strip("\"'"))
    return data


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def repo_python() -> str:
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def media_url(path: Path | None) -> str:
    if not path:
        return ""
    return f"/media/{rel(path)}"


def safe_repo_path(relative_path: str) -> Path | None:
    candidate = (REPO_ROOT / relative_path).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError:
        return None
    return candidate


def latest_mtime(paths: list[Path]) -> float:
    mtimes = []
    for path in paths:
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            pass
    return max(mtimes) if mtimes else 0.0


def iso_from_mtime(mtime: float) -> str:
    if not mtime:
        return ""
    return datetime.fromtimestamp(mtime, timezone.utc).isoformat()


def project_dirs() -> list[Path]:
    if not PROJECTS_ROOT.exists():
        return []
    return sorted([path for path in PROJECTS_ROOT.iterdir() if path.is_dir()], key=lambda p: p.name)


def count_files(root: Path, patterns: tuple[str, ...]) -> int:
    if not root.exists():
        return 0
    total = 0
    for pattern in patterns:
        total += len([path for path in root.rglob(pattern) if path.is_file() and not path.name.startswith(".")])
    return total


def project_files(project_dir: Path) -> list[Path]:
    files: list[Path] = []
    for child in ("script", "assets", "outputs", "state"):
        root = project_dir / child
        if root.exists():
            files.extend([path for path in root.rglob("*") if path.is_file() and not path.name.startswith(".")])
    return files


def episode_sort_key(path: Path) -> tuple[int, str]:
    match = EPISODE_RE.search(path.name)
    if not match:
        return (999, path.name)
    return (int(match.group()[2:]), path.name)


def first_heading(path: Path) -> str:
    for line in text_sample(path, 1200).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return path.stem


def matching_image(image_dir: Path, profile_name: str) -> Path | None:
    if not image_dir.exists():
        return None
    images = sorted(
        [path for path in image_dir.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    )
    for image in images:
        if profile_name and profile_name in image.stem:
            return image
    return images[0] if images else None


def summarize_profile(path: Path, image_dir: Path, fallback_code: str) -> dict:
    data = simple_yaml(path)
    name = str(data.get("name") or path.stem)
    image = matching_image(image_dir, name)
    return {
        "code": fallback_code,
        "name": name,
        "path": rel(path),
        "image_url": media_url(image),
        "tier": data.get("tier", ""),
        "gender": data.get("gender", ""),
        "age": data.get("age", ""),
        "appearance": data.get("appearance") or data.get("description") or "",
        "personality": data.get("personality") or data.get("atmosphere") or "",
        "aliases": data.get("aliases", []),
        "first_episode": data.get("first_episode", ""),
        "raw": data,
    }


def collect_scripts(project_dir: Path) -> list[dict]:
    scripts = []
    for path in sorted((project_dir / "script").glob("*.md"), key=episode_sort_key):
        scripts.append({
            "episode": EPISODE_RE.search(path.name).group(0) if EPISODE_RE.search(path.name) else path.stem,
            "title": first_heading(path),
            "path": rel(path),
            "excerpt": text_sample(path, 2200),
            "updated_at": iso_from_mtime(path.stat().st_mtime),
        })
    return scripts


def collect_states(project_dir: Path) -> tuple[list[dict], list[dict]]:
    phases: list[dict] = []
    shots: list[dict] = []
    state_dir = project_dir / "state"
    if not state_dir.exists():
        return phases, shots
    for path in sorted(state_dir.glob("*.json")):
        data = read_json(path)
        if not data:
            continue
        entry = {
            "file": path.name,
            "path": rel(path),
            "episode": data.get("episode") or "",
            "status": data.get("status") or data.get("gen_status") or data.get("sm_state") or "",
            "updated_at": data.get("updated_at") or data.get("completed_at") or data.get("started_at") or iso_from_mtime(path.stat().st_mtime),
            "data": data,
        }
        if "shot" in path.stem or data.get("shot_id"):
            entry["shot_id"] = data.get("shot_id") or path.stem
            shots.append(entry)
        elif "phase" in path.stem or "phase" in data:
            entry["phase"] = data.get("phase") or path.stem
            phases.append(entry)
    return phases, shots


def collect_storyboards(project_dir: Path, shot_states: list[dict]) -> list[dict]:
    state_by_key = {}
    for state in shot_states:
        shot_id = str(state.get("shot_id") or "")
        file_stem = str(state.get("file") or "").replace(".json", "")
        for key in (shot_id, file_stem):
            if key:
                state_by_key[key.lower()] = state

    packet_by_key = {}
    packets_dir = project_dir / "state" / "shot-packets"
    if packets_dir.exists():
        for packet_path in sorted(packets_dir.glob("*.json")):
            data = read_json(packet_path)
            if not data:
                continue
            shot_id = str(data.get("shot_id") or packet_path.stem)
            episode = str(data.get("episode") or "")
            shot_number = data.get("shot_number")
            candidates = [shot_id, packet_path.stem]
            if episode and shot_number:
                candidates.extend([
                    f"{episode}-shot-{int(shot_number):02d}",
                    f"{episode}-shot-{int(shot_number)}",
                ])
            packet = {
                "path": rel(packet_path),
                "shot_id": shot_id,
                "duration_sec": data.get("duration_sec", ""),
                "dialogue_mode": data.get("dialogue_mode", ""),
                "story_logic": data.get("story_logic") or {},
                "characters": data.get("characters") or [],
                "background": data.get("background") or {},
                "camera": data.get("camera") or "",
                "seedance_mode": (data.get("seedance_inputs") or {}).get("mode", ""),
            }
            for key in candidates:
                if key:
                    packet_by_key[str(key).lower()] = packet

    shots = []
    outputs_dir = project_dir / "outputs"
    if not outputs_dir.exists():
        return shots
    for image in sorted(outputs_dir.glob("ep*/storyboard/*"), key=lambda p: (p.parent.parent.name, p.name)):
        if image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        episode = image.parent.parent.name
        shot_match = SHOT_RE.search(image.stem)
        shot_number = int(shot_match.group(1)) if shot_match else len(shots) + 1
        candidates = [
            f"{episode}-shot-{shot_number:02d}",
            f"{episode}-shot-{shot_number}",
            image.stem,
        ]
        state = next((state_by_key[key.lower()] for key in candidates if key.lower() in state_by_key), {})
        packet = next((packet_by_key[key.lower()] for key in candidates if key.lower() in packet_by_key), {})
        shots.append({
            "id": f"{episode}-shot-{shot_number:02d}",
            "episode": episode,
            "shot": shot_number,
            "title": f"{episode.upper()} · Shot {shot_number:02d}",
            "image_url": media_url(image),
            "path": rel(image),
            "status": state.get("status") or "storyboard",
            "updated_at": state.get("updated_at") or iso_from_mtime(image.stat().st_mtime),
            "packet": packet,
        })
    return shots


PHASE_LABELS = {
    "0": "本体论",
    "1": "合规预检",
    "2": "视觉指导",
    "2.2": "叙事审查",
    "2.3": "分镜图",
    "2.5": "资产工厂",
    "3": "美术校验",
    "3.5": "Shot Packet",
    "4": "音色配置",
    "5": "视频生成",
    "6": "QA / Repair",
}


def normalize_phase(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def collect_phase_matrix(project_dir: Path) -> list[dict]:
    state_dir = project_dir / "state"
    if not state_dir.exists():
        return []
    by_episode: dict[str, dict] = {}
    for path in sorted(state_dir.glob("*-phase*.json")):
        data = read_json(path)
        if not data:
            continue
        episode = str(data.get("episode") or path.stem.split("-phase")[0])
        phase = normalize_phase(data.get("phase") or path.stem.split("-phase", 1)[-1])
        if not episode or not phase:
            continue
        row = by_episode.setdefault(episode, {"episode": episode, "phases": {}})
        row["phases"][phase] = {
            "phase": phase,
            "label": PHASE_LABELS.get(phase, f"Phase {phase}"),
            "status": data.get("status") or data.get("decision") or "unknown",
            "decision": data.get("decision", ""),
            "score": data.get("total_score", ""),
            "path": rel(path),
            "updated_at": data.get("completed_at") or data.get("reviewed_at") or data.get("started_at") or iso_from_mtime(path.stat().st_mtime),
            "data": data.get("data") or {},
            "needs_human_review": data.get("needs_human_review") or [],
        }
    rows = []
    phase_order = ["0", "1", "2", "2.2", "2.3", "2.5", "3", "3.5", "4", "5", "6"]
    for episode, row in sorted(by_episode.items(), key=lambda item: episode_sort_key(Path(item[0]))):
        phases = row["phases"]
        row["ordered"] = [
            phases.get(phase) or {
                "phase": phase,
                "label": PHASE_LABELS.get(phase, f"Phase {phase}"),
                "status": "missing",
                "path": "",
                "updated_at": "",
                "data": {},
                "needs_human_review": [],
            }
            for phase in phase_order
        ]
        rows.append(row)
    return rows


def collect_ontology(project_dir: Path) -> dict:
    ontology_dir = project_dir / "state" / "ontology"
    if not ontology_dir.exists():
        return {"episodes": [], "entities": {"characters": [], "locations": [], "props": []}, "relationships": [], "rules": []}

    episodes = []
    characters: dict[str, dict] = {}
    locations: dict[str, dict] = {}
    props: dict[str, dict] = {}
    relationships = []
    rules: list[str] = []
    for path in sorted(ontology_dir.glob("*-world-model.json"), key=episode_sort_key):
        data = read_json(path)
        if not data:
            continue
        episode = data.get("episode") or path.stem.split("-")[0]
        entities = data.get("entities") or {}
        for item in entities.get("characters") or []:
            name = str(item.get("name") or item.get("id") or "")
            if name:
                current = characters.setdefault(name, {**item, "episodes": []})
                current["episodes"].append(episode)
        for item in entities.get("locations") or []:
            name = str(item.get("name") or item.get("id") or "")
            if name:
                current = locations.setdefault(name, {**item, "episodes": []})
                current["episodes"].append(episode)
        for item in entities.get("props") or []:
            name = str(item.get("name") or item.get("id") or "")
            if name:
                current = props.setdefault(name, {**item, "episodes": []})
                current["episodes"].append(episode)
        for relation in data.get("relationships") or []:
            relationships.append({**relation, "episode": episode})
        narrative = data.get("narrative_constraints") or {}
        rules.extend([str(item) for item in narrative.get("world_rules") or []])
        physics_notes = (data.get("physics_rules") or {}).get("notes")
        if physics_notes:
            rules.append(str(physics_notes))
        episodes.append({
            "episode": episode,
            "path": rel(path),
            "characters": len(entities.get("characters") or []),
            "locations": len(entities.get("locations") or []),
            "props": len(entities.get("props") or []),
            "relationships": len(data.get("relationships") or []),
        })

    return {
        "episodes": episodes,
        "entities": {
            "characters": list(characters.values()),
            "locations": list(locations.values()),
            "props": list(props.values()),
        },
        "relationships": relationships,
        "rules": list(dict.fromkeys(rules))[:24],
    }


def split_asset_name(path: Path) -> tuple[str, str, str]:
    stem = path.stem
    parts = stem.split("-")
    if len(parts) >= 3 and parts[-1] in {"front", "side", "back"}:
        return "-".join(parts[:-2]), parts[-2], parts[-1]
    if len(parts) >= 2 and parts[-1] in {"front", "side", "back", "interface"}:
        return "-".join(parts[:-1]), "default", parts[-1]
    if len(parts) >= 2 and parts[-1] in {"day", "night", "dusk", "dawn"}:
        return "-".join(parts[:-1]), parts[-1], "styleframe"
    return stem, "default", "asset"


def collect_asset_matrix(project_dir: Path) -> dict:
    matrix: dict[str, dict[str, dict]] = {"characters": {}, "scenes": {}, "props": {}}
    image_roots = [
        ("characters", project_dir / "assets" / "characters" / "images"),
        ("scenes", project_dir / "assets" / "scenes" / "images"),
        ("props", project_dir / "assets" / "props" / "images"),
    ]
    for asset_type, root in image_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            entity, variant, view = split_asset_name(path)
            entity_row = matrix[asset_type].setdefault(entity, {"entity": entity, "variants": {}})
            variant_row = entity_row["variants"].setdefault(variant, {"variant": variant, "views": {}})
            variant_row["views"][view] = {"path": rel(path), "url": media_url(path)}

    def flatten(section: dict) -> list[dict]:
        rows = []
        for entity, row in sorted(section.items()):
            variants = []
            for variant, variant_row in sorted(row["variants"].items()):
                variants.append({
                    "variant": variant,
                    "views": variant_row["views"],
                    "view_count": len(variant_row["views"]),
                })
            rows.append({"entity": entity, "variants": variants, "asset_count": sum(item["view_count"] for item in variants)})
        return rows

    return {key: flatten(value) for key, value in matrix.items()}


def collect_review_queue(project_dir: Path, phase_matrix: list[dict]) -> list[dict]:
    queue = []
    for row in phase_matrix:
        episode = row["episode"]
        for phase in row.get("ordered", []):
            for item in phase.get("needs_human_review") or []:
                queue.append({
                    "episode": episode,
                    "phase": phase["phase"],
                    "label": phase["label"],
                    "severity": "review",
                    "text": str(item),
                    "source": phase.get("path", ""),
                })
            if phase["status"] in {"pending", "failed", "missing"} and phase["phase"] in {"2.2", "2.3", "3.5", "5", "6"}:
                queue.append({
                    "episode": episode,
                    "phase": phase["phase"],
                    "label": phase["label"],
                    "severity": "pending" if phase["status"] == "pending" else "gap",
                    "text": f"{phase['label']} 状态为 {phase['status']}",
                    "source": phase.get("path", ""),
                })

    outputs_dir = project_dir / "outputs"
    for path in sorted(outputs_dir.glob("ep*/review/*.md")) + sorted(outputs_dir.glob("ep*/narrative-review.md")) + sorted(outputs_dir.glob("ep*/art-direction-review.md")):
        if path.is_file():
            episode = path.parent.parent.name if path.parent.name == "review" else path.parent.name
            queue.append({
                "episode": episode,
                "phase": "review",
                "label": "审核资料",
                "severity": "info",
                "text": path.name,
                "source": rel(path),
            })
    return queue[:80]


def shot_phase_status(shot: dict, project_dir: Path, phase_matrix: list[dict]) -> dict:
    episode = shot.get("episode", "")
    shot_number = int(shot.get("shot") or 0)
    phases = next((row.get("phases", {}) for row in phase_matrix if row.get("episode") == episode), {})
    video_candidates = [
        project_dir / "outputs" / episode / "deliverables" / "shots" / f"shot-{shot_number:02d}.mp4",
        project_dir / "outputs" / episode / "videos" / f"shot-{shot_number:02d}.mp4",
    ]
    video = next((path for path in video_candidates if path.exists()), None)
    return {
        "ontology": phases.get("0", {}).get("status", "missing"),
        "storyboard": "completed" if shot.get("image_url") else phases.get("2.3", {}).get("status", "missing"),
        "packet": "completed" if shot.get("packet") else phases.get("3.5", {}).get("status", "missing"),
        "video": "completed" if video else phases.get("5", {}).get("status", "missing"),
        "qa": phases.get("6", {}).get("status", "missing"),
        "video_path": rel(video) if video else "",
        "video_url": media_url(video) if video else "",
    }


def pipeline_from_project(project_dir: Path, counts: dict, phases: list[dict]) -> list[dict]:
    phase_done = any(str(phase.get("status")).lower() == "completed" for phase in phases)
    checks = [
        ("需求确认", counts["scripts"] > 0 or (project_dir / "state" / "preprocess.json").exists()),
        ("创作方案", counts["scripts"] > 0 or phase_done),
        ("角色档案", counts["characters"] > 0),
        ("故事地图 / 分集目录", counts["scenes"] > 0),
        ("分集本", counts["scripts"] > 0),
        ("视觉指导", count_files(project_dir / "outputs", ("visual-direction.yaml", "visual-direction.md")) > 0),
        ("分镜表", counts["storyboards"] > 0),
        ("导出交付包", count_files(project_dir / "outputs", ("manifest.json", "final.mp4", "*final*.mp4")) > 0),
    ]
    first_pending = next((index for index, (_, done) in enumerate(checks) if not done), len(checks))
    pipeline = []
    for index, (name, done) in enumerate(checks, start=1):
        status = "completed" if done else "in_progress" if index - 1 == first_pending else "pending"
        pipeline.append({"index": index, "name": name, "status": status})
    return pipeline


def project_summary(project_dir: Path) -> dict:
    files = project_files(project_dir)
    state_dir = project_dir / "state"
    outputs_dir = project_dir / "outputs"
    preprocess = read_json(state_dir / "preprocess.json")
    phases, shot_states = collect_states(project_dir)
    counts = {
        "scripts": count_files(project_dir / "script", ("*.md",)),
        "episodes": count_files(project_dir / "script", ("ep*.md",)),
        "characters": count_files(project_dir / "assets" / "characters" / "profiles", ("*.yaml", "*.yml")),
        "scenes": count_files(project_dir / "assets" / "scenes" / "profiles", ("*.yaml", "*.yml")),
        "storyboards": count_files(outputs_dir, ("storyboard/*.png", "storyboard/*.jpg", "storyboard/*.webp")),
        "videos": count_files(outputs_dir, ("*.mp4", "*.mov")),
        "state_files": count_files(state_dir, ("*.json",)),
    }
    pipeline = pipeline_from_project(project_dir, counts, phases)
    completed_nodes = sum(1 for node in pipeline if node["status"] == "completed")
    status = "completed" if completed_nodes == len(pipeline) else "active" if completed_nodes else "draft"
    mtime = latest_mtime(files + [project_dir])
    first_script = next(iter(collect_scripts(project_dir)), {})
    return {
        "id": project_dir.name,
        "name": project_dir.name,
        "title": project_dir.name,
        "headline": first_script.get("title") or preprocess.get("project") or project_dir.name,
        "source": preprocess.get("source", ""),
        "status": status,
        "counts": counts,
        "progress": {
            "completed_nodes": completed_nodes,
            "total_nodes": len(pipeline),
            "percent": round((completed_nodes / len(pipeline)) * 100, 1) if pipeline else 0,
        },
        "current_node": next((node for node in pipeline if node["status"] == "in_progress"), pipeline[-1] if pipeline else {}),
        "updated_at": iso_from_mtime(mtime),
    }


def project_detail(project_id: str) -> dict | None:
    project_dir = PROJECTS_ROOT / project_id
    if not project_dir.is_dir():
        return None

    summary = project_summary(project_dir)
    phases, shot_states = collect_states(project_dir)
    phase_matrix = collect_phase_matrix(project_dir)
    pipeline = pipeline_from_project(project_dir, summary["counts"], phases)
    character_profiles = sorted((project_dir / "assets" / "characters" / "profiles").glob("*.yaml"))
    scene_profiles = sorted((project_dir / "assets" / "scenes" / "profiles").glob("*.yaml"))
    characters = [
        summarize_profile(path, project_dir / "assets" / "characters" / "images", f"C{index:03d}")
        for index, path in enumerate(character_profiles, start=1)
    ]
    scenes = [
        summarize_profile(path, project_dir / "assets" / "scenes" / "images", f"S{index:03d}")
        for index, path in enumerate(scene_profiles, start=1)
    ]
    deliverables = []
    for path in sorted((project_dir / "outputs").glob("ep*/deliverables/*")):
        if path.is_file() and not path.name.startswith("."):
            deliverables.append({"name": path.name, "path": rel(path), "url": media_url(path), "episode": path.parent.parent.name})
    commands = [
        {"label": "查看状态", "command": f"~status {project_id}"},
        {"label": "继续生成", "command": f"~batch --project {project_id} --resume"},
        {"label": "打开审核", "command": "~review"},
        {"label": "查看链路", "command": "~trace"},
    ]
    storyboards = collect_storyboards(project_dir, shot_states)
    for shot in storyboards:
        shot["phase_status"] = shot_phase_status(shot, project_dir, phase_matrix)

    ontology = collect_ontology(project_dir)
    asset_matrix = collect_asset_matrix(project_dir)
    review_queue = collect_review_queue(project_dir, phase_matrix)

    detail = {
        **summary,
        "pipeline": pipeline,
        "phase_matrix": phase_matrix,
        "ontology": ontology,
        "asset_matrix": asset_matrix,
        "review_queue": review_queue,
        "scripts": collect_scripts(project_dir),
        "characters": characters,
        "scenes": scenes,
        "phases": phases,
        "shot_states": shot_states,
        "storyboards": storyboards,
        "deliverables": deliverables,
        "commands": commands,
    }
    return detail


def extract_yaml_value(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*[\"']?([^\"'\n#]+)", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def config_summary() -> dict:
    seedance_file = REPO_ROOT / "config" / "platforms" / "seedance-v2.yaml"
    endpoints_file = REPO_ROOT / "config" / "api-endpoints.yaml"
    seedance_text = text_sample(seedance_file, 12000) if seedance_file.exists() else ""
    endpoints_text = text_sample(endpoints_file, 12000) if endpoints_file.exists() else ""
    config_files = sorted([path for path in (REPO_ROOT / "config").rglob("*") if path.is_file() and path.suffix in {".yaml", ".yml", ".json"}])
    return {
        "files": [rel(path) for path in config_files],
        "seedance": {
            "default_model": extract_yaml_value(seedance_text, "default_model"),
            "generation_backend": extract_yaml_value(seedance_text, "generation_backend"),
            "max_prompt_length": extract_yaml_value(seedance_text, "max_prompt_length"),
            "max_concurrent_workers": extract_yaml_value(seedance_text, "max_concurrent_workers"),
            "video_model": extract_yaml_value(seedance_text, "video_model"),
            "image_model": extract_yaml_value(seedance_text, "image_model"),
            "video_resolution": extract_yaml_value(seedance_text, "video_resolution"),
        },
        "endpoints": {
            "seedance_base_url": re.search(r"seedance:[\s\S]*?base_url:\s*[\"']([^\"']+)", endpoints_text).group(1)
            if re.search(r"seedance:[\s\S]*?base_url:\s*[\"']([^\"']+)", endpoints_text)
            else "",
            "tuzi_base_url": re.search(r"tuzi:[\s\S]*?base_url:\s*[\"']([^\"']+)", endpoints_text).group(1)
            if re.search(r"tuzi:[\s\S]*?base_url:\s*[\"']([^\"']+)", endpoints_text)
            else "",
        },
        "env": {
            "ARK_API_KEY": bool(os.getenv("ARK_API_KEY")),
            "TUZI_API_KEY": bool(os.getenv("TUZI_API_KEY")),
            "IMAGE_GEN_API_KEY": bool(os.getenv("IMAGE_GEN_API_KEY")),
            "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        },
    }


def validate_project_id(project_id: str) -> Path | None:
    if not project_id or not SAFE_ID_RE.match(project_id):
        return None
    project_dir = PROJECTS_ROOT / project_id
    return project_dir if project_dir.is_dir() else None


def latest_trace_session() -> Path | None:
    traces_root = REPO_ROOT / "state" / "traces"
    if not traces_root.exists():
        return None
    sessions = [path for path in traces_root.iterdir() if path.is_dir()]
    if not sessions:
        return None
    return max(sessions, key=lambda path: path.stat().st_mtime)


def job_path(job_id: str) -> Path:
    return JOBS_ROOT / f"{job_id}.json"


def job_log_path(job_id: str) -> Path:
    return JOBS_ROOT / f"{job_id}.log"


def read_job(job_id: str) -> dict:
    if not SAFE_ID_RE.match(job_id):
        return {}
    return read_json(job_path(job_id))


def update_job(job_id: str, **updates: object) -> dict:
    data = read_job(job_id)
    if not data:
        return {}
    data.update(updates)
    data["updated_at"] = utc_now()
    write_json(job_path(job_id), data)
    return data


def append_job_log(job_id: str, text: str) -> None:
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    with job_log_path(job_id).open("a", encoding="utf-8", errors="replace") as fh:
        fh.write(text)
        if text and not text.endswith("\n"):
            fh.write("\n")


def job_with_log(job_id: str) -> dict:
    job = read_job(job_id)
    if not job:
        return {}
    log_path = job_log_path(job_id)
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8", errors="replace")
        job["log_tail"] = text[-MAX_LOG_TAIL:]
    else:
        job["log_tail"] = ""
    return job


def list_jobs(limit: int = 20) -> list[dict]:
    if not JOBS_ROOT.exists():
        return []
    jobs = []
    for path in sorted(JOBS_ROOT.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        data = read_json(path)
        if data:
            data["log_tail"] = ""
            jobs.append(data)
    return jobs


def make_job(action: dict, payload: dict, command: list[str] | None = None) -> dict:
    job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job = {
        "id": job_id,
        "action": action["id"],
        "label": action["label"],
        "status": "queued",
        "project_id": payload.get("project_id", ""),
        "episode": payload.get("episode", ""),
        "risk": action["risk"],
        "mutates": action["mutates"],
        "command": " ".join(command or []),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    write_json(job_path(job_id), job)
    append_job_log(job_id, f"[{job['created_at']}] queued {action['id']}")
    return job


def queued_job_response(job: dict) -> dict:
    return {
        **job,
        "log_tail": f"[{job['created_at']}] queued {job['action']}\n",
    }


def action_catalog() -> dict:
    traces = latest_trace_session()
    return {
        "actions": list(ACTION_REGISTRY.values()),
        "capabilities": {
            "remote_trigger_configured": bool(os.getenv("CLAUDE_TRIGGER_ID") and os.getenv("CLAUDE_TRIGGER_TOKEN")),
            "latest_trace_session": rel(traces) if traces else "",
            "jobs_root": rel(JOBS_ROOT),
        },
    }


def build_action_command(action_id: str, payload: dict) -> list[str] | None:
    project_id = str(payload.get("project_id") or "")
    episode = str(payload.get("episode") or "")

    if action_id == "env_check":
        return ["bash", "scripts/api-caller.sh", "env-check"]

    if action_id == "workflow_sync":
        if not validate_project_id(project_id):
            raise ValueError("invalid project_id")
        command = [repo_python(), "scripts/workflow-sync.py", "--project", project_id]
        if episode:
            if not EPISODE_RE.fullmatch(episode):
                raise ValueError("invalid episode")
            command.extend(["--episode", episode])
        else:
            command.append("--all-output-episodes")
        return command

    if action_id == "trace_summary":
        trace_session = str(payload.get("trace_session") or "")
        if trace_session:
            if not SAFE_ID_RE.match(Path(trace_session).name):
                raise ValueError("invalid trace_session")
            trace_dir = REPO_ROOT / "state" / "traces" / Path(trace_session).name
        else:
            trace_dir = latest_trace_session()
        if not trace_dir or not trace_dir.is_dir():
            raise ValueError("trace session not found")
        return ["bash", "scripts/api-caller.sh", "trace-summary", rel(trace_dir)]

    return None


def run_subprocess_job(job_id: str, command: list[str]) -> None:
    update_job(job_id, status="running", started_at=utc_now())
    append_job_log(job_id, f"$ {' '.join(command)}")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        update_job(job_id, pid=process.pid)
        assert process.stdout is not None
        for line in process.stdout:
            append_job_log(job_id, line)
        code = process.wait()
        update_job(
            job_id,
            status="succeeded" if code == 0 else "failed",
            exit_code=code,
            completed_at=utc_now(),
        )
        append_job_log(job_id, f"[exit {code}]")
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc), completed_at=utc_now())
        append_job_log(job_id, f"[error] {exc}")


def run_resume_request_job(job_id: str, payload: dict) -> None:
    project_id = str(payload.get("project_id") or "")
    if not validate_project_id(project_id):
        update_job(job_id, status="failed", error="invalid project_id", completed_at=utc_now())
        return

    update_job(job_id, status="running", started_at=utc_now())
    prompt = f"~batch --project {project_id} --resume"
    request_payload = {
        "job_id": job_id,
        "project_id": project_id,
        "prompt": prompt,
        "created_at": utc_now(),
        "source": "studio-ui",
    }
    request_path = REQUESTS_ROOT / f"{job_id}.json"
    write_json(request_path, request_payload)
    append_job_log(job_id, f"request written: {rel(request_path)}")
    append_job_log(job_id, f"prompt: {prompt}")

    trigger_id = os.getenv("CLAUDE_TRIGGER_ID", "")
    trigger_token = os.getenv("CLAUDE_TRIGGER_TOKEN", "")
    if trigger_id and trigger_token:
        url = f"https://api.claude.ai/v1/code/triggers/{trigger_id}/run"
        body = json.dumps({"prompt": prompt}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {trigger_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                append_job_log(job_id, f"remote trigger status: {response.status}")
            update_job(job_id, status="succeeded", completed_at=utc_now(), request_path=rel(request_path))
        except urllib.error.URLError as exc:
            update_job(
                job_id,
                status="failed",
                error=f"remote trigger failed: {exc}",
                completed_at=utc_now(),
                request_path=rel(request_path),
            )
            append_job_log(job_id, f"[trigger error] {exc}")
        return

    append_job_log(job_id, "remote trigger not configured; request file is ready for agent pickup")
    update_job(job_id, status="succeeded", completed_at=utc_now(), request_path=rel(request_path))


def create_action_job(payload: dict) -> dict:
    action_id = str(payload.get("action") or "")
    action = ACTION_REGISTRY.get(action_id)
    if not action:
        raise ValueError("unknown action")
    if action["requires_confirmation"] and not payload.get("confirmed"):
        raise PermissionError("confirmation required")

    if action_id == "request_resume":
        job = make_job(action, payload)
        response_job = queued_job_response(job)
        thread = threading.Thread(target=run_resume_request_job, args=(job["id"], payload), daemon=True)
        thread.start()
        return response_job

    command = build_action_command(action_id, payload)
    if not command:
        raise ValueError("action has no runner")
    job = make_job(action, payload, command)
    response_job = queued_job_response(job)
    thread = threading.Thread(target=run_subprocess_job, args=(job["id"], command), daemon=True)
    thread.start()
    return response_job


def list_projects() -> dict:
    summaries = [project_summary(path) for path in project_dirs()]
    summaries.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    config = config_summary()
    stats = {
        "projects_total": len(summaries),
        "active_projects": len([item for item in summaries if item["status"] == "active"]),
        "drafts": len([item for item in summaries if item["status"] == "draft"]),
        "scripts": sum(item["counts"]["scripts"] for item in summaries),
        "characters": sum(item["counts"]["characters"] for item in summaries),
        "scenes": sum(item["counts"]["scenes"] for item in summaries),
        "storyboards": sum(item["counts"]["storyboards"] for item in summaries),
        "videos": sum(item["counts"]["videos"] for item in summaries),
        "state_files": sum(item["counts"]["state_files"] for item in summaries),
        "config_files": len(config["files"]),
    }
    return {
        "connected": True,
        "repo_root": str(REPO_ROOT),
        "projects_root": rel(PROJECTS_ROOT),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "config": config,
        "projects": summaries,
    }


class StudioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_ROOT), **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[studio-ui] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/health":
            return json_response(self, {"status": "ok", "repo_root": str(REPO_ROOT)})
        if path == "/api/actions":
            return json_response(self, action_catalog())
        if path == "/api/jobs":
            return json_response(self, {"jobs": list_jobs()})
        if path.startswith("/api/jobs/"):
            job_id = path.removeprefix("/api/jobs/").strip("/")
            job = job_with_log(job_id)
            if not job:
                return error_response(self, HTTPStatus.NOT_FOUND, f"job not found: {job_id}")
            return json_response(self, job)
        if path == "/api/projects":
            return json_response(self, list_projects())
        if path.startswith("/api/projects/"):
            project_id = path.removeprefix("/api/projects/").strip("/")
            if "/" in project_id or not project_id:
                return error_response(self, HTTPStatus.BAD_REQUEST, "invalid project id")
            detail = project_detail(project_id)
            if detail is None:
                return error_response(self, HTTPStatus.NOT_FOUND, f"project not found: {project_id}")
            return json_response(self, detail)
        if path.startswith("/media/"):
            return self.serve_media(path.removeprefix("/media/"))
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/actions":
            payload = read_request_json(self)
            try:
                job = create_action_job(payload)
            except PermissionError as exc:
                return error_response(self, HTTPStatus.FORBIDDEN, str(exc))
            except ValueError as exc:
                return error_response(self, HTTPStatus.BAD_REQUEST, str(exc))
            return json_response(self, job, HTTPStatus.ACCEPTED.value)

        return error_response(self, HTTPStatus.NOT_FOUND, "not found")

    def serve_media(self, relative_path: str) -> None:
        target = safe_repo_path(relative_path)
        if not target or not target.is_file():
            return error_response(self, HTTPStatus.NOT_FOUND, "media not found")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(target.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with target.open("rb") as file:
            try:
                self.wfile.write(file.read())
            except BrokenPipeError:
                return


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Aladdin Studio UI with guarded local actions")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("STUDIO_UI_PORT", "4173")))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), StudioHandler)
    print(f"Studio UI: http://{args.host}:{args.port}/")
    print(f"Repo root: {REPO_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Studio UI")


if __name__ == "__main__":
    main()
