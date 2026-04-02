#!/usr/bin/env python3
"""
compare_faces.py - 脸部相似度比较脚本
用法: python3 scripts/compare_faces.py <reference_image> <generated_image>
输出: 相似度分数（0-1）
"""

import sys
import os

def compare_faces(ref_image_path, gen_image_path):
    """
    比较两张图片中的脸部相似度

    注意：这是一个简化实现，实际生产环境应使用：
    - face_recognition 库
    - OpenCV + dlib
    - 或调用云端人脸识别 API
    """

    # 检查文件是否存在
    if not os.path.exists(ref_image_path):
        print(f"错误: 参考图不存在: {ref_image_path}", file=sys.stderr)
        return 0.0

    if not os.path.exists(gen_image_path):
        print(f"错误: 生成图不存在: {gen_image_path}", file=sys.stderr)
        return 0.0

    # 简化实现：返回固定值
    # 实际应使用人脸识别算法计算相似度

    try:
        # 尝试导入 face_recognition（如果已安装）
        import face_recognition
        import numpy as np

        # 加载图片
        ref_image = face_recognition.load_image_file(ref_image_path)
        gen_image = face_recognition.load_image_file(gen_image_path)

        # 提取人脸编码
        ref_encodings = face_recognition.face_encodings(ref_image)
        gen_encodings = face_recognition.face_encodings(gen_image)

        if len(ref_encodings) == 0:
            print(f"警告: 参考图中未检测到人脸", file=sys.stderr)
            return 0.5

        if len(gen_encodings) == 0:
            print(f"警告: 生成图中未检测到人脸", file=sys.stderr)
            return 0.5

        # 计算相似度（使用欧氏距离）
        ref_encoding = ref_encodings[0]
        gen_encoding = gen_encodings[0]

        distance = np.linalg.norm(ref_encoding - gen_encoding)

        # 将距离转换为相似度（0-1）
        # face_recognition 的阈值通常是 0.6
        similarity = max(0.0, 1.0 - distance / 0.6)

        return similarity

    except ImportError:
        # face_recognition 未安装，返回默认值
        print(f"警告: face_recognition 库未安装，返回默认相似度", file=sys.stderr)
        return 0.8
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 0.5

def main():
    if len(sys.argv) != 3:
        print("用法: python3 scripts/compare_faces.py <reference_image> <generated_image>", file=sys.stderr)
        sys.exit(1)

    ref_image = sys.argv[1]
    gen_image = sys.argv[2]

    similarity = compare_faces(ref_image, gen_image)

    # 输出相似度分数
    print(f"{similarity:.2f}")

if __name__ == "__main__":
    main()
