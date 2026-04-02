#!/usr/bin/env python3
"""重新生成萧凡三视图 - 简化提示词"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "assets/characters/images"

# 简化提示词，减少长度
prompt = """角色设计三视图，正面/侧面/背面水平排列，白色背景。

萧凡，18岁男性，白色长袍，英俊脸庞，剑眉星目，腰间佩剑，正义坚定的眼神，挺拔身材，主角光环。

玄幻短剧风格，半写实画风，电影级质感，高饱和度色彩，专业角色设计稿，三个视图必须是同一个人。

禁止：卡通化、不同人物、视图融合、背景元素"""

print("重新生成：萧凡（简化提示词）")

payload = {
    "model": "gpt-4o-image",
    "prompt": prompt,
    "n": 1,
    "size": "1792x1024"
}

payload_file = Path("/tmp/xiaofan-simple-payload.json")
with open(payload_file, 'w') as f:
    json.dump(payload, f)

try:
    result = subprocess.run(
        [str(PROJECT_ROOT / "scripts/api-caller.sh"), "image_gen", "generate", str(payload_file)],
        capture_output=True,
        text=True,
        check=True,
        cwd=PROJECT_ROOT,
        timeout=90
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
    print("✗ 生成失败：请求超时")
    sys.exit(1)
except Exception as e:
    print(f"✗ 生成失败：{e}")
    sys.exit(1)
