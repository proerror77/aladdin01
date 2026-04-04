# ~preprocess — 长篇剧本预处理

将原始剧本文件（.docx/.md/.txt）拆解为标准化分集剧本，并提取角色档案和场景档案。

## 使用方式

```
~preprocess                          # 扫描 raw/ 目录下的文件
~preprocess /path/to/script.docx     # 指定文件路径
~preprocess /path/to/script.docx jiuba  # 指定文件路径 + 项目名
```

## 执行流程

### 1. 确定输入文件

**无参数**：扫描 `raw/` 目录，列出所有 `.docx`、`.md`、`.txt` 文件，让用户选择。

**有文件路径**：直接使用该文件。

如果文件不存在：
```
❌ 文件不存在：{path}
请检查路径后重试。
```

### 2. 确定项目名

**已提供**：直接使用（必须为 ASCII 字母数字和连字符，如 `jiuba`、`bar-boss`）。

**未提供**：文件名包含非 ASCII 字符（如中文）时，**不能自动推断**，必须询问用户：

```
文件名包含非 ASCII 字符，无法自动生成项目名。
请输入项目名（仅限英文字母、数字、连字符，如 jiuba）：
```

文件名为纯 ASCII 时，从文件名推断（去掉扩展名，替换空格为连字符，转小写），并询问确认：

```
项目名将用于生成文件名（如 jiuba-ep01.md）。
推断项目名：{name}
确认？(yes/修改为其他名称)
```

### 3. 启动预处理

```
开始预处理：{filename}
项目名：{project_name}

正在提取文本...
正在分析角色和场景...
正在拆分集数...
```

spawn preprocess-agent：
- `source_file`: 文件路径
- `project_name`: 项目名
- 等待完成

### 3.5 角色融合（大文件分段扫描时）

如果预处理使用了分段扫描（多个 scan agent 并行扫描不同集数范围），在写入最终档案前执行跨集角色名融合：

1. 检查 `state/char-scan-ep*.md` 是否存在多个扫描结果文件
2. 如果只有 1 个（小剧本，未分段）→ 跳过融合，直接写档案
3. 如果有多个 → spawn merge-agent：
   - `scan_files`: 所有 `state/char-scan-ep*.md` 文件路径
   - `project_name`: 项目名
   - 等待完成
4. 展示融合结果：

```
🔗 角色融合完成
   合并了 {M} 组角色（涉及 {K} 个别名）
   最终独立角色数：{N}
   融合映射表：state/character-merge-map.json

   合并示例：
   - 凌霄 ← [凌宵, 宵凌]（笔误）
   - 曾令辉 ← [阿白]（昵称）
```

5. 后续写档案步骤读取 `state/character-merge-map.json`，按正名写入，aliases 记录到 YAML

### 4. 展示结果

预处理完成后，展示报告摘要：

```
✅ 预处理完成！

📺 共 {N} 集
   script/{project_name}-ep01.md ... ep{N}.md

👥 角色档案 {M} 个
   主角（{M1}）：{角色1}、{角色2}...
   重要配角（{M2}）：{角色3}、{角色4}...
   单集角色（{M3}）：{角色5}、{角色6}...

🏠 场景档案 {K} 个

详细报告：outputs/preprocess/{project_name}-report.md

下一步：运行 ~design 生成参考图（角色 + 场景）
      推荐在 ~batch 前运行；~start 模式可选（Phase 3 会提示缺失的参考图）
```

## 支持的文件格式

| 格式 | 说明 |
|------|------|
| `.docx` | Word 文档，自动提取文本 |
| `.md` | Markdown 格式剧本 |
| `.txt` | 纯文本剧本 |

## 目录约定

- `raw/` — 放置原始剧本文件（建议）
- `script/` — 预处理后的分集剧本输出目录
- `projects/{project}/assets/characters/profiles/` — 角色档案
- `projects/{project}/assets/scenes/profiles/` — 场景档案
- `outputs/preprocess/` — 预处理报告
