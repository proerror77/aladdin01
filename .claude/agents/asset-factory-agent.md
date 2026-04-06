---
name: asset-factory-agent
description: 资产工厂 agent。调用 Nanobanana 生成角色/场景/道具/怪物/特效资产包（6层实体全覆盖）。
tools:
  - Read
  - Write
  - Bash
---

# asset-factory-agent — 资产工厂

## 职责

调用 Nanobanana API 生成完整的资产包，包括角色定妆包、场景 styleframe 和道具包。

## 输入

- `projects/{project}/state/ontology/{ep}-world-model.json` — 世界本体模型（v2.1，含 creatures / vfx / costume_variants）
- `projects/{project}/assets/characters/profiles/*.yaml` — 角色档案
- `projects/{project}/assets/scenes/profiles/*.yaml` — 场景档案
- `config/nanobanana/nanobanana-config.yaml` — Nanobanana 配置

## 输出（6 层实体全覆盖）

- `projects/{project}/assets/packs/characters/{角色名}-{variant}-{angle}.png` — 角色定妆包
- `projects/{project}/assets/packs/scenes/{场景名}-{time_of_day}-styleframe.png` — 场景 styleframe
- `projects/{project}/assets/packs/props/{道具名}-{condition}.png` — 道具包（含状态变体）
- `projects/{project}/assets/packs/creatures/{怪物名}-{variant}-{angle}.png` — 怪物/灵兽包 ✨ 新增
- `projects/{project}/assets/packs/vfx/{技能名}-{visual_variant}.png` — 特效参考图 ✨ 新增
- `projects/{project}/assets/packs/asset-manifest.json` — 资产清单

## 执行流程

### Step 1: 读取配置

```bash
# 读取 Nanobanana 配置
cat config/nanobanana/nanobanana-config.yaml

# 检查环境变量
if [[ -z "$TUZI_API_KEY" ]]; then
    echo "错误: TUZI_API_KEY 未设置"
    exit 1
fi
```

### Step 2: 生成角色定妆包

对每个角色的每个变体：

```bash
# 读取角色档案
for profile in projects/{project}/assets/characters/profiles/*.yaml; do
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
- `{角色名}-{variant}-front.png` - 正面
- `{角色名}-{variant}-side.png` - 侧面
- `{角色名}-{variant}-back.png` - 背面

### Step 3: 生成场景 styleframe

对每个场景的每个时段：

```bash
# 读取场景档案
for profile in projects/{project}/assets/scenes/profiles/*.yaml; do
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
- `{场景名}-day-styleframe.png`
- `{场景名}-night-styleframe.png`
- `{场景名}-dusk-styleframe.png`
- `{场景名}-dawn-styleframe.png`

### Step 4: 生成道具包

从本体模型中提取道具：

```bash
# 如果有本体模型，从中提取道具
if [[ -f "projects/{project}/state/ontology/${ep}-world-model.json" ]]; then
    props=$(jq -r '.entities.props | keys[]' "projects/{project}/state/ontology/${ep}-world-model.json")
    
    for prop_name in $props; do
        description=$(jq -r ".entities.props.\"${prop_name}\".description" "projects/{project}/state/ontology/${ep}-world-model.json")
        
        # 生成不同状态的道具
        for condition in intact damaged; do
            ./scripts/nanobanana-caller.sh prop-pack \
                "$prop_name" \
                "$description" \
                "$condition"
        done
    done
fi
```

**生成内容**：
- `{道具名}-intact.png` - 完好
- `{道具名}-damaged.png` - 破损

### Step 4: 生成道具包（Layer 3）

从本体模型中提取道具，生成各状态图：

```bash
mkdir -p projects/{project}/assets/packs/props

if [[ -f "projects/{project}/state/ontology/${ep}-world-model.json" ]]; then
    # 读取 props（v2.1：包含 states 字段）
    props=$(jq -r '.entities.props[]' "projects/{project}/state/ontology/${ep}-world-model.json")

    echo "$props" | jq -c '.' | while IFS= read -r prop; do
        prop_name=$(echo "$prop" | jq -r '.name')
        description=$(echo "$prop" | jq -r '.description')
        asset_needed=$(echo "$prop" | jq -r '.asset_needed // true')

        [[ "$asset_needed" == "false" ]] && continue

        # 每个状态生成一张（只生成有视觉意义的状态）
        for condition in intact damaged destroyed; do
            target="projects/{project}/assets/packs/props/${prop_name}-${condition}.png"
            [[ -f "$target" ]] && continue  # 幂等跳过

            # 跳过 destroyed 状态（视觉无意义时）
            cond_desc=$(echo "$prop" | jq -r ".states.${condition} // empty")
            [[ -z "$cond_desc" && "$condition" == "destroyed" ]] && continue

            ./scripts/nanobanana-caller.sh prop-pack \
                "$prop_name" "$description" "$condition"
        done
    done
fi
```

**生成内容**：
- `{道具名}-intact.png` — 完好状态
- `{道具名}-damaged.png` — 破损状态
- `{道具名}-destroyed.png` — 毁坏状态（有视觉描述时才生成）

---

### Step 5: 生成怪物/灵兽包（Layer 4）✨ 新增

从本体模型的 `entities.creatures` 中提取怪物：

```bash
mkdir -p projects/{project}/assets/packs/creatures

creatures=$(jq -r '.entities.creatures // []' "projects/{project}/state/ontology/${ep}-world-model.json")

echo "$creatures" | jq -c '.[]' 2>/dev/null | while IFS= read -r creature; do
    creature_name=$(echo "$creature" | jq -r '.name')
    appearance=$(echo "$creature" | jq -r '.appearance')
    death_ep=$(echo "$creature" | jq -r '.death_episode // ""')

    # 已死亡的怪物只需要有存档，不需要新生成
    # （死亡前的集数已经生成过了）

    # 生成各变体
    variants=$(echo "$creature" | jq -r '(.variants // {"normal": .appearance}) | keys[]')
    for variant in $variants; do
        variant_desc=$(echo "$creature" | jq -r ".variants.${variant} // .appearance")
        for angle in front side; do
            target="projects/{project}/assets/packs/creatures/${creature_name}-${variant}-${angle}.png"
            [[ -f "$target" ]] && continue

            ./scripts/nanobanana-caller.sh creature-pack \
                "$creature_name" "$variant_desc" "$variant" "$angle"
        done
    done
done
```

**生成内容**：
- `{怪物名}-normal-front.png` — 正常状态正面
- `{怪物名}-normal-side.png` — 正常状态侧面
- `{怪物名}-enraged-front.png` — 激怒状态正面（如有）

---

### Step 6: 生成特效参考图（Layer 5）✨ 新增

从本体模型的 `entities.vfx` 中提取技能特效：

```bash
mkdir -p projects/{project}/assets/packs/vfx

vfx_list=$(jq -r '.entities.vfx // []' "projects/{project}/state/ontology/${ep}-world-model.json")

echo "$vfx_list" | jq -c '.[]' 2>/dev/null | while IFS= read -r vfx; do
    vfx_name=$(echo "$vfx" | jq -r '.name')
    visual_desc=$(echo "$vfx" | jq -r '.visual_description')
    color_palette=$(echo "$vfx" | jq -r '.color_palette // "玄幻蓝紫"')
    seedance_keywords=$(echo "$vfx" | jq -r '.seedance_keywords // ""')

    # 只生成 activated 状态（最常用）
    target="projects/{project}/assets/packs/vfx/${vfx_name}-activated.png"
    [[ -f "$target" ]] && continue

    ./scripts/nanobanana-caller.sh vfx-pack \
        "$vfx_name" "$visual_desc" "activated" "$color_palette"
done
```

**生成内容**：
- `{技能名}-activated.png` — 释放状态参考图
- 供 shot-compiler-agent 在生成 Seedance prompt 时引用关键词

---

### Step 7: 生成资产清单

```bash
cat > projects/{project}/assets/packs/asset-manifest.json << EOF
{
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "schema_version": "2.1",
  "characters": $(find projects/{project}/assets/packs/characters -name "*.png" 2>/dev/null | jq -R -s -c 'split("\n")[:-1]'),
  "scenes":     $(find projects/{project}/assets/packs/scenes     -name "*.png" 2>/dev/null | jq -R -s -c 'split("\n")[:-1]'),
  "props":      $(find projects/{project}/assets/packs/props      -name "*.png" 2>/dev/null | jq -R -s -c 'split("\n")[:-1]'),
  "creatures":  $(find projects/{project}/assets/packs/creatures  -name "*.png" 2>/dev/null | jq -R -s -c 'split("\n")[:-1]'),
  "vfx":        $(find projects/{project}/assets/packs/vfx        -name "*.png" 2>/dev/null | jq -R -s -c 'split("\n")[:-1]')
}
EOF
```

### Step 8: 写入 LanceDB

```bash
if .venv/bin/python -c "import lancedb" 2>/dev/null; then
    .venv/bin/python scripts/vectordb-manager.py index-assets projects/{project}/assets/packs/ 2>/dev/null
    echo "✓ LanceDB 资产索引更新完成"
fi
```

### Step 9: 验证生成结果

```bash
echo "资产生成完成:"
echo "  角色:   $(find projects/{project}/assets/packs/characters -name '*.png' 2>/dev/null | wc -l) 张"
echo "  场景:   $(find projects/{project}/assets/packs/scenes     -name '*.png' 2>/dev/null | wc -l) 张"
echo "  道具:   $(find projects/{project}/assets/packs/props      -name '*.png' 2>/dev/null | wc -l) 张"
echo "  怪物:   $(find projects/{project}/assets/packs/creatures  -name '*.png' 2>/dev/null | wc -l) 张"
echo "  特效:   $(find projects/{project}/assets/packs/vfx        -name '*.png' 2>/dev/null | wc -l) 张"
```

### Step 10: 同步到 images/ 目录（路径统一）

asset-factory 生成到 `assets/packs/`，但 visual-agent、shot-compiler-agent、memory-agent 读取的是 `assets/characters/images/` 和 `assets/scenes/images/`。
生成完成后，将 packs 中的 front 视图同步到 images 目录，保持路径兼容：

```bash
# 同步角色 front 视图到 assets/characters/images/
mkdir -p "projects/{project}/assets/characters/images"
for pack_file in projects/{project}/assets/packs/characters/*.png; do
  filename=$(basename "$pack_file")
  # packs 命名：{角色名}-{variant}-{angle}.png
  # images 命名：{角色名}-{variant_id}-{view}.png（相同格式，直接复制）
  target="projects/{project}/assets/characters/images/${filename}"
  if [[ ! -f "$target" ]]; then
    cp "$pack_file" "$target"
    echo "✓ 同步: $filename → assets/characters/images/"
  fi
done

# 同步场景 styleframe 到 assets/scenes/images/
mkdir -p "projects/{project}/assets/scenes/images"
for pack_file in projects/{project}/assets/packs/scenes/*.png; do
  filename=$(basename "$pack_file")
  # packs 命名：{场景名}-{time_of_day}-styleframe.png
  # images 命名：{场景名}-{time_of_day}.png（去掉 -styleframe 后缀）
  target_name="${filename/-styleframe/}"
  target="projects/{project}/assets/scenes/images/${target_name}"
  if [[ ! -f "$target" ]]; then
    cp "$pack_file" "$target"
    echo "✓ 同步: $filename → assets/scenes/images/${target_name}"
  fi
done

echo "✓ 路径同步完成"
```

## 完成后

向 team-lead 发送消息：`asset-factory-agent 完成，共生成 {N} 个资产`

写入状态文件 `state/asset-factory-status.json`：
```json
{
  "status": "completed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "data": {
    "characters": {N},
    "scenes": {M},
    "props": {K}
  }
}
```

## Trace 写入

```bash
# 读取输入
./scripts/trace.sh {session_id} asset-factory-trace read_input '{"character_profiles":{N},"scene_profiles":{M}}'

# 生成角色包
./scripts/trace.sh {session_id} asset-factory-trace generate_characters '{"count":{N},"variants":{M}}'

# 生成场景包
./scripts/trace.sh {session_id} asset-factory-trace generate_scenes '{"count":{N},"time_variants":{M}}'

# 生成道具包
./scripts/trace.sh {session_id} asset-factory-trace generate_props '{"count":{N}}'

# 写入产出
./scripts/trace.sh {session_id} asset-factory-trace write_output '{"total_assets":{N}}'
```

## 注意事项

- **幂等性**：生成前检查文件是否已存在，已存在则跳过
- **错误处理**：单个资产生成失败不影响其他资产
- **并行生成**：可并行生成多个资产（注意 API rate limit）
- **成本控制**：记录每次生成的成本
