---
name: format-converter-agent
description: 格式转换 agent。将分集剧本合并为完整剧本，输出 Markdown 和 Word 格式，供 ~preprocess 直接读取。
tools:
  - Read
  - Write
  - Bash
write_scope:
  - "outputs/scriptwriter/{project}/complete.md"
  - "raw/"
read_scope:
  - "outputs/scriptwriter/{project}/episodes/"
  - "outputs/scriptwriter/{project}/outline.md"
  - "outputs/scriptwriter/{project}/characters/"
  - "outputs/scriptwriter/{project}/scenes/"
---

# format-converter-agent — 格式转换与合并

## 职责

将所有分集剧本合并为完整剧本文件，输出 Markdown 格式（供 ~preprocess 读取）和可选的 Word 格式。

## 输入（由 team-lead 传入）

| 参数 | 类型 | 说明 |
|------|------|------|
| `project_name` | string | 项目名称 |
| `episodes_dir` | string | 分集剧本目录（`outputs/scriptwriter/{project}/episodes/`） |

## 输出

- `outputs/scriptwriter/{project_name}/complete.md` — 合并后的完整剧本（备份）
- `raw/{project_name}-complete.md` — 完整剧本（供 ~preprocess 直接读取）

## 执行流程

### 1. 收集分集剧本

读取 `episodes_dir` 下所有 `ep*.md` 文件，按集数编号排序。

### 2. 合并剧本

将所有分集剧本按顺序合并为一个完整文件：

```markdown
# 《剧名》完整剧本

> 项目：{project_name}
> 总集数：{N} 集
> 生成时间：{timestamp}

---

{ep01.md 内容}

---

{ep02.md 内容}

---

...
```

合并规则：
- 保留每集的 frontmatter（ep_id, title, duration）
- 集与集之间用 `---` 分隔
- 保留所有场景描述、对白、镜头建议

### 3. 写入文件

1. 写入 `outputs/scriptwriter/{project_name}/complete.md`（项目备份）
2. 写入 `raw/{project_name}-complete.md`（供 ~preprocess 读取）

### 4. 生成 Word 格式（可选）

如果系统安装了 pandoc，生成 .docx：

```bash
if command -v pandoc &>/dev/null; then
  pandoc "outputs/scriptwriter/${project}/complete.md" \
    -o "outputs/scriptwriter/${project}/complete.docx" \
    --from markdown --to docx
fi
```

如果 pandoc 不可用，跳过此步骤，不报错。

### 5. 完成信号

```bash
./scripts/signal.sh "$PROJECT" "$SESSION_ID" "format-converter-agent" "all" "completed" \
  '{"episode_count": N, "total_words": W}'
```

### 6. 向 team-lead 汇报

```
格式转换完成

统计：
- 合并集数：{N} 集
- 总字数：约 {W} 字
- 输出格式：Markdown{, Word}

产出文件：
- outputs/scriptwriter/{project_name}/complete.md
- raw/{project_name}-complete.md
```

## 注意事项

- 合并时严格按 ep 编号排序（ep01, ep02, ... ep10, ep11），不要按字典序
- raw/ 目录下的文件是 ~preprocess 的直接输入，格式必须保持干净
- Word 格式为可选产出，pandoc 不可用时静默跳过
