#!/usr/bin/env python3
"""正确的三视图生成方法：一张图包含三个视图"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "assets/characters/images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def generate_turnaround(name, description, output_file):
    """生成三视图（一张图包含 front/side/back）"""
    output_path = IMAGES_DIR / output_file

    if output_path.exists():
        print(f"⊙ {output_file} 已存在，跳过")
        return True

    print(f"生成：{name}")

    # 正确的三视图提示词
    prompt = f"""best quality, masterpiece, character design turnaround sheet, white background, same character shown in three full-body views arranged horizontally — front view on left, side profile in center, back view on right, {description}, consistent character design across all three views with identical proportions clothing and features, neutral standing pose in each view, clean even spacing between figures, flat studio lighting, professional concept art reference quality, high resolution

Negative prompt: merged views, overlapping figures, figures touching each other, views blending into one image, different appearance between views, different proportions between views, scenic background, environmental background, dramatic lighting"""

    payload = {
        "model": "gpt-4o-image",
        "prompt": prompt,
        "n": 1,
        "size": "1792x1024"  # 16:9 横向布局
    }

    payload_file = Path("/tmp/turnaround-payload.json")
    with open(payload_file, 'w') as f:
        json.dump(payload, f)

    try:
        result = subprocess.run(
            [str(PROJECT_ROOT / "scripts/api-caller.sh"), "image_gen", "generate", str(payload_file)],
            capture_output=True,
            text=True,
            check=True,
            cwd=PROJECT_ROOT
        )

        response = json.loads(result.stdout)
        url = response['data'][0]['url']

        subprocess.run(
            [str(PROJECT_ROOT / "scripts/api-caller.sh"), "image_gen", "download", url, output_file],
            check=True,
            cwd=IMAGES_DIR
        )

        print(f"✓ {output_file}")
        return True

    except Exception as e:
        print(f"✗ 生成失败：{e}")
        return False

# 主角三视图（每个角色/变体一张图）
characters = [
    ("苏夜-青玉蚕", "a chubby bright green silkworm creature, thumb-sized, with mischievous eyes and slightly smug expression, cute fantasy creature design", "苏夜-qingyucan-turnaround.png"),

    ("苏夜-碧鳞蛇", "a chopstick-length emerald green snake with exquisite scales, golden pupils, forked tongue, elegant serpent design", "苏夜-bilinse-turnaround.png"),

    ("苏夜-玄冥蟒", "a three-meter-long python with jet-black scales with golden sheen, golden pupils, two small bumps on head, majestic serpent design", "苏夜-xuanmingmang-turnaround.png"),

    ("叶红衣", "an 18-year-old Chinese girl in flowing red robes, cold elegant face with stubborn eyes showing loneliness, long black hair, delicate features, martial arts fantasy character design", "叶红衣-turnaround.png"),
]

print("━━━ 生成主角三视图（正确方法）━━━\n")
print(f"总计：{len(characters)} 个角色/变体\n")

success_count = 0
for name, description, output_file in characters:
    if generate_turnaround(name, description, output_file):
        success_count += 1
    print()

print(f"\n━━━ 完成 ━━━")
print(f"成功：{success_count}/{len(characters)}")

if success_count < len(characters):
    sys.exit(1)
