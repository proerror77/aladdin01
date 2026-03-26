#!/usr/bin/env bash
# concat-episode.sh — 将镜次视频拼接为完整集数
# 用法：./scripts/concat-episode.sh <ep_id>
# 示例：./scripts/concat-episode.sh ep01

set -euo pipefail

EP="${1:-}"
if [[ -z "$EP" ]]; then
  echo "Usage: $0 <ep_id>  (e.g. ep01)" >&2
  exit 1
fi

VIDEOS_DIR="outputs/${EP}/videos"
NORMALIZED_DIR="${VIDEOS_DIR}/normalized"
OUTPUT="outputs/${EP}/${EP}-final.mp4"

if [[ ! -d "$VIDEOS_DIR" ]]; then
  echo "ERROR: $VIDEOS_DIR not found" >&2
  exit 1
fi

echo "=== 拼接 ${EP} ==="

# Step 1: 补静音轨（无音轨的镜次补 AAC 静音，避免拼接时音频丢失）
mkdir -p "$NORMALIZED_DIR"
for f in "${VIDEOS_DIR}/${EP}"-shot-*.mp4; do
  fname=$(basename "$f")
  has_audio=$(ffprobe -v quiet -show_streams -select_streams a "$f" | grep -c "codec_name" || true)
  if [[ "$has_audio" -eq 0 ]]; then
    ffmpeg -i "$f" -f lavfi -i anullsrc=r=44100:cl=stereo \
      -c:v copy -c:a aac -shortest \
      "${NORMALIZED_DIR}/${fname}" -y 2>/dev/null
    echo "  补音轨: $fname"
  else
    cp "$f" "${NORMALIZED_DIR}/${fname}"
    echo "  保留:   $fname"
  fi
done

# Step 2: 生成拼接列表（使用绝对路径，避免 ffmpeg 路径解析歧义）
CONCAT_LIST="${NORMALIZED_DIR}/concat.txt"
ls "${NORMALIZED_DIR}/${EP}"-shot-*.mp4 | sort | while read -r f; do
  echo "file '$(realpath "$f")'"
done > "$CONCAT_LIST"

# Step 3: 拼接
echo ""
echo "拼接中..."
ffmpeg -f concat -safe 0 -i "$CONCAT_LIST" -c copy "$OUTPUT" -y 2>&1 | tail -2

# Step 4: 验证
duration=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$OUTPUT")
size=$(du -sh "$OUTPUT" | cut -f1)
has_audio=$(ffprobe -v quiet -show_streams -select_streams a "$OUTPUT" | grep -c "codec_name" || true)

echo ""
echo "=== 完成 ==="
echo "  文件：$OUTPUT"
echo "  大小：$size"
printf "  时长：%.1f 秒\n" "$duration"
echo "  音频：$([ "$has_audio" -gt 0 ] && echo '✅ 有' || echo '❌ 无')"

# 清理临时文件
rm -rf "$NORMALIZED_DIR"
