# ~scriptwriter-to-video — 一键从创意到视频

从创意发想到视频输出的完整 E2E 流程，自动串联 ~scriptwriter → ~preprocess → ~design → ~batch。

## 使用方式

```bash
~scriptwriter-to-video --idea "你的创意" --episodes 15 --length short
~scriptwriter-to-video                           # 交互式
~scriptwriter-to-video --resume {project-name}   # 断点续传
```

### 参数

| 参数 | 说明 |
|------|------|
| `--idea <text>` | 创意描述（可选，不提供则交互式输入） |
| `--episodes <N>` | 目标集数（默认 10） |
| `--length <mode>` | 每集时长模式：short/medium/long（默认 short） |
| `--genre <type>` | 故事类型：romance/mystery/scifi/fantasy/comedy（可选） |
| `--style <ref>` | 参考风格（可选） |
| `--resume <project>` | 断点续传，从上次中断的阶段继续 |

## 执行流程

### 0. 初始化

生成项目名（从 idea 推断或询问用户）。

初始化 E2E 进度文件 `state/e2e-progress.json`：
```json
{
  "project_name": "{project}",
  "current_stage": 1,
  "started_at": "{ISO8601}",
  "stages": {
    "1_scriptwriter": "pending",
    "2_preprocess": "pending",
    "3_design": "pending",
    "4_batch": "pending"
  }
}
```

如果 `--resume`：读取已有进度文件，跳到第一个未完成的阶段。

### 阶段 1：剧本创作（~scriptwriter）

更新进度：`1_scriptwriter: "in_progress"`

执行 ~scriptwriter 的完整流程：

1. 收集创意信息（交互式或从参数获取）
2. spawn outline-agent 生成大纲
3. 🔴 **确认点 1**：大纲确认
   ```
   大纲已生成：outputs/scriptwriter/{project}/outline.md
   确认后继续？(yes/no/revise)
   ```
4. 生成角色档案和场景档案
5. spawn episode-writer-agent × N 并行生成分集剧本
6. 🔴 **确认点 2**（每 5 集）：剧本确认
7. spawn script-reviewer-agent 质量检查
8. 格式转换：
   - 合并分集剧本为完整文件
   - **写入 `raw/{project}-complete.md`**（供 ~preprocess 直接读取）
   - 同时保留 `outputs/scriptwriter/{project}/complete.md`

完成后输出：
```
✅ 阶段 1 完成：剧本创作

📁 产出文件：
- 完整剧本：raw/{project}-complete.md
- 分集剧本：outputs/scriptwriter/{project}/episodes/ep*.md
- 角色档案：outputs/scriptwriter/{project}/characters/*.yaml
- 场景档案：outputs/scriptwriter/{project}/scenes/*.yaml

⏭️ 自动进入阶段 2：剧本预处理...
```

更新进度：`1_scriptwriter: "completed"`, `current_stage: 2`

### 阶段 2：剧本预处理（~preprocess）

更新进度：`2_preprocess: "in_progress"`

自动调用 ~preprocess，无需用户操作：
```
~preprocess raw/{project}-complete.md {project}
```

执行：
1. preprocess-agent 拆分为标准分集剧本
2. 提取角色档案 → `assets/characters/profiles/`
3. 提取场景档案 → `assets/scenes/profiles/`
4. 如果多段扫描 → merge-agent 角色融合

完成后输出：
```
✅ 阶段 2 完成：剧本预处理

📺 共 {N} 集：script/{project}-ep01.md ... ep{N}.md
👥 角色档案：{M} 个
🏠 场景档案：{K} 个

⏭️ 自动进入阶段 3：参考图生成...
```

更新进度：`2_preprocess: "completed"`, `current_stage: 3`

### 阶段 3：参考图生成（~design）

更新进度：`3_design: "in_progress"`

自动调用 ~design：
```
~design --project {project}
```

执行：
1. 读取所有角色/场景档案
2. 按优先级生成参考图（protagonist 迭代 → supporting 审核 → minor 自动）
3. 🔴 **确认点 3**：主角形象确认（~design 内置的审核流程）
4. 生成场景参考图（含时间变体）
5. 锁定 `state/design-lock.json`

完成后输出：
```
✅ 阶段 3 完成：参考图生成

🎨 角色参考图：{N} 张
🏞️ 场景参考图：{M} 张
🔒 锁定文件：state/design-lock.json

⏭️ 自动进入阶段 4：视频生成...
```

更新进度：`3_design: "completed"`, `current_stage: 4`

### 阶段 4：视频生成（~batch）

更新进度：`4_batch: "in_progress"`

自动调用 ~batch（全自动模式）：
- `--auto-approve`：跳过 Phase 2/3 人工确认
- 自动音色匹配（batch 默认 `auto_voice_match: true`）

执行：
1. Phase 1: 合规预检（并行）
2. Phase 2: 视觉指导（并行，auto-approve）
3. Phase 3: 美术校验（并行，auto-approve）
4. Phase 4: 音色配置（并行，auto-match）
5. Phase 5: 视频生成（并行 gen-workers）

完成后输出：
```
✅ 阶段 4 完成：视频生成

📊 总览：
- 总集数：{N}
- 总镜次：{T}
- 成功：{S}
- 失败：{F}

📁 视频文件：outputs/{ep}/videos/
```

更新进度：`4_batch: "completed"`

### 最终汇总

```
🎬 E2E 流程完成！从创意到视频，全程自动。

━━━ 项目总览 ━━━
项目名：{project}
创意：{idea 前 50 字}...
总集数：{N} 集
总镜次：{T}
成功率：{S}/{T} ({percent}%)
总耗时：{duration}

━━━ 产出文件 ━━━
剧本大纲：outputs/scriptwriter/{project}/outline.md
分集剧本：script/{project}-ep*.md
角色档案：assets/characters/profiles/*.yaml
场景档案：assets/scenes/profiles/*.yaml
角色参考图：assets/characters/images/
场景参考图：assets/scenes/images/
视频文件：outputs/ep*/videos/

━━━ 可观测性 ━━━
Trace 日志：state/traces/{session-id}/
运行 ~trace 查看完整执行路径
运行 ~trace --backtrack {ep} shot-{N} 诊断失败镜次

━━━ 失败镜次（如有） ━━━
运行 ~status {ep} 查看详情
```

## 确认点总结

| 确认点 | 阶段 | 内容 | 可跳过？ |
|--------|------|------|---------|
| 🔴 确认点 1 | 阶段 1 | 大纲确认 | 否（影响全局方向） |
| 🔴 确认点 2 | 阶段 1 | 质量报告确认 | 否（影响剧本质量） |
| 🔴 确认点 3 | 阶段 3 | 主角形象确认 | 否（~design 内置） |

阶段 2 和阶段 4 全自动，无确认点。

## 断点续传

```bash
~scriptwriter-to-video --resume love-coffee
```

读取 `state/e2e-progress.json`，输出：
```
检查 E2E 进度：love-coffee

✅ 阶段 1 剧本创作：已完成
✅ 阶段 2 剧本预处理：已完成
🔄 阶段 3 参考图生成：进行中
⏳ 阶段 4 视频生成：等待

从阶段 3 继续...
```

## 错误处理

任何阶段失败时：
1. 更新进度文件标记当前阶段为 `failed`
2. 输出失败信息和建议
3. 提示使用 `--resume` 从失败阶段重新开始

```
❌ 阶段 2 失败：剧本预处理出错

错误：preprocess-agent 无法解析剧本格式

建议：
1. 检查 raw/{project}-complete.md 的格式
2. 手动运行 ~preprocess 修复后，运行 ~scriptwriter-to-video --resume {project}
```
