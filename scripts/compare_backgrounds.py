#!/usr/bin/env python3
"""
compare_backgrounds.py - 背景相似度比较脚本
用法: python3 scripts/compare_backgrounds.py <prev_frame> <curr_frame>
输出: 相似度分数（0-1）
"""

import sys
import os

def compare_backgrounds(prev_frame_path, curr_frame_path):
    """
    比较两张图片的背景相似度

    注意：这是一个简化实现，实际生产环境应使用：
    - OpenCV 的结构相似性指数（SSIM）
    - 感知哈希（pHash）
    - 或深度学习特征提取
    """

    # 检查文件是否存在
    if not os.path.exists(prev_frame_path):
        print(f"错误: 前一帧不存在: {prev_frame_path}", file=sys.stderr)
        return 0.0

    if not os.path.exists(curr_frame_path):
        print(f"错误: 当前帧不存在: {curr_frame_path}", file=sys.stderr)
        return 0.0

    # 简化实现：返回固定值
    # 实际应使用图像相似度算法

    try:
        # 尝试导入 OpenCV 和 skimage（如果已安装）
        import cv2
        from skimage.metrics import structural_similarity as ssim
        import numpy as np

        # 加载图片
        prev_img = cv2.imread(prev_frame_path)
        curr_img = cv2.imread(curr_frame_path)

        if prev_img is None:
            print(f"错误: 无法读取前一帧", file=sys.stderr)
            return 0.0

        if curr_img is None:
            print(f"错误: 无法读取当前帧", file=sys.stderr)
            return 0.0

        # 调整大小到相同尺寸
        height = min(prev_img.shape[0], curr_img.shape[0])
        width = min(prev_img.shape[1], curr_img.shape[1])

        prev_img = cv2.resize(prev_img, (width, height))
        curr_img = cv2.resize(curr_img, (width, height))

        # 转换为灰度图
        prev_gray = cv2.cvtColor(prev_img, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(curr_img, cv2.COLOR_BGR2GRAY)

        # 计算 SSIM
        similarity = ssim(prev_gray, curr_gray)

        return similarity

    except ImportError:
        # OpenCV 或 skimage 未安装，返回默认值
        print(f"警告: OpenCV 或 skimage 库未安装，返回默认相似度", file=sys.stderr)
        return 0.7
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 0.5

def main():
    if len(sys.argv) != 3:
        print("用法: python3 scripts/compare_backgrounds.py <prev_frame> <curr_frame>", file=sys.stderr)
        sys.exit(1)

    prev_frame = sys.argv[1]
    curr_frame = sys.argv[2]

    similarity = compare_backgrounds(prev_frame, curr_frame)

    # 输出相似度分数
    print(f"{similarity:.2f}")

if __name__ == "__main__":
    main()
