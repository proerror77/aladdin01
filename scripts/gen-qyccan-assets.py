#!/usr/bin/env python3
"""
qyccan 项目全套资产生成脚本
生成角色定妆包（三视图）+ 场景参考图（时间变体）
使用 api-caller.sh image_gen generate / download
"""

import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
API_CALLER = PROJECT_ROOT / "scripts/api-caller.sh"
PACKS_CHARS = PROJECT_ROOT / "assets/packs/characters"
PACKS_SCENES = PROJECT_ROOT / "assets/packs/scenes"
PACKS_PROPS  = PROJECT_ROOT / "assets/packs/props"
PAYLOAD_TMP  = Path("/tmp/qyccan_image_payload.json")

# 确保目录存在
for d in [PACKS_CHARS, PACKS_SCENES, PACKS_PROPS]:
    d.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# 资产定义
# ─────────────────────────────────────────────

CHARACTERS = [
    # (file_stem, prompt_template)
    # 苏夜 - 青玉蚕
    {
        "stem": "suye-qingyucan-front",
        "prompt": "通体碧绿肥嘟嘟的蚕宝宝，拇指大小，肉乎乎小短腿，眼神欠揍，正面视角，白色背景，角色设计稿，全身，照片级写实，无水印，柔和工作室光照",
    },
    {
        "stem": "suye-qingyucan-side",
        "prompt": "通体碧绿肥嘟嘟的蚕宝宝，拇指大小，肉乎乎小短腿，眼神欠揍，侧面视角，白色背景，角色设计稿，全身，照片级写实，无水印，柔和工作室光照",
    },
    {
        "stem": "suye-qingyucan-back",
        "prompt": "通体碧绿肥嘟嘟的蚕宝宝，拇指大小，肉乎乎小短腿，背面视角，白色背景，角色设计稿，全身，照片级写实，无水印，柔和工作室光照",
    },
    # 苏夜 - 碧鳞蛇
    {
        "stem": "suye-bilinse-front",
        "prompt": "筷子长的小蛇，通体碧绿精致鳞片，金色瞳孔，头顶两个小鼓包，正面视角，白色背景，角色设计稿，照片级写实，无水印，柔和工作室光照",
    },
    {
        "stem": "suye-bilinse-side",
        "prompt": "筷子长的小蛇，通体碧绿精致鳞片，金色瞳孔，头顶两个小鼓包，侧面视角，白色背景，角色设计稿，照片级写实，无水印，柔和工作室光照",
    },
    {
        "stem": "suye-bilinse-back",
        "prompt": "筷子长的小蛇，通体碧绿精致鳞片，金色瞳孔，头顶两个小鼓包，背面视角，白色背景，角色设计稿，照片级写实，无水印，柔和工作室光照",
    },
    # 苏夜 - 玄冥黑金蟒
    {
        "stem": "suye-xuanmingmang-front",
        "prompt": "漆黑巨蟒长达三米，头顶两个小鼓包，鳞片镶嵌金色纹路，金色瞳孔，气势威严，正面视角，白色背景，角色设计稿，照片级写实，无水印",
    },
    {
        "stem": "suye-xuanmingmang-side",
        "prompt": "漆黑巨蟒长达三米，头顶两个小鼓包，鳞片镶嵌金色纹路，金色瞳孔，气势威严，侧面视角，白色背景，角色设计稿，照片级写实，无水印",
    },
    {
        "stem": "suye-xuanmingmang-back",
        "prompt": "漆黑巨蟒长达三米，头顶两个小鼓包，鳞片镶嵌金色纹路，金色瞳孔，气势威严，背面视角，白色背景，角色设计稿，照片级写实，无水印",
    },
    # 叶红衣 - 正面
    {
        "stem": "yehongyi-default-front",
        "prompt": "古装美女，18岁，红色衣裙似火，高挑纤细，发髻精致，气质高冷御姐，眼神透着倔强和落寞，长发，正面视角，白色背景，全身，照片级写实，真人实拍质感，35mm胶片",
    },
    {
        "stem": "yehongyi-default-side",
        "prompt": "古装美女，18岁，红色衣裙似火，高挑纤细，发髻精致，气质高冷御姐，长发，侧面视角，白色背景，全身，照片级写实，真人实拍质感，35mm胶片",
    },
    # 萧凡 - 正面
    {
        "stem": "xiaofan-default-front",
        "prompt": "古装青年男子，身穿朴素布衣，眼神坚毅，手指戴古朴黑戒，歪嘴笑，正面视角，白色背景，全身，照片级写实，真人实拍质感",
    },
    # 青儿 - 正面
    {
        "stem": "qinger-default-front",
        "prompt": "古装少女，气质清冷，容貌绝世，温柔气质，正面视角，白色背景，全身，照片级写实，真人实拍质感",
    },
]

SCENES = [
    # 黑雾森林
    {
        "stem": "heiwu-forest-day",
        "prompt": "黑雾弥漫的神秘森林，白天，柔和自然光透过树叶洒下，树木茂密，雾气缭绕，巨大树叶和灌木丛，玄幻修仙风格，电影级构图，无人物，4K超清，16:9宽画面",
    },
    {
        "stem": "heiwu-forest-night",
        "prompt": "黑雾弥漫的神秘森林，夜晚，月光冷冽，阴森神秘，树木茂密，雾气缭绕，幽暗氛围，玄幻修仙风格，电影级构图，无人物，4K超清，16:9宽画面",
    },
    # 叶家大厅
    {
        "stem": "ye-family-hall-day",
        "prompt": "古代豪门议事厅，白天，富丽堂皇，朱红柱子，精致木制梁柱，高大宽敞，阳光从窗户透入，玄幻修仙古风格，电影级构图，无人物，4K超清，16:9宽画面",
    },
    # 叶红衣闺房
    {
        "stem": "yehongyi-room-night",
        "prompt": "古代闺房，夜晚，烛光摇曳，红纱帷幕，简单桌椅床铺，温暖而略带忧郁的氛围，玄幻古风格，电影级构图，无人物，4K超清，16:9宽画面",
    },
    {
        "stem": "yehongyi-room-day",
        "prompt": "古代闺房，白天，简单桌椅床铺，简陋但整洁，自然光线，玄幻古风格，电影级构图，无人物，4K超清，16:9宽画面",
    },
    # 天风学院广场
    {
        "stem": "tianfeng-plaza-day",
        "prompt": "修仙学院广场，白天，宏伟建筑群，飞檐斗拱，阵法光纹地面，修炼气息浓厚，弟子往来其间，玄幻修仙风格，电影级构图，无人物特写，4K超清，16:9宽画面",
    },
    # 擂台
    {
        "stem": "arena-day",
        "prompt": "修仙竞技擂台，白天，高台设计，阵法光纹镶嵌台面，观众席环绕，气势宏大，玄幻修仙风格，电影级构图，无人物特写，4K超清，16:9宽画面",
    },
]


# ─────────────────────────────────────────────
# 生成函数
# ─────────────────────────────────────────────

def check_exists(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 1000


def generate_image(prompt: str, output_path: Path) -> bool:
    """调用 image_gen generate + download，返回成功与否"""
    # 幂等跳过
    if check_exists(output_path):
        print(f"  [skip] {output_path.name} 已存在")
        return True

    payload = {"model": "gpt-4o-image", "prompt": prompt, "n": 1, "size": "1024x1024"}
    PAYLOAD_TMP.write_text(json.dumps(payload, ensure_ascii=False))

    print(f"  [gen ] {output_path.name} ...")
    try:
        result = subprocess.run(
            [str(API_CALLER), "image_gen", "generate", str(PAYLOAD_TMP)],
            capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired:
        print(f"  [FAIL] timeout: {output_path.name}")
        return False

    if result.returncode != 0:
        print(f"  [FAIL] generate stderr: {result.stderr.strip()[:200]}")
        print(f"  [FAIL] generate stdout: {result.stdout.strip()[:200]}")
        return False

    # 解析 URL
    try:
        resp = json.loads(result.stdout)
        image_url = resp["data"][0]["url"]
    except Exception as e:
        print(f"  [FAIL] parse response: {e}  stdout={result.stdout[:300]}")
        return False

    # 下载到 /tmp 中间文件（api-caller 不允许绝对路径输出）
    tmp_out = Path("/tmp/qyccan_dl_tmp.png")
    try:
        dl = subprocess.run(
            [str(API_CALLER), "image_gen", "download", image_url, tmp_out.name],
            capture_output=True, text=True, timeout=60,
            cwd="/tmp"
        )
    except subprocess.TimeoutExpired:
        print(f"  [FAIL] download timeout: {output_path.name}")
        return False

    if dl.returncode != 0:
        print(f"  [FAIL] download stderr: {dl.stderr.strip()[:200]}")
        return False

    if not tmp_out.exists() or tmp_out.stat().st_size == 0:
        print(f"  [FAIL] downloaded file empty: {output_path.name}")
        return False

    # 移动到目标路径
    import shutil
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp_out), str(output_path))
    print(f"  [ OK ] saved → {output_path.relative_to(PROJECT_ROOT)}")
    return True


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    ok = fail = skip = 0

    print("=" * 60)
    print("角色定妆包生成")
    print("=" * 60)
    for item in CHARACTERS:
        out = PACKS_CHARS / f"{item['stem']}.png"
        if check_exists(out):
            print(f"  [skip] {out.name} 已存在")
            skip += 1
            continue
        success = generate_image(item["prompt"], out)
        if success:
            ok += 1
        else:
            fail += 1
        time.sleep(0.5)  # 避免触发速率限制

    print()
    print("=" * 60)
    print("场景参考图生成")
    print("=" * 60)
    for item in SCENES:
        out = PACKS_SCENES / f"{item['stem']}.png"
        if check_exists(out):
            print(f"  [skip] {out.name} 已存在")
            skip += 1
            continue
        success = generate_image(item["prompt"], out)
        if success:
            ok += 1
        else:
            fail += 1
        time.sleep(0.5)

    print()
    print("=" * 60)
    print(f"完成: OK={ok}  FAIL={fail}  SKIP={skip}")
    print("=" * 60)

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
