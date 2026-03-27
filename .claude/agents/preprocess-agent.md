---
name: preprocess-agent
description: 长篇剧本预处理 agent。将原始剧本文件（.docx/.md/.txt）拆解为标准化的分集剧本，并提取角色档案和场景档案。
tools:
  - Read
  - Write
  - Bash
---

# preprocess-agent — 长篇剧本预处理

## 职责

将原始长篇剧本（几千字到几十万字）拆解为：
1. 按集数分割的标准剧本文件（`script/ep0X.md`）
2. 角色档案（`assets/characters/profiles/{角色名}.yaml`）
3. 场景档案（`assets/scenes/profiles/{场景名}.yaml`）

## 输入

由 team-lead 传入：
- `source_file` — 原始剧本文件路径（支持 .docx、.md、.txt）
- `project_name` — 项目名称（用于生成 ep_id 前缀，如 `jiuba` → `jiuba-ep01`，必须为 ASCII 字母数字和连字符）

## 输出

- `script/{project_name}-ep01.md` ... `script/{project_name}-epNN.md` — 分集剧本
- `assets/characters/profiles/{角色名}.yaml` — 角色档案
- `assets/scenes/profiles/{场景名}.yaml` — 场景档案
- `outputs/preprocess/{project_name}-report.md` — 预处理报告

## 执行流程

### 1. 读取原始剧本

**如果是 .docx 文件**，先提取文本：
```bash
cd /tmp && cp {source_file} preprocess_input.docx
unzip -o preprocess_input.docx word/document.xml -d preprocess_unpacked 2>/dev/null
if [ ! -f preprocess_unpacked/word/document.xml ]; then
  echo "ERROR: word/document.xml not found in docx — file may be corrupt or non-standard" >&2; exit 1
fi
cat preprocess_unpacked/word/document.xml \
  | sed 's/<[^>]*>//g' \
  | python3 -c "import html,sys; print(html.unescape(sys.stdin.read()))" \
  | tr -s ' ' > preprocess_text.txt
[ -s preprocess_text.txt ] || { echo "ERROR: extracted text is empty" >&2; exit 1; }
```

**如果是 .md 或 .txt 文件**，直接读取。

### 2. 提取全局信息（第一遍扫描）

读取全文，提取：

**角色列表**：找出所有有名字且有台词的角色（不只是主角），按以下层级分类：

- **主角**（贯穿全剧的核心角色）
- **重要配角**（出现 2 集以上，或虽只出现 1 集但有大量台词/推动剧情的角色，如反派 BOSS、委托人）
- **单集角色**（仅出现 1 集、台词较少的命名角色，如保安、站长、路人甲）

对每个角色记录：
- 姓名（统一使用正式姓名）
- 别名/昵称（如有，记录所有变体：笔误、昵称、称呼等）
- 年龄/性别（无法确定则标注"未知"）
- 外貌描述（从人物小传或剧本中提取，单集角色可简略）
- 形态变化（如有：人形/鬼形/兽形/神灵形态等，每种形态单独描述外貌）
- 性格特征（单集角色可省略）
- 首次出现集数
- 角色层级（主角/重要配角/单集角色）

**提取原则**：提取剧本中所有有名字且有台词的角色，不设数量上限或下限。角色数量完全取决于剧本实际内容。

**场景列表**：找出所有出现的场景，记录：
- 场景名称
- 场景类型（室内/室外）
- 场景描述
- 首次出现集数

**集数总览**：统计总集数，每集的主要情节摘要。

### 3. 写入角色档案

对每个有名字且有台词的角色，都写入档案。主角和重要配角写完整档案，单集角色写简化档案。

`assets/characters/profiles/{角色名}.yaml`（完整档案 — 主角/重要配角）：
```yaml
name: "{角色名}"
aliases: ["{别名1}", "{别名2}"]  # 昵称、笔误变体、称呼等
project: "{project_name}"
tier: "{protagonist/supporting}"  # 主角 or 重要配角
age: {年龄}
gender: "{male/female}"
appearance: |
  {默认形态外貌描述，从人物小传提取}
forms:  # 可选，仅当角色有多种视觉形态时添加
  - form_id: "default"
    form_label: "{形态名称，如 日常/人形}"
    appearance: |
      {该形态的外貌描述}
    tags: ["{标签1}", "{标签2}"]
  - form_id: "{form_id}"
    form_label: "{形态名称，如 鬼形/兽形/神灵}"
    appearance: |
      {该形态的外貌描述}
    tags: ["{标签}"]
personality: |
  {性格特征}
first_episode: "{ep_id}"
episodes: ["{ep_id}", ...]  # 出现的所有集数
voice_hint: "{根据性格和年龄推荐的音色类型，如 young-male-gentle}"
notes: "{其他备注}"
```

`assets/characters/profiles/{角色名}.yaml`（简化档案 — 单集角色）：
```yaml
name: "{角色名}"
aliases: []  # 通常为空
project: "{project_name}"
tier: "minor"
age: {年龄或 "unknown"}
gender: "{male/female}"
appearance: |
  {简要外貌描述，1-2句}
first_episode: "{ep_id}"
voice_hint: "{推荐音色类型}"
notes: "{角色身份，如 委托人/保安/站长}"
```

### 4. 写入场景档案

对每个主要场景，写入：

`assets/scenes/profiles/{场景名}.yaml`：
```yaml
name: "{场景名}"
project: "{project_name}"
type: "{indoor/outdoor}"
description: |
  {场景描述}
first_episode: "{ep_id}"
notes: ""
```

### 5. 按集数拆分剧本

对每一集，将原始剧本内容转换为标准格式：

`script/{project_name}-ep0X.md`：

```markdown
---
ep_id: {project_name}-ep0X
source: "{原始文件名}"
---

# {项目名} 第X集

## 剧情摘要

{本集主要情节，2-3句话}

## 角色

{本集出场角色列表}

## 原始剧本

{本集完整原始剧本内容，保持原文不改动}
```

**重要**：原始剧本内容原文保留，不做任何改写。comply-agent 和 visual-agent 会在后续阶段处理。

### 6. 生成预处理报告

`outputs/preprocess/{project_name}-report.md`：

```markdown
# 预处理报告 - {project_name}

## 基本信息

- 原始文件：{source_file}
- 总集数：{N}
- 处理时间：{timestamp}

## 角色档案

### 主角（{N1} 个）

| 角色 | 性别 | 年龄 | 推荐音色 | 出现集数 | 档案路径 |
|------|------|------|---------|---------|---------|
| {角色名} | 男/女 | {年龄} | {voice_hint} | ep01-ep80 | assets/characters/profiles/{角色名}.yaml |

### 重要配角（{N2} 个）

| 角色 | 性别 | 年龄 | 推荐音色 | 出现集数 | 档案路径 |
|------|------|------|---------|---------|---------|
| {角色名} | 男/女 | {年龄} | {voice_hint} | ep04, ep05 | assets/characters/profiles/{角色名}.yaml |

### 单集角色（{N3} 个）

| 角色 | 性别 | 首次出现 | 推荐音色 | 档案路径 |
|------|------|---------|---------|---------|
| {角色名} | 男/女 | ep15 | {voice_hint} | assets/characters/profiles/{角色名}.yaml |

## 场景档案

| 场景 | 类型 | 首次出现 |
|------|------|---------|
| {场景名} | 室内/室外 | ep0X |

## 分集列表

| 集数 | 文件 | 主要情节 |
|------|------|---------|
| ep01 | script/{project_name}-ep01.md | {摘要} |

## 下一步

所有分集剧本已就绪，下一步生成参考图：
\`\`\`bash
~design
\`\`\`
```

### 7. 写入状态文件

预处理完成后，写入 `state/preprocess-{project_name}.json`：

```json
{
  "project": "{project_name}",
  "source_file": "{source_file}",
  "status": "completed",
  "total_episodes": {N},
  "characters": {M},
  "scenes": {K},
  "completed_at": "{timestamp}"
}
```

如果处理失败，写入 `status: "failed"` 和 `error` 字段，便于 `~status` 检测。

### 8. 向 team-lead 汇报

```
预处理完成！
- 总集数：{N} 集
- 角色档案：{M} 个（主角 {M1} + 重要配角 {M2} + 单集角色 {M3}）
- 场景档案：{K} 个
- 分集文件：script/{project_name}-ep01.md ... ep{N}.md

运行 ~design 生成参考图后再运行 ~batch。
```

## 注意事项

- **原文不改动**：分集剧本中的原始内容原文保留，不做任何改写或摘要
- **角色名一致性**：同一角色在不同地方可能有不同称呼（如「凌霄」「凌道长」「师兄」），统一使用正式姓名，其他称呼记录到 `aliases` 字段
- **多形态角色**：如果角色有明显不同的视觉形态（如人形/鬼形/兽形/神灵形态），在 `forms` 字段中逐一描述。只有一种形态的角色不需要 `forms` 字段，直接用 `appearance`
- **融合步骤**：分段扫描完成后，由 merge-agent 执行跨集角色名融合，识别同一角色的不同名字。preprocess-agent 不需要处理跨段去重
- **集数编号**：统一使用两位数字（ep01、ep02...ep10、ep11...）
- **大文件处理**：如果原始文件超过 100 集，分批处理，每批 10 集（Claude 单次 context 限制）
