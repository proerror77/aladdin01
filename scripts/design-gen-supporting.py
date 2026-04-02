#!/usr/bin/env python3
"""生成重要配角三视图 - 使用统一的玄幻爽剧风格"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "assets/characters/images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# 统一风格后缀（从 state/qyccan-style-guide.yaml 提取）
STYLE_SUFFIX = """
玄幻短剧风格，半写实画风，电影级质感，
高饱和度色彩，冷暖对比光影，戏剧化打光，
专业角色概念设计，角色设计稿，
三视图（正面/侧面/背面）水平排列，白色背景，
三个视图必须是同一个角色，保持完全一致
"""

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

# 重要配角三视图
characters = [
    ("赵无极", f"""角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：赵无极（反派配角）
外貌：20岁男性，华丽的紫色锦袍，傲慢的表情，眼神轻蔑，身材修长，手持折扇，贵公子气质但带着阴险。
性格特征：傲慢、阴险、自大、欺软怕硬。
气质要求：纨绔子弟的傲慢，眼神要有轻蔑和阴险感。
画面要求：三个视图必须是同一个人，保持完全一致的脸型、发型、服装、气质。正面视图展示傲慢表情和轻蔑眼神，侧面视图展示身材轮廓和折扇，背面视图展示紫色锦袍背部细节。
{STYLE_SUFFIX}

禁止：卡通化、萌系风格、不同的人物、视图融合、背景元素、文字标注""", "赵无极-turnaround.png"),

    ("王胖子", f"""角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：王胖子（喜剧配角）
外貌：18岁男性，圆润的身材，憨厚的笑容，朴素的灰色布衣，眼神真诚，肉嘟嘟的脸颊。
性格特征：憨厚、忠诚、贪吃、胆小但讲义气。
气质要求：憨厚老实，眼神要有真诚和憨厚感，带点喜剧效果。
画面要求：三个视图必须是同一个人，保持完全一致的脸型、发型、服装、气质。正面视图展示憨厚笑容和真诚眼神，侧面视图展示圆润身材，背面视图展示朴素布衣背部。
{STYLE_SUFFIX}

禁止：卡通化、萌系风格、不同的人物、视图融合、背景元素、文字标注""", "王胖子-turnaround.png"),

    ("叶如烟", f"""角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：叶如烟（反派配角）
外貌：17岁女性，粉色长裙，甜美的外表下藏着阴险，眼神表面温柔实则狠毒，长发披肩，身材娇小。
性格特征：表面甜美、内心阴险、嫉妒心强、善于伪装。
气质要求：表面甜美温柔，但眼神要有一丝阴险和嫉妒感，双面性格。
画面要求：三个视图必须是同一个女孩，保持完全一致的脸型、发型、服装、气质。正面视图展示甜美外表和微妙的阴险眼神，侧面视图展示娇小身材和长发，背面视图展示粉色长裙背部。
{STYLE_SUFFIX}

禁止：卡通化、萌系风格、不同的人物、视图融合、背景元素、文字标注""", "叶如烟-turnaround.png"),

    ("萧凡", f"""角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：萧凡（龙傲天配角）
外貌：18岁男性，白色长袍，英俊的脸庞，眼神坚定正义，剑眉星目，身材挺拔，腰间佩剑，主角光环。
性格特征：正义、自信、天赋异禀、有主角光环但会被苏夜打脸。
气质要求：正派主角气质，眼神要有坚定和正义感，带着自信和天赋的光芒。
画面要求：三个视图必须是同一个人，保持完全一致的脸型、发型、服装、气质。正面视图展示英俊脸庞和坚定眼神，侧面视图展示挺拔身材和佩剑，背面视图展示白色长袍背部。
{STYLE_SUFFIX}

禁止：卡通化、萌系风格、不同的人物、视图融合、背景元素、文字标注""", "萧凡-turnaround.png"),

    ("青儿", f"""角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：青儿（温柔配角）
外貌：17岁女性，淡绿色长裙，温柔的笑容，眼神柔和，长发及腰，身材纤细，气质温婉。
性格特征：温柔、善良、体贴、对萧凡有好感。
气质要求：温婉柔和，眼神要有温柔和善良感，带着少女的羞涩。
画面要求：三个视图必须是同一个女孩，保持完全一致的脸型、发型、服装、气质。正面视图展示温柔笑容和柔和眼神，侧面视图展示纤细身材和长发，背面视图展示淡绿色长裙背部。
{STYLE_SUFFIX}

禁止：卡通化、萌系风格、不同的人物、视图融合、背景元素、文字标注""", "青儿-turnaround.png"),

    ("戒指老爷爷", f"""角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：戒指老爷爷（神秘配角）
外貌：外表年龄不详，白色长袍，白发白须，仙风道骨，眼神深邃睿智，手持拂尘，飘逸的长袍。
性格特征：睿智、神秘、高深莫测、萧凡的金手指。
气质要求：仙风道骨，眼神要有深邃和睿智感，带着神秘和高深莫测的气质。
画面要求：三个视图必须是同一个老者，保持完全一致的脸型、发型、服装、气质。正面视图展示仙风道骨和深邃眼神，侧面视图展示飘逸长袍和拂尘，背面视图展示白色长袍背部。
{STYLE_SUFFIX}

禁止：卡通化、萌系风格、不同的人物、视图融合、背景元素、文字标注""", "戒指老爷爷-turnaround.png"),
]

# 系统不需要三视图，用单张图
system_prompt = f"""角色概念设计，单张图。

角色：系统（机械界面）
外貌：半透明的蓝色光幕，科技感的界面，显示文字和数据，悬浮在空中，发出淡蓝色光芒。
风格：玄幻短剧风格，科技感与玄幻结合，半透明光效，电影级质感，高饱和度蓝色光芒。

禁止：卡通化、萌系风格、背景元素过多、文字标注"""

print("━━━ 生成重要配角三视图（统一玄幻爽剧风格）━━━\n")
print(f"总计：{len(characters)} 个角色 + 1 个系统界面\n")

success_count = 0

# 生成配角三视图
for name, prompt, output_file in characters:
    if generate_turnaround(name, prompt, output_file):
        success_count += 1

# 生成系统界面
print("生成：系统界面")
print(f"提示词：{system_prompt[:100]}...")

payload = {
    "model": "gpt-4o-image",
    "prompt": system_prompt,
    "n": 1,
    "size": "1024x1024"
}

payload_file = Path("/tmp/system-payload.json")
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
        [str(PROJECT_ROOT / "scripts/api-caller.sh"), "image_gen", "download", url, "系统-interface.png"],
        check=True,
        cwd=IMAGES_DIR
    )

    print(f"✓ 系统-interface.png\n")
    success_count += 1

except Exception as e:
    print(f"✗ 生成失败：{e}\n")

print(f"\n━━━ 完成 ━━━")
print(f"成功：{success_count}/{len(characters) + 1}")

if success_count < len(characters) + 1:
    sys.exit(1)
