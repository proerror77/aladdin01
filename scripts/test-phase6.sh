#!/usr/bin/env bash
# test-phase6.sh - Phase 6 (Audit & Repair) 测试脚本

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Phase 6 (Audit & Repair) 测试 ==="
echo ""

# 测试环境准备
TEST_EP="ep01"
TEST_SHOT_ID="${TEST_EP}-shot-01"
TEST_SESSION_ID="test-phase6-$(date +%Y%m%d-%H%M%S)"
export TEST_SESSION_ID

echo "1. 检查必要的目录和文件..."

# 创建测试目录
mkdir -p "$PROJECT_ROOT/state/shot-packets"
mkdir -p "$PROJECT_ROOT/state/ontology"
mkdir -p "$PROJECT_ROOT/state/audit"
mkdir -p "$PROJECT_ROOT/outputs/${TEST_EP}/videos"
mkdir -p "$PROJECT_ROOT/outputs/${TEST_EP}/audit"

# 创建测试用的 shot packet
cat > "$PROJECT_ROOT/state/shot-packets/${TEST_SHOT_ID}.json" << 'EOF'
{
  "shot_id": "ep01-shot-01",
  "characters": [
    {
      "id": "苏夜",
      "ref_assets": ["assets/characters/images/苏夜-default.png"],
      "current_state": {
        "costume": "default",
        "injury": "none",
        "emotion": "calm",
        "props_in_possession": []
      }
    }
  ],
  "seedance_inputs": {
    "prompt": "测试提示词",
    "generation_mode": "text2video"
  },
  "audio": ""
}
EOF

# 创建测试用的 world model
cat > "$PROJECT_ROOT/state/ontology/${TEST_EP}-world-model.json" << 'EOF'
{
  "entities": {
    "characters": {
      "苏夜": {
        "personality": "冷静、理智"
      }
    }
  }
}
EOF

# 创建测试用的视频文件（空文件）
touch "$PROJECT_ROOT/outputs/${TEST_EP}/videos/shot-01.mp4"

echo "✓ 测试环境准备完成"
echo ""

echo "2. 测试 qa-agent..."

# 检查 qa-agent 是否存在
if [[ ! -f "$PROJECT_ROOT/.claude/agents/qa-agent.md" ]]; then
  echo "❌ qa-agent.md 不存在"
  exit 1
fi

echo "✓ qa-agent.md 存在"

# 注意：实际执行需要 Claude Code Agent 环境
# 这里只验证文件结构

echo ""
echo "3. 测试 repair-agent..."

# 检查 repair-agent 是否存在
if [[ ! -f "$PROJECT_ROOT/.claude/agents/repair-agent.md" ]]; then
  echo "❌ repair-agent.md 不存在"
  exit 1
fi

echo "✓ repair-agent.md 存在"

echo ""
echo "4. 测试辅助脚本..."

# 检查 compare_faces.py
if [[ ! -f "$PROJECT_ROOT/scripts/compare_faces.py" ]]; then
  echo "❌ compare_faces.py 不存在"
  exit 1
fi

if [[ ! -x "$PROJECT_ROOT/scripts/compare_faces.py" ]]; then
  echo "❌ compare_faces.py 不可执行"
  exit 1
fi

echo "✓ compare_faces.py 存在且可执行"

# 检查 compare_backgrounds.py
if [[ ! -f "$PROJECT_ROOT/scripts/compare_backgrounds.py" ]]; then
  echo "❌ compare_backgrounds.py 不存在"
  exit 1
fi

if [[ ! -x "$PROJECT_ROOT/scripts/compare_backgrounds.py" ]]; then
  echo "❌ compare_backgrounds.py 不可执行"
  exit 1
fi

echo "✓ compare_backgrounds.py 存在且可执行"

echo ""
echo "5. 测试 Python 脚本语法..."

# 测试 compare_faces.py 语法
if python3 -m py_compile "$PROJECT_ROOT/scripts/compare_faces.py" 2>/dev/null; then
  echo "✓ compare_faces.py 语法正确"
else
  echo "❌ compare_faces.py 语法错误"
  exit 1
fi

# 测试 compare_backgrounds.py 语法
if python3 -m py_compile "$PROJECT_ROOT/scripts/compare_backgrounds.py" 2>/dev/null; then
  echo "✓ compare_backgrounds.py 语法正确"
else
  echo "❌ compare_backgrounds.py 语法错误"
  exit 1
fi

echo ""
echo "6. 验证 agent 文档结构..."

# 验证 qa-agent.md 包含必要的章节
if grep -q "## 职责" "$PROJECT_ROOT/.claude/agents/qa-agent.md" && \
   grep -q "## 输入" "$PROJECT_ROOT/.claude/agents/qa-agent.md" && \
   grep -q "## 输出" "$PROJECT_ROOT/.claude/agents/qa-agent.md" && \
   grep -q "## 执行流程" "$PROJECT_ROOT/.claude/agents/qa-agent.md"; then
  echo "✓ qa-agent.md 文档结构完整"
else
  echo "❌ qa-agent.md 文档结构不完整"
  exit 1
fi

# 验证 repair-agent.md 包含必要的章节
if grep -q "## 职责" "$PROJECT_ROOT/.claude/agents/repair-agent.md" && \
   grep -q "## 输入" "$PROJECT_ROOT/.claude/agents/repair-agent.md" && \
   grep -q "## 输出" "$PROJECT_ROOT/.claude/agents/repair-agent.md" && \
   grep -q "## 执行流程" "$PROJECT_ROOT/.claude/agents/repair-agent.md"; then
  echo "✓ repair-agent.md 文档结构完整"
else
  echo "❌ repair-agent.md 文档结构不完整"
  exit 1
fi

echo ""
echo "7. 验证关键功能..."

# 验证 qa-agent 包含 3 种 QA
if grep -q "symbolic_qa" "$PROJECT_ROOT/.claude/agents/qa-agent.md" && \
   grep -q "visual_qa" "$PROJECT_ROOT/.claude/agents/qa-agent.md" && \
   grep -q "semantic_qa" "$PROJECT_ROOT/.claude/agents/qa-agent.md"; then
  echo "✓ qa-agent 包含 3 种 QA"
else
  echo "❌ qa-agent 缺少 QA 类型"
  exit 1
fi

# 验证 repair-agent 包含 3 种修复策略
if grep -q "pass" "$PROJECT_ROOT/.claude/agents/repair-agent.md" && \
   grep -q "local_repair" "$PROJECT_ROOT/.claude/agents/repair-agent.md" && \
   grep -q "regenerate" "$PROJECT_ROOT/.claude/agents/repair-agent.md"; then
  echo "✓ repair-agent 包含 3 种修复策略"
else
  echo "❌ repair-agent 缺少修复策略"
  exit 1
fi

echo ""
echo "=== 测试完成 ==="
echo ""
echo "✓ Phase 6 (Audit & Repair) 实现验证通过"
echo ""
echo "注意事项："
echo "- qa-agent 和 repair-agent 需要在 Claude Code Agent 环境中运行"
echo "- 图像相似度比较需要安装 face_recognition、OpenCV 和 skimage 库"
echo "- 当前实现为简化版，实际生产环境需要完善各功能模块"
echo ""
echo "下一步："
echo "1. 在 ~start 和 ~batch skills 中集成 Phase 6"
echo "2. 测试完整的 E2E 流程"
echo "3. 根据实际效果调整阈值和策略"
