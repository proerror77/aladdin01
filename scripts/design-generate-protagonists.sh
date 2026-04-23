#!/bin/bash
# 生成主角参考图（苏夜 3 变体 + 叶红衣 1 变体）

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p assets/characters/images

echo "━━━ 开始生成主角参考图 ━━━"
echo ""

# 苏夜 - 青玉蚕形态
echo "生成：苏夜 - 青玉蚕形态（三视图）"
cat > /tmp/suye-qingyucan-front.json << 'EOF'
{
  "model": "gpt-image-2",
  "prompt": "Character design: Su Ye (Green Jade Silkworm form). A chubby, bright green silkworm with mischievous eyes, thumb-sized, cute but with a slightly smug expression. Front view, white background, professional character concept art, clear features, uniform lighting.",
  "n": 1,
  "size": "1:1"
}
EOF

if [ ! -f "assets/characters/images/苏夜-qingyucan-front.png" ]; then
  URL=$(./scripts/api-caller.sh image_gen generate /tmp/suye-qingyucan-front.json | jq -r '.data[0].url')
  ./scripts/api-caller.sh image_gen download "$URL" "苏夜-qingyucan-front.png"
  mv "苏夜-qingyucan-front.png" assets/characters/images/
  echo "✓ 苏夜-qingyucan-front.png"
else
  echo "⊙ 已存在，跳过"
fi

cat > /tmp/suye-qingyucan-side.json << 'EOF'
{
  "model": "gpt-image-2",
  "prompt": "Character design: Su Ye (Green Jade Silkworm form). A chubby, bright green silkworm with mischievous eyes, thumb-sized. Side view, white background, professional character concept art, clear features, uniform lighting.",
  "n": 1,
  "size": "1:1"
}
EOF

if [ ! -f "assets/characters/images/苏夜-qingyucan-side.png" ]; then
  URL=$(./scripts/api-caller.sh image_gen generate /tmp/suye-qingyucan-side.json | jq -r '.data[0].url')
  ./scripts/api-caller.sh image_gen download "$URL" "苏夜-qingyucan-side.png"
  mv "苏夜-qingyucan-side.png" assets/characters/images/
  echo "✓ 苏夜-qingyucan-side.png"
else
  echo "⊙ 已存在，跳过"
fi

cat > /tmp/suye-qingyucan-back.json << 'EOF'
{
  "model": "gpt-image-2",
  "prompt": "Character design: Su Ye (Green Jade Silkworm form). A chubby, bright green silkworm with mischievous eyes, thumb-sized. Back view, white background, professional character concept art, clear features, uniform lighting.",
  "n": 1,
  "size": "1:1"
}
EOF

if [ ! -f "assets/characters/images/苏夜-qingyucan-back.png" ]; then
  URL=$(./scripts/api-caller.sh image_gen generate /tmp/suye-qingyucan-back.json | jq -r '.data[0].url')
  ./scripts/api-caller.sh image_gen download "$URL" "苏夜-qingyucan-back.png"
  mv "苏夜-qingyucan-back.png" assets/characters/images/
  echo "✓ 苏夜-qingyucan-back.png"
else
  echo "⊙ 已存在，跳过"
fi

echo ""

# 苏夜 - 碧鳞蛇形态
echo "生成：苏夜 - 碧鳞蛇形态（三视图）"
cat > /tmp/suye-bilinse-front.json << 'EOF'
{
  "model": "gpt-image-2",
  "prompt": "Character design: Su Ye (Emerald Scale Snake form). A chopstick-length snake covered in exquisite emerald green scales, golden pupils, forked tongue visible, elegant and slightly menacing. Front view, white background, professional character concept art, clear features, uniform lighting.",
  "n": 1,
  "size": "1:1"
}
EOF

if [ ! -f "assets/characters/images/苏夜-bilinse-front.png" ]; then
  URL=$(./scripts/api-caller.sh image_gen generate /tmp/suye-bilinse-front.json | jq -r '.data[0].url')
  ./scripts/api-caller.sh image_gen download "$URL" "苏夜-bilinse-front.png"
  mv "苏夜-bilinse-front.png" assets/characters/images/
  echo "✓ 苏夜-bilinse-front.png"
else
  echo "⊙ 已存在，跳过"
fi

# ... 继续其他视图
