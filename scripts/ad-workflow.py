#!/usr/bin/env python3
"""
ad-workflow.py - 广告片工作流脚手架与 Seedance payload 编译器。

它不直接消耗 API credit；只把广告 brief 编译为可审核、可生成的结构化产物：
- 5 段广告结构（hook / product / function / trust / cta）
- ChatGPT-image-2 storyboard prompt + Tuzi payload
- Seedance 2.0 分段执行 payload（按用户设置总时长自动切分）
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


BEAT_SPECS = [
    {
        "role": "hook",
        "label": "钩子",
        "weight": 0.18,
        "objective": "用痛点、反差或结果承诺抓住注意力。",
    },
    {
        "role": "product",
        "label": "产品",
        "weight": 0.18,
        "objective": "让产品第一次清楚出场，建立人物、场景和品牌关系。",
    },
    {
        "role": "function",
        "label": "功能",
        "weight": 0.28,
        "objective": "展示核心功能如何解决问题，不做抽象口号。",
    },
    {
        "role": "trust",
        "label": "信任",
        "weight": 0.18,
        "objective": "用证据、结果、对比或真实使用细节降低怀疑。",
    },
    {
        "role": "cta",
        "label": "CTA",
        "weight": 0.18,
        "objective": "收口到一个明确动作，让观众知道下一步做什么。",
    },
]

RATIO_OPTIONS = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"}
RESOLUTION_OPTIONS = {"480p", "720p", "1080p", "2K"}


@dataclass(frozen=True)
class SegmentLimit:
    minimum: int = 4
    maximum: int = 15


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip()).strip("-").lower()
    return slug or "ad"


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML 顶层必须是 object: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False, width=120)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def allocate_beat_seconds(total_duration: int) -> list[int]:
    if total_duration < len(BEAT_SPECS):
        raise ValueError(f"广告结构有 {len(BEAT_SPECS)} 个 beat，总时长至少需要 {len(BEAT_SPECS)} 秒")

    raw = [spec["weight"] * total_duration for spec in BEAT_SPECS]
    durations = [max(1, math.floor(value)) for value in raw]
    delta = total_duration - sum(durations)

    if delta > 0:
        order = sorted(range(len(raw)), key=lambda i: raw[i] - math.floor(raw[i]), reverse=True)
        for index in order:
            if delta <= 0:
                break
            durations[index] += 1
            delta -= 1
    elif delta < 0:
        order = sorted(range(len(raw)), key=lambda i: raw[i] - math.floor(raw[i]))
        for index in order:
            while delta < 0 and durations[index] > 1:
                durations[index] -= 1
                delta += 1

    if sum(durations) != total_duration:
        raise AssertionError(f"duration allocation failed: {durations} != {total_duration}")
    return durations


def allocate_seedance_segments(total_duration: int, limit: SegmentLimit) -> list[dict[str, int]]:
    if total_duration < limit.minimum:
        raise ValueError(f"Seedance 单段最短 {limit.minimum} 秒，广告总时长不能小于 {limit.minimum} 秒")

    count = math.ceil(total_duration / limit.maximum)
    if total_duration / count < limit.minimum:
        raise ValueError(
            f"无法在 Seedance {limit.minimum}-{limit.maximum} 秒限制内切分 {total_duration} 秒广告"
        )

    base = total_duration // count
    remainder = total_duration % count
    segments: list[dict[str, int]] = []
    start = 0
    for index in range(count):
        duration = base + (1 if index < remainder else 0)
        if not (limit.minimum <= duration <= limit.maximum):
            raise AssertionError(f"invalid segment duration: {duration}")
        end = start + duration
        segments.append({"segment_index": index + 1, "start_sec": start, "end_sec": end, "duration_sec": duration})
        start = end
    return segments


def overlapping_roles(beats: list[dict[str, Any]], start_sec: int, end_sec: int) -> list[str]:
    roles: list[str] = []
    for beat in beats:
        if beat["start_sec"] < end_sec and beat["end_sec"] > start_sec:
            roles.append(str(beat["role"]))
    return roles


def build_brief(args: argparse.Namespace) -> dict[str, Any]:
    ad_id = args.ad or slugify(args.product)
    return {
        "project": args.project,
        "ad_id": ad_id,
        "product": args.product,
        "brand": args.brand or args.product,
        "target_duration_sec": args.duration,
        "ratio": args.ratio,
        "resolution": args.resolution,
        "platform": args.platform,
        "audience": args.audience,
        "product_description": args.product_description,
        "selling_points": args.selling_point or [],
        "proof_points": args.proof or [],
        "cta": args.cta,
        "visual_style": args.style,
        "fixed_character_ref": args.character_ref,
        "created_at": utc_now(),
    }


def normalize_brief(brief: dict[str, Any]) -> dict[str, Any]:
    required = ["project", "ad_id", "product", "brand", "target_duration_sec", "ratio", "cta"]
    missing = [key for key in required if not brief.get(key)]
    if missing:
        raise ValueError(f"brief 缺少字段: {', '.join(missing)}")

    duration = int(brief["target_duration_sec"])
    if duration < len(BEAT_SPECS):
        raise ValueError(f"target_duration_sec 至少为 {len(BEAT_SPECS)}")
    if str(brief["ratio"]) not in RATIO_OPTIONS:
        raise ValueError(f"ratio 不支持: {brief['ratio']}")
    resolution = str(brief.get("resolution") or "1080p")
    if resolution not in RESOLUTION_OPTIONS:
        raise ValueError(f"resolution 不支持: {resolution}")

    brief = dict(brief)
    brief["target_duration_sec"] = duration
    brief["resolution"] = resolution
    brief.setdefault("platform", "")
    brief.setdefault("audience", "")
    brief.setdefault("product_description", "")
    brief.setdefault("selling_points", [])
    brief.setdefault("proof_points", [])
    brief.setdefault("visual_style", "真人广告片，商业质感，清晰产品展示")
    brief.setdefault("fixed_character_ref", "")
    return brief


def build_beats(brief: dict[str, Any]) -> list[dict[str, Any]]:
    durations = allocate_beat_seconds(int(brief["target_duration_sec"]))
    product = str(brief["product"])
    brand = str(brief["brand"])
    selling_points = [str(item) for item in brief.get("selling_points") or []]
    proof_points = [str(item) for item in brief.get("proof_points") or []]
    cta = str(brief["cta"])

    function_copy = " / ".join(selling_points[:3]) if selling_points else "展示一个最关键的功能动作"
    proof_copy = " / ".join(proof_points[:2]) if proof_points else "用真实使用结果或前后对比建立信任"

    templates = {
        "hook": {
            "screen_text": f"别再直接拍产品，先让用户看到问题",
            "voiceover": f"如果你也在为{product}的转化发愁，问题可能不在素材数量。",
            "action": "人物停在一个明确痛点场景里，表情和动作先让观众代入。",
            "product_focus": "产品暂不完全露出，只给出品牌或包装线索。",
            "transition_to_next": "由人物视线或手部动作切到产品正式出场。",
        },
        "product": {
            "screen_text": f"{brand} 出场",
            "voiceover": f"这条广告先让{product}解决一个具体问题。",
            "action": "人物拿起、打开或开始使用产品，画面给到品牌名和核心形态。",
            "product_focus": "品牌标识、产品外观、使用入口必须清楚可见。",
            "transition_to_next": "从产品外观切到功能动作细节。",
        },
        "function": {
            "screen_text": function_copy,
            "voiceover": f"关键不是说它好，而是拍清楚它怎么起作用：{function_copy}。",
            "action": "用一个连续动作展示使用前、使用中、使用后的变化。",
            "product_focus": "功能界面、关键部件或使用效果占画面主体。",
            "transition_to_next": "用结果画面或反应镜头承接到信任证明。",
        },
        "trust": {
            "screen_text": proof_copy,
            "voiceover": proof_copy,
            "action": "展示真实反馈、数据、对比结果、细节质感或第三方场景。",
            "product_focus": "产品仍在画面中，避免变成空泛背书。",
            "transition_to_next": "从信任证据切到品牌收口和行动指令。",
        },
        "cta": {
            "screen_text": cta,
            "voiceover": cta,
            "action": "人物完成动作，看向产品或镜头，品牌和行动入口同时出现。",
            "product_focus": "品牌名、产品名、购买/预约/下载入口同屏收口。",
            "transition_to_next": "最后一帧保持 0.5 秒，便于平台自动截帧。",
        },
    }

    beats: list[dict[str, Any]] = []
    start = 0
    for index, spec in enumerate(BEAT_SPECS):
        duration = durations[index]
        end = start + duration
        role = str(spec["role"])
        beats.append(
            {
                "beat_id": f"{brief['ad_id']}-beat-{index + 1:02d}",
                "role": role,
                "label": spec["label"],
                "start_sec": start,
                "end_sec": end,
                "duration_sec": duration,
                "objective": spec["objective"],
                **templates[role],
            }
        )
        start = end
    return beats


def build_storyboard_prompt(brief: dict[str, Any], beats: list[dict[str, Any]]) -> str:
    panel_lines = []
    for index, beat in enumerate(beats, start=1):
        panel_lines.append(
            "\n".join(
                [
                    f"Panel {index} / {beat['label']} / {beat['start_sec']}-{beat['end_sec']}s",
                    f"- 人物动作: {beat['action']}",
                    f"- 字幕/台词: {beat['screen_text']} / {beat['voiceover']}",
                    f"- 产品重点: {beat['product_focus']}",
                    f"- 转场: {beat['transition_to_next']}",
                ]
            )
        )

    character_ref = brief.get("fixed_character_ref") or "无外部人物参考时，保持同一个真人演员外貌、服装和发型贯穿 5 格。"
    return "\n\n".join(
        [
            "生成一张可拍摄的商业广告 storyboard，而不是单张海报。",
            f"品牌: {brief['brand']}",
            f"产品: {brief['product']}",
            f"目标平台: {brief.get('platform') or '短视频平台'}",
            f"目标时长: {brief['target_duration_sec']} 秒",
            f"画幅: {brief['ratio']}",
            f"视觉风格: {brief.get('visual_style')}",
            f"固定人物参考: {character_ref}",
            "画面要求: 一张图包含 5 个清晰分镜格；每格带时间轴、人物动作、字幕/台词、转场箭头、品牌信息；真人拍摄质感；构图可执行；不要做抽象海报。",
            "5 个镜头:",
            "\n\n".join(panel_lines),
        ]
    )


def build_segment_prompt(brief: dict[str, Any], beats: list[dict[str, Any]], segment: dict[str, int]) -> str:
    roles = overlapping_roles(beats, segment["start_sec"], segment["end_sec"])
    active = [beat for beat in beats if beat["role"] in roles]
    lines = [
        f"按广告 storyboard 执行第 {segment['segment_index']} 段，不自由发挥。",
        f"品牌: {brief['brand']}；产品: {brief['product']}。",
        f"本段时间: {segment['start_sec']}-{segment['end_sec']} 秒，时长 {segment['duration_sec']} 秒。",
        f"画幅: {brief['ratio']}；风格: {brief.get('visual_style')}",
        "固定人物: 全段保持同一个真人演员外貌、服装、发型、年龄和气质一致。",
        "产品连续性: 产品外观、品牌标识、使用动作和字幕风格保持一致。",
        "节奏: 广告片节奏，镜头干净，产品清楚，避免炫技式无意义运动。",
        "",
        "本段覆盖的广告 beat:",
    ]
    for beat in active:
        lines.extend(
            [
                f"- {beat['label']} ({beat['start_sec']}-{beat['end_sec']}s): {beat['objective']}",
                f"  动作: {beat['action']}",
                f"  字幕/台词: {beat['screen_text']} / {beat['voiceover']}",
                f"  转场: {beat['transition_to_next']}",
            ]
        )
    lines.append("如果参考图包含完整 storyboard，只参考镜头顺序、人物位置、品牌信息和构图，不复制文字错误或多余装饰。")
    return "\n".join(lines)


def build_structure(project_root: Path, brief: dict[str, Any], image_model: str, seedance_model: str) -> dict[str, Any]:
    brief = normalize_brief(brief)
    project = str(brief["project"])
    ad_id = str(brief["ad_id"])
    ad_root = project_root / "projects" / project / "ads" / ad_id
    output_root = project_root / "projects" / project / "outputs" / "ads" / ad_id
    state_root = project_root / "projects" / project / "state" / "ads"
    storyboard_image_path = output_root / "storyboard" / "ad-storyboard.png"

    beats = build_beats(brief)
    segment_limit = SegmentLimit()
    seedance_segments = allocate_seedance_segments(int(brief["target_duration_sec"]), segment_limit)
    storyboard_prompt = build_storyboard_prompt(brief, beats)

    prompt_path = output_root / "storyboard" / "storyboard-prompt.md"
    image_payload_path = output_root / "storyboard" / "tuzi-storyboard-payload.json"
    write_text(prompt_path, storyboard_prompt + "\n")
    write_json(
        image_payload_path,
        {
            "model": image_model,
            "prompt": storyboard_prompt,
            "n": 1,
            "size": brief["ratio"],
        },
    )

    compiled_segments: list[dict[str, Any]] = []
    for segment in seedance_segments:
        segment_id = f"{ad_id}-seg-{segment['segment_index']:02d}"
        prompt = build_segment_prompt(brief, beats, segment)
        payload_path = output_root / "seedance-payloads" / f"{segment_id}.dreamina.json"
        video_output_path = output_root / "videos" / f"{segment_id}.mp4"
        payload = {
            "command": "multimodal2video",
            "prompt": prompt,
            "images": [
                storyboard_image_path.as_posix(),
                *([str(brief["fixed_character_ref"])] if brief.get("fixed_character_ref") else []),
            ],
            "duration": segment["duration_sec"],
            "ratio": brief["ratio"],
            "video_resolution": brief["resolution"],
            "model_version": seedance_model,
            "poll": "true",
        }
        write_json(payload_path, payload)
        compiled_segments.append(
            {
                "segment_id": segment_id,
                **segment,
                "beat_roles": overlapping_roles(beats, segment["start_sec"], segment["end_sec"]),
                "prompt": prompt,
                "payload_path": payload_path.relative_to(project_root).as_posix(),
                "output_path": video_output_path.relative_to(project_root).as_posix(),
            }
        )

    structure = {
        "schema_version": "ad-workflow/v1",
        "project": project,
        "ad_id": ad_id,
        "created_at": utc_now(),
        "brief_path": (ad_root / "brief.yaml").relative_to(project_root).as_posix(),
        "target_duration_sec": brief["target_duration_sec"],
        "ratio": brief["ratio"],
        "resolution": brief["resolution"],
        "funnel": [spec["role"] for spec in BEAT_SPECS],
        "brief": brief,
        "beats": beats,
        "storyboard": {
            "panel_count": 5,
            "image_model": image_model,
            "prompt_path": prompt_path.relative_to(project_root).as_posix(),
            "payload_path": image_payload_path.relative_to(project_root).as_posix(),
            "expected_image_path": storyboard_image_path.relative_to(project_root).as_posix(),
        },
        "seedance": {
            "model": seedance_model,
            "duration_min_sec": segment_limit.minimum,
            "duration_max_sec": segment_limit.maximum,
            "segments": compiled_segments,
        },
        "iteration_slots": {
            "hook_variants": [],
            "selling_point_order_variants": [],
            "subtitle_variants": [],
            "character_style_variants": [],
            "cta_variants": [],
        },
    }

    write_yaml(ad_root / "brief.yaml", brief)
    write_yaml(output_root / "ad-structure.yaml", structure)
    write_json(
        state_root / f"{ad_id}-phase1.json",
        {
            "phase": 1,
            "name": "ad_structure",
            "status": "completed",
            "completed_at": utc_now(),
            "data": {
                "duration_sec": brief["target_duration_sec"],
                "beats": len(beats),
                "seedance_segments": len(compiled_segments),
                "structure_path": f"projects/{project}/outputs/ads/{ad_id}/ad-structure.yaml",
            },
        },
    )
    return structure


def validate_structure(structure: dict[str, Any]) -> None:
    beats = structure.get("beats") or []
    segments = (structure.get("seedance") or {}).get("segments") or []
    target = int(structure.get("target_duration_sec") or 0)
    minimum = int((structure.get("seedance") or {}).get("duration_min_sec") or 4)
    maximum = int((structure.get("seedance") or {}).get("duration_max_sec") or 15)

    if [beat.get("role") for beat in beats] != [spec["role"] for spec in BEAT_SPECS]:
        raise ValueError("beats 必须按 hook/product/function/trust/cta 排列")
    if sum(int(beat.get("duration_sec") or 0) for beat in beats) != target:
        raise ValueError("beat 时长总和不等于目标时长")
    if sum(int(segment.get("duration_sec") or 0) for segment in segments) != target:
        raise ValueError("Seedance segment 时长总和不等于目标时长")
    for segment in segments:
        duration = int(segment.get("duration_sec") or 0)
        if not (minimum <= duration <= maximum):
            raise ValueError(f"Seedance segment 时长越界: {segment.get('segment_id')}={duration}")
        if not segment.get("beat_roles"):
            raise ValueError(f"Seedance segment 未映射广告 beat: {segment.get('segment_id')}")


def cmd_init(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    brief = build_brief(args)
    structure = build_structure(project_root, brief, args.image_model, args.seedance_model)
    validate_structure(structure)
    print(
        json.dumps(
            {
                "project": structure["project"],
                "ad_id": structure["ad_id"],
                "structure_path": f"projects/{structure['project']}/outputs/ads/{structure['ad_id']}/ad-structure.yaml",
                "storyboard_payload": structure["storyboard"]["payload_path"],
                "seedance_segments": len(structure["seedance"]["segments"]),
                "duration_sec": structure["target_duration_sec"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    brief = read_yaml(Path(args.brief))
    structure = build_structure(project_root, brief, args.image_model, args.seedance_model)
    validate_structure(structure)
    print(json.dumps({"structure_path": f"projects/{structure['project']}/outputs/ads/{structure['ad_id']}/ad-structure.yaml"}, ensure_ascii=False))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    structure = read_yaml(Path(args.structure))
    validate_structure(structure)
    print(json.dumps({"valid": True, "structure": args.structure}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="广告片工作流脚手架与 Seedance payload 编译器")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=".", help="仓库根目录")
    common.add_argument("--image-model", default="gpt-image-2.0", help="storyboard 生图模型")
    common.add_argument("--seedance-model", default="seedance2.0fast", help="Dreamina Seedance 模型")

    init = subparsers.add_parser("init", parents=[common], help="从命令行 brief 创建广告片结构")
    init.add_argument("--project", required=True, help="projects/{project} 名称")
    init.add_argument("--ad", help="广告 ID，默认从产品名生成")
    init.add_argument("--product", required=True, help="产品名")
    init.add_argument("--brand", help="品牌名，默认等于产品名")
    init.add_argument("--duration", type=int, required=True, help="广告总时长，用户在开始时设定")
    init.add_argument("--ratio", default="9:16", choices=sorted(RATIO_OPTIONS), help="目标画幅")
    init.add_argument("--resolution", default="1080p", choices=sorted(RESOLUTION_OPTIONS), help="视频分辨率")
    init.add_argument("--platform", default="抖音/小红书/Reels", help="目标投放平台")
    init.add_argument("--audience", default="", help="目标人群")
    init.add_argument("--product-description", default="", help="产品说明")
    init.add_argument("--selling-point", action="append", help="核心卖点，可重复")
    init.add_argument("--proof", action="append", help="信任证明，可重复")
    init.add_argument("--cta", required=True, help="收口行动指令")
    init.add_argument("--style", default="真人广告片，商业质感，清晰产品展示", help="视觉风格")
    init.add_argument("--character-ref", default="", help="固定人物参考图 URL 或本地路径")
    init.set_defaults(func=cmd_init)

    compile_cmd = subparsers.add_parser("compile", parents=[common], help="从 brief.yaml 重新编译广告片结构")
    compile_cmd.add_argument("--brief", required=True, help="brief.yaml 路径")
    compile_cmd.set_defaults(func=cmd_compile)

    validate = subparsers.add_parser("validate", help="校验 ad-structure.yaml")
    validate.add_argument("--structure", required=True, help="ad-structure.yaml 路径")
    validate.set_defaults(func=cmd_validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
