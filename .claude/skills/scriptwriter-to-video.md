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
    "3_build_ontology": "pending",
    "4_asset_factory": "pending",
    "5_batch": "pending"
  }
}
```

如果 `--resume`：读取已有进度文件，跳到第一个未完成的阶段。

### 阶段 1：剧本创作（~scriptwriter）

更新进度：`1_scriptwriter: "in_progress"`

执行 ~scriptwriter 的完整流程：

1. 收集创意信息（交互式或从参数获取）
2. spawn outline-agent 生成大纲
3. 🔴 **确认点 1**：大纲确认（Auto-Gate + 异步飞书审核）
   ```
   spawn gate-agent:
     checkpoint: "outline"
     target_files: [outline.md]
     scoring_config: config/scoring/auto-gate-rules.yaml

   gate-agent 评分后三种结果：
   A) ≥85 分 auto_approve → 跳过飞书，直接继续步骤 4
   B) 50-85 分 human_review → 推飞书卡片（附评分报告），session 结束等回调
   C) <50 分 auto_reject → 自动重跑 outline-agent（退回原因作为修改指令）

   飞书回调后：approve → 继续 / redo → 重做 / terminate → 终止
   ```
4. 生成角色档案和场景档案
5. spawn episode-writer-agent × N 并行生成分集剧本
6. spawn script-reviewer-agent 质量检查
7. 🔴 **确认点 1.5**（仅当 episodes > 20 时）：季度规划确认
   - 触发条件：剧本集数超过 20 集
   - 内容：outline-agent 生成的季度规划（分季结构、主线/支线分配）
   - 操作：通过/重做（附修改意见）
8. 🔴 **确认点 2**：质量报告确认（Auto-Gate + 异步飞书审核）
   ```
   spawn gate-agent:
     checkpoint: "episode_quality"
     target_files: [所有 ep*.md]
     context_files: [outline.md, review-report.md]

   同上三种结果：auto_approve / human_review / auto_reject
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
2. 提取角色档案 → `projects/{project}/assets/characters/profiles/`
3. 提取场景档案 → `projects/{project}/assets/scenes/profiles/`
4. 如果多段扫描 → 角色融合已内联到 preprocess-agent Step 2.5

完成后输出：
```
✅ 阶段 2 完成：剧本预处理

📺 共 {N} 集：script/{project}-ep01.md ... ep{N}.md
👥 角色档案：{M} 个
🏠 场景档案：{K} 个

⏭️ 自动进入阶段 3：参考图生成...
```

更新进度：`2_preprocess: "completed"`, `current_stage: 3`

### 阶段 3：本体论构建（~build-ontology — v2.0 新增）

更新进度：`3_build_ontology: "in_progress"`

自动调用 ~build-ontology：
```
~build-ontology --all
```

执行：
1. 对每个剧本，spawn ontology-builder-agent
2. 从剧本 + 角色档案 + 场景档案中提取：
   - 实体（角色变体、场景时间变体、道具状态）
   - 关系（社交、空间、因果、时间）
   - 物理规则（重力、魔法系统）
   - 叙事约束（角色能力、道具状态、知识状态）
3. 验证逻辑一致性
4. 写入 `projects/{project}/state/ontology/{ep}-world-model.json`

完成后输出：
```
✅ 阶段 3 完成：本体论构建

🧠 世界模型：{N} 个
📊 实体总数：{E} 个（角色 {C} + 场景 {S} + 道具 {P}）
🔗 关系总数：{R} 个
⚖️ 物理规则：{PR} 条
📜 叙事约束：{NC} 条

⏭️ 自动进入阶段 4：资产工厂...
```

更新进度：`3_build_ontology: "completed"`, `current_stage: 4`

### 阶段 4：资产工厂（~asset-factory — v2.0 新增）

更新进度：`4_asset_factory: "in_progress"`

自动调用 ~asset-factory：
```
~asset-factory --project {project}
```

执行：
1. 读取所有 world-model.json
2. 提取需要多视角资产的实体：
   - 角色变体（人形/兽形/鬼形等）
   - 场景时间变体（day/night/dusk/dawn）
3. 调用 NanoBanana API 生成多视角资产包：
   - 角色：front/side/back/3quarter 视角
   - 场景：styleframe/wide 视角
4. 写入 `projects/{project}/assets/packs/characters/` 和 `projects/{project}/assets/packs/scenes/`
5. 🔴 **确认点 3**：主角多视角资产确认（Auto-Gate + 异步飞书审核 — 视觉类）
   ```
   spawn gate-agent:
     checkpoint: "character_pack"
     target_files: [所有主角 pack 路径]
     context_files: [角色档案 YAML]

   gate-agent 评分（身份一致性/视角一致性/风格统一/资产质量）：
   A) ≥85 分 auto_approve → 跳过飞书，直接继续阶段 5
   B) 50-85 分 human_review → 推飞书视觉卡片（含 Web 链接 + 评分报告）
   C) <50 分 auto_reject → 自动重跑 ~asset-factory（退回原因 + 低分维度）

   飞书/Web 回调后：approve → 继续 / redo → 重做选中角色 / terminate → 终止
   ```

完成后输出：
```
✅ 阶段 4 完成：资产工厂

📦 角色资产包：{N} 个（{V} 个视角）
🏞️ 场景资产包：{M} 个（{T} 个时间变体）
💾 总文件数：{F} 张
🔒 锁定文件：state/asset-lock.json

⏭️ 自动进入阶段 5：视频生成...
```

更新进度：`4_asset_factory: "completed"`, `current_stage: 5`

### 阶段 5：视频生成（~batch）

更新进度：`5_batch: "in_progress"`

自动调用 ~batch（全自动模式）：
- `--auto-approve`：跳过 Phase 2/3 人工确认
- 自动音色匹配（batch 默认 `auto_voice_match: true`）

执行：
1. Phase 1: 合规预检（并行）
2. Phase 2: 视觉指导（并行，auto-approve）
3. Phase 3: 美术校验（并行，auto-approve）
4. Phase 3.5: Shot Packet 编译（并行，v2.0 新增）
5. Phase 4: 音色配置（并行，auto-match）
6. Phase 5: 视频生成（并行 gen-workers）
7. Phase 6: Audit & Repair（并行，v2.0 新增）

完成后输出：
```
✅ 阶段 5 完成：视频生成

📊 总览：
- 总集数：{N}
- 总镜次：{T}
- 成功：{S}
- 失败：{F}
- 审计通过：{P}
- 修复成功：{R}

📁 视频文件：projects/{project}/outputs/{ep}/videos/
```

更新进度：`5_batch: "completed"`

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
角色档案：projects/{project}/assets/characters/profiles/*.yaml
场景档案：projects/{project}/assets/scenes/profiles/*.yaml
世界模型：projects/{project}/state/ontology/{ep}-world-model.json
角色资产包：projects/{project}/assets/packs/characters/
场景资产包：projects/{project}/assets/packs/scenes/
视频文件：outputs/ep*/videos/

━━━ 可观测性 ━━━
Trace 日志：projects/{project}/state/traces/{session-id}/
运行 ~trace 查看完整执行路径
运行 ~trace --backtrack {ep} shot-{N} 诊断失败镜次

━━━ 失败镜次（如有） ━━━
运行 ~status {ep} 查看详情
```

## 确认点总结

| 确认点 | 阶段 | 类型 | 审核方式 | 可跳过？ |
|--------|------|------|---------|---------|
| 🔴 确认点 1 | 阶段 1 | text | 飞书卡片按钮 | 否 |
| 🔴 确认点 1.5 | 阶段 1 | text | 飞书卡片按钮 | 是（episodes <= 20 时跳过） |
| 🔴 确认点 2 | 阶段 1 | text | 飞书卡片按钮 | 否 |
| 🔴 确认点 3 | 阶段 4 | visual | 飞书链接 → Web 页面 | 否 |

所有确认点走异步飞书通知，session 结束等回调。审核结果（通过/重做/终止）通过 Review Server webhook 写入 `projects/{project}/state/reviews/`，Remote Trigger 唤醒新 session 继续。

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
✅ 阶段 3 本体论构建：已完成
🔄 阶段 4 资产工厂：进行中
⏳ 阶段 5 视频生成：等待

从阶段 4 继续...
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
