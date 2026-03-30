# ~scriptwriter — 剧本创作

从创意发想生成完整长篇剧本。

## 使用方式

```bash
~scriptwriter                           # 交互式创作
~scriptwriter --idea "你的创意"          # 直接输入创意
~scriptwriter --episodes 20             # 指定集数（默认 10）
~scriptwriter --length short            # 短剧模式（每集 60-90 秒）
~scriptwriter --length medium           # 中剧模式（每集 3-5 分钟）
~scriptwriter --length long             # 长剧模式（每集 10-15 分钟）
```

## 参数

| 参数 | 说明 |
|------|------|
| `--idea <text>` | 创意描述（可选，不提供则交互式输入） |
| `--episodes <N>` | 目标集数（默认 10） |
| `--length <mode>` | 每集时长模式：short/medium/long（默认 short） |
| `--genre <type>` | 故事类型：romance/mystery/scifi/fantasy/comedy（可选） |
| `--style <ref>` | 参考风格（可选，如"类似《爱情公寓》"） |

## 执行流程

### 1. 收集创意信息

**如果未提供 --idea**，交互式问答：

```
━━━ 剧本创作助手 ━━━

请描述你的创意（可以很简短）：
> 程序员和咖啡店老板的爱情故事

很好！让我问几个问题来完善创意：

1. 故事类型？
   1) 都市爱情
   2) 古装言情
   3) 悬疑推理
   4) 科幻奇幻
   5) 喜剧
   6) 其他
> 1

2. 目标集数？
   1) 短剧 (10-20 集)
   2) 中剧 (20-40 集)
   3) 长剧 (40-80 集)
> 1

3. 每集时长？
   1) 短视频 (60-90 秒)
   2) 中视频 (3-5 分钟)
   3) 长视频 (10-15 分钟)
> 1

4. 核心冲突/看点是什么？（可选）
> 他们其实是多年前的网友，但都不知道

5. 目标受众？（可选）
> 18-35 岁都市白领

6. 参考作品/风格？（可选）
> 类似《爱情公寓》的轻松幽默风格
```

### 2. 生成项目大纲

spawn **outline-agent**：

**任务**：
1. 分析创意核心（主题、冲突、情感线）
2. 设计故事结构（三幕式/五幕式）
3. 规划分集节奏（起承转合）
4. 设计主要角色（3-5 个主角 + 配角）
5. 设计主要场景（5-10 个）
6. 生成分集大纲（每集 2-3 句话概括）

**产出**：`outputs/scriptwriter/{project-name}/outline.md`

**大纲结构**：
```markdown
# 《剧名》剧本大纲

## 基本信息
- 类型：都市爱情轻喜剧
- 集数：15 集
- 每集时长：60-90 秒
- 总时长：约 15-20 分钟

## 核心设定
- 主题：错过与重逢
- 核心冲突：线上线下的身份差异
- 情感线：从误会 → 了解 → 暧昧 → 真相 → 在一起

## 主要角色
1. **角色名**（主角，年龄，职业）
   - 性格：...
   - 外貌：...
   - 背景：...

## 主要场景
1. **场景名**
   - 类型：室内/室外
   - 描述：...

## 分集大纲
### 第 1 集：标题
- 剧情概要（2-3 句话）

### 第 2 集：标题
- 剧情概要
```

🔴 **人工确认点 1**：
```
大纲已生成，请查看：outputs/scriptwriter/{project}/outline.md

确认后继续生成完整剧本？(yes/no/revise)
- yes: 继续生成
- no: 终止
- revise: 修改大纲（你可以直接编辑 outline.md 后输入 yes）
```

### 3. 生成角色档案

spawn **character-creator-agent**：

**任务**：
1. 读取 outline.md 中的角色信息
2. 为每个角色生成详细档案
3. 包含：外貌、性格、背景故事、口头禅、行为习惯
4. 如果有线上/线下双重身份，分别描述

**产出**：`outputs/scriptwriter/{project-name}/characters/*.yaml`

**角色档案格式**：
```yaml
name: "角色名"
age: 28
gender: "male/female"
role: "protagonist/supporting/minor"
occupation: "职业"
personality: |
  性格描述（多行）
appearance: |
  外貌描述（详细，用于后续生成参考图）
backstory: |
  背景故事
catchphrase: "口头禅"
habits:
  - 习惯 1
  - 习惯 2
online_persona:  # 可选，如果有线上身份
  username: "网名"
  personality: "线上性格"
  contrast: "与线下的差异"
```

### 4. 生成场景档案

spawn **scene-creator-agent**：

**任务**：
1. 读取 outline.md 中的场景信息
2. 为每个场景生成详细档案
3. 包含：类型、描述、氛围、关键道具、时间变体

**产出**：`outputs/scriptwriter/{project-name}/scenes/*.yaml`

**场景档案格式**：
```yaml
name: "场景名"
type: "indoor/outdoor"
description: |
  场景详细描述（用于后续生成参考图）
atmosphere: "氛围描述"
key_props:
  - "关键道具 1"
  - "关键道具 2"
time_variants:
  - "早晨（光线描述）"
  - "下午（光线描述）"
  - "晚上（光线描述）"
```

### 5. 并行生成分集剧本

spawn **episode-writer-agent × N**（每集一个 agent，并行）：

**任务**（每个 agent 负责一集）：
1. 读取 outline.md 中该集的大纲
2. 读取相关角色档案
3. 读取相关场景档案
4. 生成完整剧本：
   - 场景描述
   - 人物动作
   - 对白
   - 镜头建议（可选）
   - 时长控制（根据 --length 参数）

**产出**：`outputs/scriptwriter/{project-name}/episodes/ep01.md` ... `epNN.md`

**剧本格式**：
```markdown
---
ep_id: {project}-ep01
title: "集标题"
duration: "60-90 秒"
---

# 《剧名》第 1 集：集标题

## 场景 1：场景名 - 时间

**[镜头]** 镜头描述

**[场景描述]** 场景详细描述

**[人物]** 人物动作描述

**角色名**：（情绪/动作）"对白内容"

**角色名**：（情绪/动作）"对白内容"

---

## 场景 2：场景名 - 时间

...

---

【第 X 集完】
```

🔴 **人工确认点 2**（每 5 集确认一次）：
```
前 5 集剧本已生成，请查看：
- outputs/scriptwriter/{project}/episodes/ep01.md
- outputs/scriptwriter/{project}/episodes/ep02.md
- outputs/scriptwriter/{project}/episodes/ep03.md
- outputs/scriptwriter/{project}/episodes/ep04.md
- outputs/scriptwriter/{project}/episodes/ep05.md

确认后继续生成剩余集数？(yes/no/revise)
- yes: 继续生成 ep06-ep10
- no: 终止
- revise: 修改已生成的剧本（你可以直接编辑后输入 yes）
```

### 6. 质量检查与优化

spawn **script-reviewer-agent**：

**任务**：
1. 检查剧情连贯性（前后呼应、伏笔回收）
2. 检查角色一致性（性格、说话方式、行为习惯）
3. 检查时长估算（每集是否符合目标时长）
4. 检查对白自然度（是否符合角色人设）
5. 标注潜在问题

**产出**：`outputs/scriptwriter/{project-name}/review-report.md`

**报告格式**：
```markdown
# 剧本质量检查报告

## 总体评估
- 剧情连贯性：✅ 良好 / ⚠️ 需注意 / ❌ 有问题
- 角色一致性：✅ 良好 / ⚠️ 需注意 / ❌ 有问题
- 时长控制：✅ 良好 / ⚠️ 需注意 / ❌ 有问题
- 对白自然度：✅ 良好 / ⚠️ 需注意 / ❌ 有问题

## 具体问题

### 第 X 集
- **问题**：问题描述
- **建议**：优化建议

## 优化建议
1. 全局建议 1
2. 全局建议 2
```

🔴 **人工确认点 3**：
```
质量检查完成，发现 X 个需要优化的地方。

查看报告：outputs/scriptwriter/{project}/review-report.md

是否自动优化？(yes/no/manual)
- yes: 自动优化（AI 根据建议修改剧本）
- no: 保持原样
- manual: 我自己手动修改
```

### 7. 格式转换与输出

spawn **format-converter-agent**：

**任务**：
1. 将所有分集剧本合并
2. 转换为标准格式
3. 生成 .docx 文件（用于 ~preprocess）
4. 生成 Markdown 版本（便于阅读）
5. 复制角色/场景档案到标准位置

**产出**：
- `raw/{project-name}-complete.md`（完整剧本，供 ~preprocess 直接读取）
- `outputs/scriptwriter/{project-name}/complete.md`（完整剧本，备份）
- `outputs/scriptwriter/{project-name}/characters/*.yaml`（角色档案）
- `outputs/scriptwriter/{project-name}/scenes/*.yaml`（场景档案）

### 8. 最终输出

```
✅ 剧本创作完成！

📊 统计信息：
- 项目名称：{project-name}
- 总集数：{N} 集
- 每集时长：{duration} 秒
- 总时长：约 {total} 分钟
- 主要角色：{M} 个
- 场景数：{K} 个
- 总字数：约 {words} 字

📁 产出文件：
- 完整剧本：raw/{project-name}-complete.md
- 分集剧本：outputs/scriptwriter/{project-name}/episodes/ep*.md
- 角色档案：outputs/scriptwriter/{project-name}/characters/*.yaml
- 场景档案：outputs/scriptwriter/{project-name}/scenes/*.yaml
- 项目大纲：outputs/scriptwriter/{project-name}/outline.md
- 质量报告：outputs/scriptwriter/{project-name}/review-report.md

🎬 下一步：
1. 运行 ~preprocess raw/{project-name}-complete.md {project-name}
2. 运行 ~design 生成参考图
3. 运行 ~batch 开始批量生产

或者直接运行一键命令：
~scriptwriter-to-video --resume {project-name}  # 从阶段 2 继续
```

## 时长模式说明

| 模式 | 每集时长 | 适用场景 | 字数估算 |
|------|---------|---------|---------|
| `short` | 60-90 秒 | 抖音/快手短视频 | 300-500 字/集 |
| `medium` | 3-5 分钟 | B站/YouTube 中视频 | 1500-2500 字/集 |
| `long` | 10-15 分钟 | 传统网剧 | 5000-8000 字/集 |

## 故事类型说明

| 类型 | 说明 | 典型元素 |
|------|------|---------|
| `romance` | 都市/古装爱情 | 误会、暧昧、告白、在一起 |
| `mystery` | 悬疑推理 | 线索、反转、真相揭晓 |
| `scifi` | 科幻 | 未来科技、时空穿越 |
| `fantasy` | 奇幻/玄幻 | 修仙、魔法、异世界 |
| `comedy` | 喜剧 | 搞笑、误会、夸张 |

## 注意事项

- **创意输入**：越详细越好，但也可以很简短（系统会通过交互补充）
- **人工确认点**：共 3 个，可以随时修改和调整
- **并行生成**：所有分集剧本并行生成，速度快
- **质量保证**：自动检查剧情连贯性和角色一致性
- **格式兼容**：产出的 .docx 文件可直接用于 ~preprocess

## 高级用法

### 快捷命令（一键到底）

```bash
~scriptwriter-to-video --idea "你的创意" --episodes 15 --length short
```

自动执行：
1. ~scriptwriter（剧本创作）
2. ~preprocess（剧本预处理）
3. ~design（生成参考图）
4. ~batch（批量生产）

全程自动，只在关键节点需要人工确认。

### 断点续传

如果创作过程中断：

```bash
~scriptwriter --resume {project-name}
```

从上次中断的地方继续。

### 修改已有剧本

```bash
~scriptwriter --revise {project-name} --episode 5
```

只修改第 5 集的剧本，其他集数保持不变。
