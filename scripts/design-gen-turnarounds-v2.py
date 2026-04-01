#!/usr/bin/env python3
"""重新生成主角三视图 - 使用详细的中文提示词"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "assets/characters/images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def generate_turnaround(name, prompt, output_file):
    """生成三视图"""
    output_path = IMAGES_DIR / output_file

    print(f"生成：{name}")
    print(f"提示词：{prompt[:100]}...")

    payload = {
        "model": "gpt-4o-image",
        "prompt": prompt,
        "n": 1,
        "size": "1792x1024"
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

        print(f"✓ {output_file}\n")
        return True

    except Exception as e:
        print(f"✗ 生成失败：{e}\n")
        return False

# 主角三视图 - 使用详细的中文提示词
characters = [
    ("苏夜-青玉蚕", """角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：苏夜（青玉蚕形态）
外貌：通体碧绿色的蚕宝宝，肥嘟嘟圆滚滚，拇指大小，眼神欠揍带着狡黠，Q版可爱风格但带点痞气。
性格特征：腹黑、嘴炮王者、贪吃、无赖。
画面要求：三个视图必须是同一只蚕，保持完全一致的颜色、体型、表情。正面视图展示正脸和眼神，侧面视图展示身体轮廓，背面视图展示背部细节。角色设计稿风格，清晰的参考线，专业角色概念设计，短剧动画风格。

禁止：不同的角色、视图融合、背景元素、文字标注""", "苏夜-qingyucan-turnaround-v2.png"),

    ("苏夜-碧鳞蛇", """角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：苏夜（碧鳞蛇形态）
外貌：筷子长度的小蛇，通体覆盖精致的碧绿色鳞片，金色瞳孔，吐着信子，鳞片纹理清晰，优雅但带着危险感。
性格特征：腹黑、狡猾、嘴炮、护短。
画面要求：三个视图必须是同一条蛇，保持完全一致的鳞片颜色、瞳孔颜色、身体粗细。正面视图展示蛇头和金色瞳孔，侧面视图展示身体S形曲线和鳞片纹理，背面视图展示背部鳞片排列。角色设计稿风格，清晰的参考线，专业角色概念设计，短剧动画风格。

禁止：不同的蛇、视图融合、背景元素、文字标注""", "苏夜-bilinse-turnaround-v2.png"),

    ("苏夜-玄冥蟒", """角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：苏夜（玄冥黑金蟒形态）
外貌：三米长的巨蟒，通体漆黑色鳞片带金色光泽，头顶有两个小鼓包（龙角雏形），金色瞳孔，威严霸气，黑金鳞片反射金属光泽。
性格特征：霸气、护短、腹黑、强大。
画面要求：三个视图必须是同一条巨蟒，保持完全一致的黑金鳞片、金色瞳孔、头顶鼓包。正面视图展示蟒头和威严眼神，侧面视图展示身体盘曲和鳞片质感，背面视图展示背部鳞片和尾部。角色设计稿风格，清晰的参考线，专业角色概念设计，短剧动画风格。

禁止：不同的蟒、视图融合、背景元素、文字标注""", "苏夜-xuanmingmang-turnaround-v2.png"),

    ("叶红衣", """角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：叶红衣（女主角）
外貌：18岁中国古装少女，红色长袍似火，高冷御姐脸，眼神透着倔强和落寞，长发飘逸，精致锁骨，身材修长，气质高冷但带着一丝脆弱。
性格特征：高冷、倔强、坚韧、重情义。
画面要求：三个视图必须是同一个女孩，保持完全一致的脸型、发型、服装、气质。正面视图展示高冷御姐脸和倔强眼神，侧面视图展示长发和身材轮廓，背面视图展示红袍背部和长发。角色设计稿风格，清晰的参考线，专业角色概念设计，短剧古装风格，写实人物比例。

禁止：不同的人物、视图融合、背景元素、文字标注、卡通化""", "叶红衣-turnaround-v2.png"),
]

print("━━━ 重新生成主角三视图（详细中文提示词）━━━\n")
print(f"总计：{len(characters)} 个角色/变体\n")

success_count = 0
for name, prompt, output_file in characters:
    if generate_turnaround(name, prompt, output_file):
        success_count += 1

print(f"\n━━━ 完成 ━━━")
print(f"成功：{success_count}/{len(characters)}")

if success_count < len(characters):
    sys.exit(1)
