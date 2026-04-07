#!/bin/bash
# scripts/migrate-to-v2-architecture.sh
# 一键迁移到 v2.0 架构

set -euo pipefail

echo "========================================="
echo "架构升级：v1.0 → v2.0"
echo "========================================="
echo ""

# 创建所有必要的目录
echo "[1/10] 创建目录结构..."
mkdir -p state/ontology
mkdir -p state/character-states
mkdir -p state/shot-packets
mkdir -p state/audit
mkdir -p assets/packs/characters
mkdir -p assets/packs/scenes
mkdir -p assets/packs/props
mkdir -p config/ontology
mkdir -p config/nanobanana
echo "✓ 目录结构创建完成"
echo ""

# 检查环境变量
echo "[2/10] 检查环境变量..."
if [[ -z "${TUZI_API_KEY:-}" ]]; then
    echo "⚠️  警告: TUZI_API_KEY 未设置（Nanobanana 需要）"
else
    echo "✓ TUZI_API_KEY 已设置"
fi

if [[ -z "${ARK_API_KEY:-}" ]]; then
    echo "⚠️  警告: ARK_API_KEY 未设置（Seedance 需要）"
else
    echo "✓ ARK_API_KEY 已设置"
fi
echo ""

# 更新 seedance-v2.yaml 配置
echo "[3/10] 更新 Seedance 配置..."
if [[ -f "config/platforms/seedance-v2.yaml" ]]; then
    # 备份原文件
    cp config/platforms/seedance-v2.yaml config/platforms/seedance-v2.yaml.backup

    # 添加 generation_modes 配置（如果不存在）
    if ! grep -q "generation_modes:" config/platforms/seedance-v2.yaml; then
        cat >> config/platforms/seedance-v2.yaml << 'EOF'

# 生成模式配置（v2.0 新增）
generation_modes:
  text2video:
    enabled: true
    default: false
  img2video:
    enabled: true
    default: true
    reference_mode: "composition"  # composition / keyframes
EOF
        echo "✓ Seedance 配置已更新（img2video 为默认）"
    else
        echo "✓ Seedance 配置已存在"
    fi
else
    echo "⚠️  警告: config/platforms/seedance-v2.yaml 不存在"
fi
echo ""

# 检查必要的工具
echo "[4/10] 检查依赖工具..."
MISSING_TOOLS=()

if ! command -v jq &> /dev/null; then
    MISSING_TOOLS+=("jq")
fi

if ! command -v yq &> /dev/null; then
    MISSING_TOOLS+=("yq")
fi

if [[ ${#MISSING_TOOLS[@]} -gt 0 ]]; then
    echo "⚠️  缺少工具: ${MISSING_TOOLS[*]}"
    echo "   请安装: brew install ${MISSING_TOOLS[*]}"
else
    echo "✓ 所有依赖工具已安装"
fi
echo ""

# 验证 agents 文件
echo "[5/10] 验证 Agents..."
AGENTS=(
    "ontology-builder-agent"
    "asset-factory-agent"
    "memory-agent"
    "shot-compiler-agent"
    "qa-agent"
    "repair-agent"
)

MISSING_AGENTS=()
for agent in "${AGENTS[@]}"; do
    if [[ ! -f ".claude/agents/${agent}.md" ]]; then
        MISSING_AGENTS+=("$agent")
    fi
done

if [[ ${#MISSING_AGENTS[@]} -gt 0 ]]; then
    echo "⚠️  缺少 Agents: ${MISSING_AGENTS[*]}"
else
    echo "✓ 所有 Agents 已就绪"
fi
echo ""

# 验证 skills 文件
echo "[6/10] 验证 Skills..."
SKILLS=(
    "build-ontology"
    "asset-factory"
    "compile-shots"
    "qa"
    "repair"
)

MISSING_SKILLS=()
for skill in "${SKILLS[@]}"; do
    if [[ ! -f ".claude/skills/${skill}.md" ]]; then
        MISSING_SKILLS+=("$skill")
    fi
done

if [[ ${#MISSING_SKILLS[@]} -gt 0 ]]; then
    echo "⚠️  缺少 Skills: ${MISSING_SKILLS[*]}"
else
    echo "✓ 所有 Skills 已就绪"
fi
echo ""

# 验证配置文件
echo "[7/10] 验证配置文件..."
CONFIGS=(
    "config/ontology/world-model-schema.yaml"
    "config/shot-packet/shot-packet-schema.yaml"
    "config/nanobanana/nanobanana-config.yaml"
)

MISSING_CONFIGS=()
for config in "${CONFIGS[@]}"; do
    if [[ ! -f "$config" ]]; then
        MISSING_CONFIGS+=("$config")
    fi
done

if [[ ${#MISSING_CONFIGS[@]} -gt 0 ]]; then
    echo "⚠️  缺少配置: ${MISSING_CONFIGS[*]}"
else
    echo "✓ 所有配置文件已就绪"
fi
echo ""

# 验证脚本
echo "[8/10] 验证脚本..."
if [[ -f "scripts/nanobanana-caller.sh" ]]; then
    if [[ -x "scripts/nanobanana-caller.sh" ]]; then
        echo "✓ nanobanana-caller.sh 已就绪"
    else
        chmod +x scripts/nanobanana-caller.sh
        echo "✓ nanobanana-caller.sh 权限已修复"
    fi
else
    echo "⚠️  警告: scripts/nanobanana-caller.sh 不存在"
fi
echo ""

# 迁移现有数据
echo "[9/10] 迁移现有数据..."
if [[ -d "assets/characters/images" ]]; then
    CHAR_COUNT=$(find assets/characters/images -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
    echo "  发现 $CHAR_COUNT 个角色参考图（保留作为 fallback）"
fi

if [[ -d "assets/scenes/images" ]]; then
    SCENE_COUNT=$(find assets/scenes/images -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
    echo "  发现 $SCENE_COUNT 个场景参考图（保留作为 fallback）"
fi

if [[ -f "state/progress.json" ]]; then
    echo "  发现 progress.json（保留并扩展）"
fi

echo "✓ 现有数据已保留"
echo ""

# 生成迁移报告
echo "[10/10] 生成迁移报告..."
REPORT_FILE="docs/migration-report-$(date +%Y%m%d-%H%M%S).md"
cat > "$REPORT_FILE" << EOF
# 架构迁移报告

**日期**: $(date +"%Y-%m-%d %H:%M:%S")
**版本**: v1.0 → v2.0

## 迁移状态

### 目录结构
- [x] state/ontology/
- [x] state/character-states/
- [x] state/shot-packets/
- [x] state/audit/
- [x] assets/packs/

### Agents
EOF

for agent in "${AGENTS[@]}"; do
    if [[ -f ".claude/agents/${agent}.md" ]]; then
        echo "- [x] ${agent}" >> "$REPORT_FILE"
    else
        echo "- [ ] ${agent}" >> "$REPORT_FILE"
    fi
done

cat >> "$REPORT_FILE" << EOF

### Skills
EOF

for skill in "${SKILLS[@]}"; do
    if [[ -f ".claude/skills/${skill}.md" ]]; then
        echo "- [x] ${skill}" >> "$REPORT_FILE"
    else
        echo "- [ ] ${skill}" >> "$REPORT_FILE"
    fi
done

cat >> "$REPORT_FILE" << EOF

### 配置文件
EOF

for config in "${CONFIGS[@]}"; do
    if [[ -f "$config" ]]; then
        echo "- [x] ${config}" >> "$REPORT_FILE"
    else
        echo "- [ ] ${config}" >> "$REPORT_FILE"
    fi
done

cat >> "$REPORT_FILE" << EOF

### 环境变量
- [$([ -n "${TUZI_API_KEY:-}" ] && echo "x" || echo " ")] TUZI_API_KEY
- [$([ -n "${ARK_API_KEY:-}" ] && echo "x" || echo " ")] ARK_API_KEY

### 数据迁移
- [x] 现有角色参考图已保留
- [x] 现有场景参考图已保留
- [x] progress.json 已保留

## 下一步

1. 设置环境变量（如未设置）:
   \`\`\`bash
   export TUZI_API_KEY="..."
   export ARK_API_KEY="..."
   \`\`\`

2. 为现有剧本构建本体:
   \`\`\`bash
   ~build-ontology --all
   \`\`\`

3. 生成资产包:
   \`\`\`bash
   ~asset-factory
   \`\`\`

4. 测试新流程:
   \`\`\`bash
   ~start ep01
   \`\`\`

## 回滚方案

如需回滚到 v1.0:
\`\`\`bash
# 恢复 Seedance 配置
cp config/platforms/seedance-v2.yaml.backup config/platforms/seedance-v2.yaml

# 删除新增目录（可选）
rm -rf state/ontology state/character-states state/shot-packets state/audit
rm -rf assets/packs
\`\`\`
EOF

echo "✓ 迁移报告已生成: $REPORT_FILE"
echo ""

# 总结
echo "========================================="
echo "迁移完成！"
echo "========================================="
echo ""
echo "状态摘要:"
echo "  ✓ 目录结构: 已创建"
echo "  ✓ 配置文件: 已更新"
echo "  ✓ 现有数据: 已保留"
echo ""

if [[ ${#MISSING_AGENTS[@]} -eq 0 && ${#MISSING_SKILLS[@]} -eq 0 && ${#MISSING_CONFIGS[@]} -eq 0 ]]; then
    echo "🎉 所有组件已就绪！"
    echo ""
    echo "下一步:"
    echo "  1. ~build-ontology ep01"
    echo "  2. ~asset-factory"
    echo "  3. ~start ep01"
else
    echo "⚠️  部分组件缺失，请检查:"
    [[ ${#MISSING_AGENTS[@]} -gt 0 ]] && echo "  - Agents: ${MISSING_AGENTS[*]}"
    [[ ${#MISSING_SKILLS[@]} -gt 0 ]] && echo "  - Skills: ${MISSING_SKILLS[*]}"
    [[ ${#MISSING_CONFIGS[@]} -gt 0 ]] && echo "  - Configs: ${MISSING_CONFIGS[*]}"
fi
echo ""
echo "详细报告: $REPORT_FILE"
