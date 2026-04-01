# lanshu-waytovideo 项目分析与借鉴

## 项目概览

**lanshu-waytovideo** 是一个使用 Playwright 自动化操作剪映(小云雀)生成 AI 视频的项目，支持 Seedance 2.0 模型。

## 核心架构特点

### 1. **Skill-Based 设计**（✅ 值得借鉴）

```
jianying-video-gen/
├── SKILL.md                    # Agent 识别的技能说明（frontmatter + 使用文档）
├── requirements.txt            # 依赖声明
├── scripts/
│   └── jianying_worker.py      # 核心自动化脚本
└── references/
    └── prompt-guide.md         # 提供给 Agent 学习的提示词指南
```

**关键设计**：
- `SKILL.md` 使用 YAML frontmatter 声明 skill 元数据
- `references/` 目录存放 Agent 学习材料（提示词指南）
- 单一入口脚本 `jianying_worker.py`，参数化调用

**对比我们的项目**：
- ✅ 我们也用 `.claude/skills/*.md` 和 `.claude/agents/*.md`
- ❌ 我们缺少 `references/` 目录存放学习材料
- ❌ 我们的 agent 定义分散，没有统一的 skill 入口

### 2. **提示词工程方法**（✅ 强烈推荐借鉴）

`references/prompt-guide.md` 提供了结构化的提示词模板：

```
[主体描述]，[动作/行为]，[画面风格]，[镜头语言]，[环境/光影]
```

**分类示例**：
- 🎬 运动 & 动作
- 🌊 自然 & 特效
- 🎥 镜头语言
- 🔥 风格化
- 🏯 超现实
- 🔄 V2V 风格转换

**对比我们的项目**：
- ✅ 我们有 `.claude/skills/seedance/SKILL.md` 提示词指南
- ❌ 我们的提示词指南混在 skill 定义中，不够独立
- ❌ 我们缺少分类示例和模板

### 3. **Browser Automation**（✅ 已实现）

使用 Playwright + Chromium 自动化操作 Web UI：
- Cookie 登录
- 表单填写
- 文件上传
- 轮询结果
- 下载视频

**对比我们的项目**：
- ✅ 我们已有 `scripts/jimeng-web.sh` 使用 Actionbook CLI
- ✅ 我们已有 `browser-gen-worker` agent
- ⚠️ 他们用 Playwright（更成熟），我们用 Actionbook（更轻量）

### 4. **参数化设计**（✅ 值得借鉴）

单一脚本通过参数支持多种模式：
- `--prompt` — 提示词
- `--duration` — 时长（5s/10s/15s）
- `--ratio` — 比例（横屏/竖屏/方屏）
- `--model` — 模型（Seedance 2.0 / Fast）
- `--ref-image` — 参考图（I2V）
- `--ref-video` — 参考视频（V2V）
- `--extend-url` — 向后延伸
- `--dry-run` — 调试模式

**对比我们的项目**：
- ✅ 我们的 `gen-worker` 也支持参数化
- ❌ 我们缺少 `--dry-run` 调试模式
- ❌ 我们缺少 V2V（参考视频）和 Extend（向后延伸）模式

### 5. **错误处理与重试**（✅ 值得借鉴）

```python
async def goto_with_retry(page, url: str, attempts: int = 3):
    for idx in range(attempts):
        try:
            await page.goto(url, wait_until='domcontentloaded')
            return True
        except Exception as e:
            print(f"导航失败，第 {idx + 1}/{attempts} 次: {e}")
            if idx < attempts - 1:
                await page.wait_for_timeout(2500)
```

**对比我们的项目**：
- ✅ 我们的 `gen-worker` 有重试机制（5 次原始 + 3 轮改写）
- ❌ 我们的浏览器操作缺少重试逻辑

### 6. **调试友好**（✅ 值得借鉴）

- `--dry-run` 模式：只填表不提交，生成截图
- 自动截图：每个关键步骤保存 `step_*.png`
- 详细日志：打印每个操作的状态

**对比我们的项目**：
- ❌ 我们缺少 dry-run 模式
- ❌ 我们缺少自动截图功能
- ✅ 我们有 trace 日志系统

## 可借鉴的改进点

### 🔥 高优先级

1. **独立 references/ 目录**
   ```
   .claude/skills/seedance/
   ├── SKILL.md
   └── references/
       ├── prompt-templates.md      # 提示词模板
       ├── prompt-examples.md       # 分类示例
       └── camera-vocabulary.md     # 镜头语言词汇库
   ```

2. **提示词模板化**
   - 将 `SKILL.md` 中的提示词知识提取到独立文件
   - 按场景分类（运动/自然/风格化/超现实）
   - 提供填空式模板

3. **Dry-Run 调试模式**
   ```bash
   ./scripts/jimeng-web.sh submit --dry-run  # 只填表不提交，生成截图
   ```

4. **自动截图功能**
   - 每个关键步骤保存截图到 `outputs/{ep}/debug/`
   - 失败时自动保存现场截图

### 🟡 中优先级

5. **参考视频模式 (V2V)**
   - 支持上传参考视频 + 风格描述
   - 自动预处理视频尺寸（ffmpeg）

6. **向后延伸模式 (Extend)**
   - 基于已有视频继续生成
   - 保持人物和镜头语言一致

7. **统一 Skill 入口**
   - 将 `~start` / `~batch` 改为参数化的单一 skill
   - 通过参数区分单剧本/批量模式

### 🟢 低优先级

8. **Cookie 管理**
   - 自动检测 cookie 过期
   - 提供 cookie 导出工具

9. **积分优化提示**
   - 测试阶段推荐 Fast + 5s
   - 正式出片推荐 Pro + 10s

## 对比总结

| 维度 | lanshu-waytovideo | aladdin01 | 改进建议 |
|------|-------------------|-----------|---------|
| **架构** | Skill-based，单一入口 | Agent-based，多 agent 协作 | 保持 agent 架构，增加 references/ |
| **提示词** | 独立 guide，分类示例 | 混在 SKILL.md 中 | 提取到 references/，分类整理 |
| **调试** | dry-run + 截图 | trace 日志 | 增加 dry-run 和截图 |
| **模式** | T2V/I2V/V2V/Extend | T2V/I2V | 增加 V2V 和 Extend |
| **重试** | 网络重试 + 轮询 | API 重试 + 改写 | 增加浏览器操作重试 |
| **文档** | README 详细 | CLAUDE.md 详细 | 两者都很好 |

## 推荐改进优先级

1. **立即改进**（本次可做）：
   - 创建 `.claude/skills/seedance/references/` 目录
   - 提取提示词模板和示例到独立文件
   - 修正三视图生成方法（已完成）

2. **短期改进**（下次迭代）：
   - 增加 dry-run 模式
   - 增加自动截图功能
   - 增加浏览器操作重试逻辑

3. **长期改进**（功能扩展）：
   - 支持 V2V 参考视频模式
   - 支持 Extend 向后延伸模式
   - 统一 skill 入口设计

## 结论

lanshu-waytovideo 的核心优势在于：
1. **清晰的 Skill 结构**（SKILL.md + references/）
2. **实用的提示词指南**（模板 + 分类示例）
3. **完善的调试支持**（dry-run + 截图）

我们应该借鉴其 **references/ 目录结构** 和 **提示词工程方法**，同时保持我们的 **Agent Teams 架构** 和 **Trace 系统** 优势。
