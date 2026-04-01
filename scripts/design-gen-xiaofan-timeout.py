#!/usr/bin/env python3
"""重新生成萧凡三视图 - 增加超时时间"""

import json
import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "assets/characters/images"

STYLE_SUFFIX = """
玄幻短剧风格，半写实画风，电影级质感，
高饱和度色彩，冷暖对比光影，戏剧化打光，
专业角色概念设计，角色设计稿，
三视图（正面/侧面/背面）水平排列，白色背景，
三个视图必须是同一个角色，保持完全一致
"""

prompt = f"""角色设计三视图，同一角色的正面、侧面、背面三个视角水平排列，白色背景。

角色：萧凡（龙傲天配角）
外貌：18岁男性，白色长袍，英俊的脸庞，眼神坚定正义，剑眉星目，身材挺拔，腰间佩剑，主角光环。
性格特征：正义、自信、天赋异禀、有主角光环但会被苏夜打脸。
气质要求：正派主角气质，眼神要有坚定和正义感，带着自信和天赋的光芒。
画面要求：三个视图必须是同一个人，保持完全一致的脸型、发型、服装、气质。正面视图展示英俊脸庞和坚定眼神，侧面视图展示挺拔身材和佩剑，背面视图展示白色长袍背部。
{STYLE_SUFFIX}

禁止：卡通化、萌系风格、不同的人物、视图融合、背景元素、文字标注"""

print("重新生成：萧凡（增加超时时间到 120 秒）")

payload = {
    "model": "gpt-4o-image",
    "prompt": prompt,
    "n": 1,
    "size": "1792x1024"
}

payload_file = Path("/tmp/xiaofan-timeout-payload.json")
with open(payload_file, 'w') as f:
    json.dump(payload, f)

try:
    # 设置环境变量增加超时时间
    env = os.environ.copy()
    env['IMAGE_GEN_MAX_TIME'] = '120'

    result = subprocess.run(
        [str(PROJECT_ROOT / "scripts/api-caller.sh"), "image_gen", "generate", str(payload_file)],
        capture_output=True,
        text=True,
        check=True,
        cwd=PROJECT_ROOT,
        env=env,
        timeout=150
    )

    response = json.loads(result.stdout)
    url = response['data'][0]['url']

    subprocess.run(
        [str(PROJECT_ROOT / "scripts/api-caller.sh"), "image_gen", "download", url, "萧凡-turnaround.png"],
        check=True,
        cwd=IMAGES_DIR,
        timeout=60
    )

    print("✓ 萧凡-turnaround.png")

except subprocess.TimeoutExpired:
    print("✗ 生成失败：请求超时（即使 120 秒也不够）")
    sys.exit(1)
except Exception as e:
    print(f"✗ 生成失败：{e}")
    sys.exit(1)
