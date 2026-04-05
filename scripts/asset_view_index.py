"""
asset_view_index.py — 扫描 assets/characters/images/ 和 assets/scenes/images/，
构建可检索的视角索引，供 workflow-sync.py 做 deterministic reference selection。

文件名约定：
  characters: {角色名}-{variant_id}-{view}.png   (front / side / back)
  scenes:     {场景名}-{time_of_day}.png          (day / night / dusk / dawn)
"""

from __future__ import annotations

from pathlib import Path

CHARACTER_VIEWS = ("front", "side", "back")
SCENE_TIMES = ("day", "night", "dusk", "dawn")


def build_asset_view_index(project_root: Path, project: str) -> dict:
    """返回 {characters: {name: {variant: {view: path}}}, scenes: {name: {time: path}}}"""
    base = project_root / "projects" / project / "assets"
    index: dict = {"characters": {}, "scenes": {}, "props": {}}

    char_dir = base / "characters" / "images"
    if char_dir.exists():
        for image_path in sorted(char_dir.glob("*.png")):
            stem = image_path.stem
            parts = stem.rsplit("-", 2)
            if len(parts) == 3:
                name, variant_id, view = parts
                index["characters"].setdefault(name, {}).setdefault(variant_id, {})[view] = str(image_path)
            elif len(parts) == 2:
                # 单变体：{name}-{view}.png
                name, view = parts
                index["characters"].setdefault(name, {}).setdefault("default", {})[view] = str(image_path)

    scene_dir = base / "scenes" / "images"
    if scene_dir.exists():
        for image_path in sorted(scene_dir.glob("*.png")):
            stem = image_path.stem
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                scene_name, time_of_day = parts
                index["scenes"].setdefault(scene_name, {})[time_of_day] = str(image_path)

    return index


def select_character_view(
    view_index: dict,
    name: str,
    variant_id: str,
    preferred_view: str = "front",
) -> tuple[str | None, str | None]:
    """返回 (selected_path, actual_view)，按 preferred_view → front → side → back 降级。"""
    char_variants = view_index.get("characters", {}).get(name, {})
    views = char_variants.get(variant_id) or char_variants.get("default") or {}
    fallback_order = [preferred_view] + [v for v in CHARACTER_VIEWS if v != preferred_view]
    for view in fallback_order:
        path = views.get(view)
        if path and Path(path).exists():
            return path, view
    return None, None


def select_scene_view(
    view_index: dict,
    scene_name: str,
    time_of_day: str = "day",
) -> str | None:
    """返回场景图路径，按 time_of_day → day 降级。"""
    scene_times = view_index.get("scenes", {}).get(scene_name, {})
    for candidate in [time_of_day, "day", "night"]:
        path = scene_times.get(candidate)
        if path and Path(path).exists():
            return path
    return None
