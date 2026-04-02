# ~extract-style — 从成功案例中提取风格特征

从已有的 visual-direction.yaml 或成功的视频 prompt 中提取风格特征，保存为可复用的风格资产。

## 使用方式

```
~extract-style outputs/qyccan-ep01/visual-direction.yaml --name "写实东方"
~extract-style outputs/qyccan-ep07/visual-direction.yaml --append "写实东方"
~extract-style --list                    # 列出所有已注册风格
~extract-style --bind qyccan realistic-oriental  # 绑定项目到风格
```

## 执行流程

### 1. 确定输入

**有文件路径**：从指定的 visual-direction.yaml 中提取。

**--list**：列出 `config/styles/registry.yaml` 中所有已注册风格。

**--bind**：将项目绑定到指定风格（写入 registry.yaml 的 project_bindings）。

### 2. 提取风格特征

读取 visual-direction.yaml 中所有 shot 的 seedance_prompt / style / camera 字段。

使用 LLM 分析提取以下维度：

```
请从以下 {N} 个 Seedance 提示词中提取统一的风格特征。

分析维度：
1. image_style.base_keywords — 反复出现的写实/质感关键词
2. image_style.lighting — 光影风格（按 default/warm/cold/dramatic/candle 分类）
3. image_style.avoid — 这些 prompt 中刻意避免的关键词
4. video_style.style_block — 风格段的共性（按 default/action/emotional/epic/night 分类）
5. video_style.quality_suffix — 质量后缀的共性
6. video_style.camera_preference — 镜头偏好
7. video_style.color_grade — 色彩基调
8. composition.preferred_rules — 构图偏好

输出 YAML 格式，与 config/styles/ 下的风格文件结构一致。
```

### 3. 保存风格文件

**新建模式（--name）**：

```bash
style_id=$(echo "$name" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')
output_file="config/styles/${style_id}.yaml"

# 写入提取的风格
cat > "$output_file" << EOF
name: "$name"
id: "$style_id"
${extracted_yaml}
extracted_from:
  - source: "$input_file"
    note: "自动提取于 $(date -u +%Y-%m-%dT%H:%M:%SZ)"
EOF

# 注册到 registry.yaml
yq eval ".styles.${style_id} = {\"file\": \"${output_file}\", \"description\": \"${name} — 自动提取\"}" -i config/styles/registry.yaml
```

**追加模式（--append）**：

读取已有风格文件，将新提取的特征与已有特征合并（去重），更新 extracted_from 列表。

### 4. 绑定项目

**--bind 模式**：

```bash
project_name="$1"
style_id="$2"

# 验证风格存在
if ! yq eval ".styles.${style_id}" config/styles/registry.yaml | grep -q "file"; then
    echo "错误: 风格 ${style_id} 不存在"
    exit 1
fi

# 写入绑定
yq eval ".project_bindings.${project_name} = \"${style_id}\"" -i config/styles/registry.yaml
echo "✓ 项目 ${project_name} 已绑定风格 ${style_id}"
```

### 5. 输出确认

```
✓ 风格提取完成: config/styles/realistic-oriental.yaml
  - 基础关键词: 7 个
  - 光影变体: 5 种
  - 构图偏好: 4 条
  - 来源: outputs/qyccan-ep01/visual-direction.yaml

使用方式:
  ~extract-style --bind {project} realistic-oriental
  或在 ~scriptwriter 中指定: ~scriptwriter --style realistic-oriental
```

## 注意事项

- 提取是增量的：--append 不会覆盖已有关键词，只追加新发现的
- 风格文件是人可编辑的 YAML，提取后可以手动微调
- 绑定是项目级的，一个项目只能绑定一个风格
- visual-agent 在生成 seedance_prompt 时自动读取绑定的风格
