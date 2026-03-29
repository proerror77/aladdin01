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
3. 🔴 **确认点 1**：大纲确认（异步飞书审核）
   ```
   写入 state/reviews/{review-id}.json:
     type: "text", checkpoint: "outline"
     content.summary: 剧名、集数、主角、核心冲突
     content.files: [outline.md]

   调用 ./scripts/notify.sh review state/reviews/{review-id}.json
   → 飞书发送文字审核卡片（通过/重做/终止）
   → session 结束，等待回调

   回调后新 session 读取 response:
   - approve → 继续步骤 4
   - redo → 重跑 outline-agent（reason 作为修改指令）
   - terminate → 更新 e2e-progress.json 为 terminated
   ```
4. 生成角色档案和场景档案
5. spawn episode-writer-agent × N 并行生成分集剧本
6. spawn script-reviewer-agent 质量检查
7. 🔴 **确认点 2**：质量报告确认（异步飞书审核）
   ```
   同上模式：写 review state → notify → session 结束 → 等回调
   type: "text", checkpoint: "quality"
   - redo → 重跑有问题的集数（reason 指出问题）
   ```
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
3. 🔴 **确认点 3**：主角形象确认（异步飞书审核 — 视觉类）
   ```
   写入 state/reviews/{review-id}.json:
     type: "visual", checkpoint: "character"
     assets: [所有主角参考图路径]

   调用 ./scripts/notify.sh review state/reviews/{review-id}.json
   → 飞书发送视觉审核卡片（含 Web 链接）
   → 用户在 Web 页面查看图片、选中不满意的角色 → 通过/重做/终止
   → session 结束，等待回调

   回调后新 session 读取 response:
   - approve → 继续阶段 4
   - redo → 重跑 ~design（selected_items + reason 指定重做哪些角色）
   - terminate → 终止
   ```
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

| 确认点 | 阶段 | 类型 | 审核方式 | 可跳过？ |
|--------|------|------|---------|---------|
| 🔴 确认点 1 | 阶段 1 | text | 飞书卡片按钮 | 否 |
| 🔴 确认点 2 | 阶段 1 | text | 飞书卡片按钮 | 否 |
| 🔴 确认点 3 | 阶段 3 | visual | 飞书链接 → Web 页面 | 否 |

所有确认点走异步飞书通知，session 结束等回调。审核结果（通过/重做/终止）通过 Review Server webhook 写入 `state/reviews/`，Remote Trigger 唤醒新 session 继续。

重做上限：每个确认点最多 5 次（`config/lark/lark-config.yaml` 中 `max_iterations`）。

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
