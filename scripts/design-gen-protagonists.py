#!/usr/bin/env python3
"""快速生成主角参考图（苏夜 3 变体 + 叶红衣）"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "assets/characters/images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def generate_image(name, prompt, output_file):
    """生成单张图片"""
    output_path = IMAGES_DIR / output_file

    if output_path.exists():
        print(f"⊙ {output_file} 已存在，跳过")
        return True

    print(f"生成：{name}")

    # 创建 payload
    payload = {
        "model": "gpt-4o-image",
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024"
    }

    payload_file = Path("/tmp/image-gen-payload.json")
    with open(payload_file, 'w') as f:
        json.dump(payload, f)

    # 调用 API
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

        # 下载图片
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

# 主角参考图列表
protagonists = [
    # 苏夜 - 青玉蚕
    ("苏夜-青玉蚕-正面", "Character design: Su Ye (Green Jade Silkworm). A chubby, bright green silkworm, thumb-sized, with mischievous eyes and a slightly smug expression. Front view, white background, professional character concept art.", "苏夜-qingyucan-front.png"),
    ("苏夜-青玉蚕-侧面", "Character design: Su Ye (Green Jade Silkworm). A chubby, bright green silkworm, thumb-sized. Side view, white background, professional character concept art.", "苏夜-qingyucan-side.png"),
    ("苏夜-青玉蚕-背面", "Character design: Su Ye (Green Jade Silkworm). A chubby, bright green silkworm, thumb-sized. Back view, white background, professional character concept art.", "苏夜-qingyucan-back.png"),

    # 苏夜 - 碧鳞蛇
    ("苏夜-碧鳞蛇-正面", "Character design: Su Ye (Emerald Scale Snake). A chopstick-length snake with exquisite emerald green scales, golden pupils, forked tongue. Front view, white background, professional character concept art.", "苏夜-bilinse-front.png"),
    ("苏夜-碧鳞蛇-侧面", "Character design: Su Ye (Emerald Scale Snake). A chopstick-length snake with emerald green scales, golden pupils. Side view, white background, professional character concept art.", "苏夜-bilinse-side.png"),
    ("苏夜-碧鳞蛇-背面", "Character design: Su Ye (Emerald Scale Snake). A chopstick-length snake with emerald green scales. Back view, white background, professional character concept art.", "苏夜-bilinse-back.png"),

    # 苏夜 - 玄冥蟒
    ("苏夜-玄冥蟒-正面", "Character design: Su Ye (Xuanming Python). A three-meter-long python with jet-black scales with golden sheen, golden pupils, two small bumps on head. Front view, white background, professional character concept art.", "苏夜-xuanmingmang-front.png"),
    ("苏夜-玄冥蟒-侧面", "Character design: Su Ye (Xuanming Python). A three-meter-long python with jet-black scales, golden pupils, two small bumps on head. Side view, white background, professional character concept art.", "苏夜-xuanmingmang-side.png"),
    ("苏夜-玄冥蟒-背面", "Character design: Su Ye (Xuanming Python). A three-meter-long python with jet-black scales. Back view, white background, professional character concept art.", "苏夜-xuanmingmang-back.png"),

    # 叶红衣
    ("叶红衣-正面", "Character design: Ye Hongyi. An 18-year-old Chinese girl in red robes, cold and elegant face with stubborn eyes showing loneliness, long hair, delicate collarbone, martial arts style. Front view, white background, professional character concept art.", "叶红衣-front.png"),
    ("叶红衣-侧面", "Character design: Ye Hongyi. An 18-year-old Chinese girl in red robes, cold and elegant, long hair, martial arts style. Side view, white background, professional character concept art.", "叶红衣-side.png"),
    ("叶红衣-背面", "Character design: Ye Hongyi. An 18-year-old Chinese girl in red robes, long hair flowing, martial arts style. Back view, white background, professional character concept art.", "叶红衣-back.png"),
]

print("━━━ 开始生成主角参考图 ━━━\n")
print(f"总计：{len(protagonists)} 张图片\n")

success_count = 0
for name, prompt, output_file in protagonists:
    if generate_image(name, prompt, output_file):
        success_count += 1
    print()

print(f"\n━━━ 完成 ━━━")
print(f"成功：{success_count}/{len(protagonists)}")

if success_count < len(protagonists):
    sys.exit(1)
