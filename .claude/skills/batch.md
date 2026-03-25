# ~batch — 批量剧本模式

批量处理 `script/` 目录下的所有剧本，支持并行和串行混合执行。

## 使用方式

```
~batch
```

## 执行流程

### 0. 环境变量预检

在开始前验证所有必需的环境变量：
```bash
./scripts/api-caller.sh env-check
```

如果有缺失：
```
❌ 环境变量缺失：
- ARK_API_KEY
- OPENAI_API_KEY

请设置后再运行 ~batch
```

### 1. 扫描剧本

扫描 `script/` 目录下所有 `.md` 文件。

如果没有文件：
```
script/ 目录下没有找到剧本文件。
请将剧本放入 script/ 目录（.md 格式），然后重新运行 ~batch
```

列出发现的剧本：
```
发现 {N} 个剧本：
- ep01.md
- ep02.md
- ep03.md

全部处理？(yes/no)
```

### 2. 全局配置

**选择视觉风格**（全局统一）：
```
请选择视觉风格（所有剧本统一）：
1. 写实电影感（真人短剧）
2. 国风古装
3. 现代都市
4. 动漫风格
5. 其他（请描述）
```

**选择目标媒介**：
```
请选择目标媒介：
1. 竖屏短视频（9:16）
2. 横屏视频（16:9）
3. 方形（1:1）
```

### 3. 初始化所有剧本目录

```bash
mkdir -p outputs/{ep01}/videos
mkdir -p outputs/{ep02}/videos
...
```

初始化 `state/progress.json`：
```json
{
  "version": "1.0",
  "batch_start": "{ISO8601}",
  "episodes": {
    "ep01": {"status": "pending", "current_phase": 0},
    "ep02": {"status": "pending", "current_phase": 0}
  }
}
```

### 4. Phase 1+2 并行（合规 + 视觉）

为每个剧本并行 spawn comply-agent 和 visual-agent（comply 完成后才 spawn visual）：

```
[ep01] spawn comply-agent → 完成后 spawn visual-agent
[ep02] spawn comply-agent → 完成后 spawn visual-agent
[ep03] spawn comply-agent → 完成后 spawn visual-agent
等待所有剧本的 visual-agent 完成
```

每个 agent 完成后写入独立状态文件，避免并发写入冲突。

### 🔴 批量审核点 1 — 视觉分析

所有剧本的视觉指导完成后，一次性展示：

```
所有剧本的视觉分析已完成，请逐一审核：

━━━ ep01 ━━━
outputs/ep01/visual-direction.yaml
镜次数：{N}，总时长：{X}秒

━━━ ep02 ━━━
outputs/ep02/visual-direction.yaml
镜次数：{N}，总时长：{X}秒

━━━ ep03 ━━━
...

全部确认后继续美术指导？(yes/no)
如需修改某个剧本，请输入剧本名（如 ep01）进行单独调整。
```

**单独调整流程**：
```
ep01 单独调整模式：
1. 查看并批准
2. 拒绝并修改
3. 跳过 ep01，继续处理其他剧本

请选择：
```

### 5. Phase 3 串行（美术指导）⚠️

**重要：为避免角色资产竞态条件，Phase 3 采用串行执行。**

```
[ep01] spawn design-agent → 等待完成
[ep02] spawn design-agent（自动复用 ep01 已生成的角色）→ 等待完成
[ep03] spawn design-agent（自动复用已有角色）→ 等待完成
```

串行原因：
- design-agent 需要检查 `assets/characters/images/` 中是否有已有角色
- 并行执行时多个 agent 可能同时检测到角色不存在，各自生成
- 串行确保前一个剧本生成完成后，后续剧本能正确复用

每个 design-agent 完成后写入 `state/{ep}-phase3.json`。

### 🔴 批量审核点 2 — 参考图

```
所有剧本的参考图已生成，请审核：

━━━ ep01 ━━━
outputs/ep01/art-direction-review.md
新角色：{N}，复用角色：{M}，场景：{P}

━━━ ep02 ━━━
...

全部确认后继续音色配置？(yes/no)
```

### 6. Phase 4 串行（音色配置）⚠️

**重要：为避免交互式冲突，Phase 4 采用串行执行。**

```
[ep01] spawn voice-agent → 等待完成（含用户交互）
[ep02] spawn voice-agent（自动复用 ep01 已配置的音色）→ 等待完成
[ep03] spawn voice-agent → 等待完成
```

串行原因：
- voice-agent 需要交互式询问用户选择音色
- 并行时多个 agent 同时提问，用户无法区分
- 串行确保一次只处理一个剧本的音色配置

每个 voice-agent 完成后写入 `state/{ep}-phase4.json`。

### 7. Phase 5 并行（视频生成）

所有剧本的所有镜次并行生成：

**参数提取**（每个镜次）：

| 参数 | 来源 | 说明 |
|------|------|------|
| ep | 剧本 ID | 当前剧本 |
| shot_id | shots[].shot_id | 镜次完整 ID |
| shot_index | shots[].shot_index | 镜次序号 |
| prompt | shots[].prompt | Seedance 提示词 |
| duration | shots[].duration | 时长（秒） |
| generation_mode | shots[].generation_mode | 生成模式 |
| reference_image_path | shots[].references[0].image_path | 参考图 |
| dialogue | shots[].audio | 对白内容 |
| voice_config_path | 角色音色配置 | 音色文件路径 |

```
[ep01] spawn gen-worker × N1
[ep02] spawn gen-worker × N2
[ep03] spawn gen-worker × N3
等待所有 worker 完成
```

每个 gen-worker 写入独立状态文件 `state/{ep}-shot-{N}.json`，无并发冲突。

### 8. 批量汇总报告

读取所有 `state/{ep}-shot-*.json` 文件，生成每个剧本的 `generation-report.md`：

```
批量处理完成！

━━━ 总览 ━━━
处理剧本：{N} 个
总镜次：{T}
成功：{S}
失败：{F}

━━━ 各剧本状态 ━━━
ep01：{S1}/{T1} 成功
ep02：{S2}/{T2} 成功
ep03：{S3}/{T3} 成功

失败镜次详见各剧本的 generation-report.md
```

## 并行 vs 串行策略

| 阶段 | 执行方式 | 原因 |
|------|---------|------|
| Phase 1 合规 | 并行 | 独立剧本，无共享资源 |
| Phase 2 视觉 | 并行 | 独立剧本，无共享资源 |
| Phase 3 美术 | **串行** | 跨集角色资产复用，避免竞态 |
| Phase 4 音色 | **串行** | 交互式询问用户，避免冲突 |
| Phase 5 视频 | 并行 | 每个镜次独立状态文件 |

## 单个剧本失败处理

如果某个剧本在某个阶段失败：
```
ep02 在 Phase 1 合规检测失败：剧本格式错误

选项：
1. 跳过 ep02，继续处理其他剧本
2. 终止整个批量任务

请选择：
```

选择跳过后，最终报告会标记该剧本为 `skipped`。