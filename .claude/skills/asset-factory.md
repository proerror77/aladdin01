---
name: asset-factory
description: 资产工厂。调用 Nanobanana 生成角色定妆包、场景 styleframe、道具包。在 ~build-ontology 之后、~batch 之前运行。
user_invocable: true
---

# ~asset-factory — 资产工厂（角色定妆包 + 场景 styleframe + 道具包）

在 `~build-ontology` 之后、`~batch` 之前运行。读取所有角色档案、场景档案和本体模型，生成完整的资产包。

## 使用方式

```bash
~asset-factory                 # 全量生成
~asset-factory --incremental   # 增量生成（跳过已存在的）
~asset-factory --characters    # 只生成角色定妆包
~asset-factory --scenes        # 只生成场景 styleframe
~asset-factory --props         # 只生成道具包
```

## 执行流程

### 1. 环境检查

检查必需的环境变量和依赖：

```bash
# 检查 TUZI_API_KEY
if [[ -z "$TUZI_API_KEY" ]]; then
    echo "错误: TUZI_API_KEY 未设置"
    exit 1
fi

# 检查依赖
for cmd in yq jq curl; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "错误: 缺少依赖 $cmd"
        exit 1
    fi
done

# 检查配置文件
if [[ ! -f "config/nanobanana/nanobanana-config.yaml" ]]; then
    echo "错误: 配置文件不存在"
    exit 1
fi
```

### 2. 生成角色定妆包

对每个角色的每个变体生成定妆包（front/side/back 视图 + 表情包）：

```bash
# 读取所有角色档案
for profile in assets/characters/profiles/*.yaml; do
    character_name=$(yq eval '.name' "$profile")
    
    # 检查是否有 variants
    if yq eval '.variants' "$profile" | grep -q "variant_id"; then
        # 多变体角色
        variants=$(yq eval '.variants[].variant_id' "$profile")
        for variant in $variants; do
            appearance=$(yq eval ".variants[] | select(.variant_id == \"$variant\") | .appearance" "$profile")
            
            # 调用 nanobanana-caller.sh 生成定妆包
            ./scripts/nanobanana-caller.sh character-pack \
                "$character_name" \
                "$variant" \
                "$appearance"
        done
    else
        # 单变体角色
        appearance=$(yq eval '.appearance' "$profile")
        
        ./scripts/nanobanana-caller.sh character-pack \
            "$character_name" \
            "default" \
            "$appearance"
    fi
done
```

**生成内容**：
- `assets/packs/characters/{角色名}-{variant}-front.png` - 正面视图
- `assets/packs/characters/{角色名}-{variant}-side.png` - 侧面视图
- `assets/packs/characters/{角色名}-{variant}-back.png` - 背面视图
- `assets/packs/characters/{角色名}-{variant}-neutral.png` - 中性表情
- `assets/packs/characters/{角色名}-{variant}-happy.png` - 开心表情
- `assets/packs/characters/{角色名}-{variant}-angry.png` - 愤怒表情
- `assets/packs/characters/{角色名}-{variant}-sad.png` - 悲伤表情
- `assets/packs/characters/{角色名}-{variant}-surprised.png` - 惊讶表情

### 3. 生成场景 styleframe

对每个场景的每个时段生成 styleframe：

```bash
# 读取所有场景档案
for profile in assets/scenes/profiles/*.yaml; do
    scene_name=$(yq eval '.name' "$profile")
    description=$(yq eval '.description' "$profile")
    
    # 获取时段变体
    time_variants=$(yq eval '.time_variants[]' "$profile" 2>/dev/null || echo "day night")
    
    for time_of_day in $time_variants; do
        # 获取光线描述
        lighting=$(yq eval ".lighting.${time_of_day}" "$profile" 2>/dev/null || echo "自然光")
        
        # 调用 nanobanana-caller.sh 生成 styleframe
        ./scripts/nanobanana-caller.sh scene-styleframe \
            "$scene_name" \
            "$time_of_day" \
            "$description" \
            "$lighting"
    done
done
```

**生成内容**：
- `assets/packs/scenes/{场景名}-day-styleframe.png` - 白天
- `assets/packs/scenes/{场景名}-night-styleframe.png` - 夜晚
- `assets/packs/scenes/{场景名}-dusk-styleframe.png` - 黄昏
- `assets/packs/scenes/{场景名}-dawn-styleframe.png` - 清晨

### 4. 生成道具包

从本体模型中提取关键道具，生成不同状态的道具图：

```bash
# 如果有本体模型，从中提取道具
for world_model in state/ontology/*-world-model.json; do
    if [[ -f "$world_model" ]]; then
        props=$(jq -r '.entities.props | keys[]' "$world_model" 2>/dev/null || echo "")
        
        for prop_name in $props; do
            description=$(jq -r ".entities.props.\"${prop_name}\".description" "$world_model")
            
            # 生成不同状态的道具
            for condition in intact damaged; do
                ./scripts/nanobanana-caller.sh prop-pack \
                    "$prop_name" \
                    "$description" \
                    "$condition"
            done
        done
    fi
done
```

**生成内容**：
- `assets/packs/props/{道具名}-intact.png` - 完好无损
- `assets/packs/props/{道具名}-damaged.png` - 破损
- `assets/packs/props/{道具名}-destroyed.png` - 毁坏

### 5. 生成资产清单

创建资产清单文件，记录所有生成的资产：

```bash
cat > assets/packs/asset-manifest.json << EOF
{
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "characters": $(find assets/packs/characters -name "*.png" 2>/dev/null | jq -R -s -c 'split("\n")[:-1]' || echo "[]"),
  "scenes": $(find assets/packs/scenes -name "*.png" 2>/dev/null | jq -R -s -c 'split("\n")[:-1]' || echo "[]"),
  "props": $(find assets/packs/props -name "*.png" 2>/dev/null | jq -R -s -c 'split("\n")[:-1]' || echo "[]")
}
EOF
```

### 6. 验证生成结果

统计生成的资产数量：

```bash
character_count=$(find assets/packs/characters -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
scene_count=$(find assets/packs/scenes -name "*.png" 2>/dev/null | wc -l | tr -d ' ')
prop_count=$(find assets/packs/props -name "*.png" 2>/dev/null | wc -l | tr -d ' ')

echo "━━━ 资产生成完成 ━━━"
echo "角色定妆包: $character_count 张"
echo "场景 styleframe: $scene_count 张"
echo "道具包: $prop_count 张"
echo "总计: $((character_count + scene_count + prop_count)) 张"
```

## 幂等性保证

所有生成函数在生成前检查目标文件是否已存在：
- 文件已存在 → 跳过生成，输出 `Skipping existing file: {path}`
- 文件不存在 → 调用 API 生成

即使多次运行 `~asset-factory`，已生成的资产也不会被覆盖。

## 增量模式

使用 `--incremental` 参数时，只生成缺失的资产：

```bash
~asset-factory --incremental
```

这在以下场景很有用：
- 新增角色/场景后补充生成
- 生成过程中断后继续
- 部分资产损坏需要重新生成

## 错误处理

- 单个资产生成失败不影响其他资产
- 失败的资产会记录到 `state/asset-factory-errors.log`
- 最终报告会列出失败的资产清单

## 成本控制

每次生成会记录 API 调用次数和预估成本：

```bash
echo "━━━ 成本统计 ━━━"
echo "API 调用次数: $api_call_count"
echo "预估成本: $estimated_cost USD"
```

## 注意事项

- **API Rate Limit**：Nanobanana API 有速率限制，大量生成时注意控制并发
- **存储空间**：每张图约 2-5MB，100 个角色 × 8 张图 = 约 1.6-4GB
- **生成时间**：每张图约 10-30 秒，100 个角色 × 8 张图 = 约 13-40 分钟
- **幂等性**：可安全重复运行，已存在的文件不会被覆盖

## 与 ~design 的区别

| 功能 | ~design | ~asset-factory |
|------|---------|----------------|
| 用途 | 生成参考图（用于视频生成） | 生成资产包（用于 img2video） |
| 输出格式 | 单张参考图 | 多角度定妆包 + 表情包 |
| 审核流程 | 主角迭代审核 + 配角标准审核 | 自动生成，无审核 |
| 存储位置 | `assets/characters/images/` | `assets/packs/characters/` |
| 使用场景 | Phase 3 美术校验 | Phase 3.5 Shot Packet 编译 |

## 完成后

输出摘要：

```
━━━ 资产工厂完成 ━━━

角色定妆包: 120 张（15 个角色 × 8 张）
场景 styleframe: 24 张（12 个场景 × 2 时段）
道具包: 10 张（5 个道具 × 2 状态）

总计: 154 张
API 调用次数: 154
预估成本: $15.40 USD

资产清单: assets/packs/asset-manifest.json
```

写入状态文件 `state/asset-factory-status.json`：

```json
{
  "status": "completed",
  "started_at": "2026-04-01T10:00:00Z",
  "completed_at": "2026-04-01T10:45:00Z",
  "data": {
    "characters": 120,
    "scenes": 24,
    "props": 10,
    "total": 154,
    "api_calls": 154,
    "estimated_cost_usd": 15.40
  }
}
```
