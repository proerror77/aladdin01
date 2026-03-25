#!/usr/bin/env python3
"""
xlsx-to-script.py — 将剧本 Excel 转换为系统标准 Markdown 格式
用法：python3 scripts/xlsx-to-script.py <input.xlsx> [--ep EP编号]

输出：script/ep{N}.md（每集一个文件）
"""

import sys
import re
import os
import argparse
import openpyxl

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "script")


def parse_dialogue(raw: str) -> tuple[str, str]:
    """
    解析台词列，分离对白和音效。
    返回 (dialogue, sfx)
    对白格式：角色名: "台词" 或 ROLE: "台词"
    音效格式：SFX: 描述
    """
    if not raw:
        return "", ""

    dialogue_parts = []
    sfx_parts = []

    # 按换行分割多行
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("SFX:"):
            sfx_parts.append(line[4:].strip())
        else:
            # 角色台词：ROLE: "..." 或 角色: "..."
            dialogue_parts.append(line)

    return "\n".join(dialogue_parts), "\n".join(sfx_parts)


def convert(xlsx_path: str, ep_filter: int = None):
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active

    # 按集分组
    episodes = {}
    current_ep = None

    for row in ws.iter_rows(values_only=True):
        shot_no, scene, visual, dialogue_raw = row[0], row[1], row[2], row[3]

        # 集标题行
        if shot_no and isinstance(shot_no, str) and "集" in shot_no:
            # 提取集号
            m = re.search(r"第\s*(\d+)\s*集", shot_no)
            if m:
                current_ep = int(m.group(1))
                episodes[current_ep] = []
            continue

        # 镜次行
        if shot_no and isinstance(shot_no, int) and current_ep is not None:
            dialogue, sfx = parse_dialogue(str(dialogue_raw or ""))
            episodes[current_ep].append({
                "shot": shot_no,
                "scene": str(scene or "").strip(),
                "visual": str(visual or "").strip(),
                "dialogue": dialogue,
                "sfx": sfx,
            })

    # 过滤指定集
    if ep_filter is not None:
        episodes = {k: v for k, v in episodes.items() if k == ep_filter}
        if not episodes:
            print(f"ERROR: 第 {ep_filter} 集不存在", file=sys.stderr)
            sys.exit(1)

    os.makedirs(SCRIPT_DIR, exist_ok=True)

    for ep_no, shots in sorted(episodes.items()):
        ep_id = f"ep{ep_no:02d}"
        out_path = os.path.join(SCRIPT_DIR, f"{ep_id}.md")

        lines = [
            f"# 第 {ep_no} 集\n",
            f"ep_id: {ep_id}\n",
            f"total_shots: {len(shots)}\n",
            "---\n",
        ]

        for s in shots:
            lines.append(f"\n## 镜次 {s['shot']}\n")
            lines.append(f"**场景**: {s['scene']}\n\n")
            lines.append(f"**画面**: {s['visual']}\n")
            if s["dialogue"]:
                lines.append(f"\n**台词**:\n```\n{s['dialogue']}\n```\n")
            if s["sfx"]:
                lines.append(f"\n**音效**: {s['sfx']}\n")

        with open(out_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        print(f"✓ {out_path}  ({len(shots)} 镜)")

    print(f"\n共转换 {len(episodes)} 集 → {SCRIPT_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Excel 剧本 → Markdown")
    parser.add_argument("xlsx", help="输入 Excel 文件路径")
    parser.add_argument("--ep", type=int, default=None, help="只转换指定集（如 --ep 1）")
    args = parser.parse_args()
    convert(args.xlsx, args.ep)
