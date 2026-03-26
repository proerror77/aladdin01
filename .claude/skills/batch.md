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

Phase 2 完成后自动通过（批量模式默认 `--auto-approve`），无需人工确认。

输出日志：
```
[auto-approve] 所有剧本视觉指导自动通过
```

### 4.5 角色预扫描（Phase 3 前置）

在 Phase 3 并行执行前，先串行扫描所有剧本的 render-script，构建全局角色注册表：

```
1. 遍历所有 outputs/{ep}/render-script.md
2. 提取每个剧本中出现的角色列表
3. 去重，生成全局角色列表
4. 检查 assets/characters/images/ 中已有角色
5. 输出角色注册表到 state/character-registry.json
```

`state/character-registry.json` 格式：
```json
{
  "characters": {
    "凌霄": {"first_ep": "jiuba-ep01", "status": "pending"},
    "徐莺莺": {"first_ep": "jiuba-ep01", "status": "pending"}
  }
}
```

角色注册表的作用：
- Phase 3 并行时，每个 design-agent 读取注册表判断角色归属
- 角色的参考图由 `first_ep` 对应的 design-agent 负责生成
- 其他剧本的 design-agent 直接复用，不重复生成

### 5. Phase 3 并行（美术指导）

**有了角色注册表，Phase 3 可以安全并行。**

```
[ep01] spawn design-agent（读取 character-registry.json，生成归属本集的新角色）
[ep02] spawn design-agent（读取 character-registry.json，复用已有角色）
[ep03] spawn design-agent（读取 character-registry.json，复用已有角色）
等待所有 design-agent 完成
```

并行安全保证：
- 每个角色只由 `first_ep` 的 design-agent 生成参考图
- 其他集的 design-agent 等待该角色的参考图就绪后复用
- 场景参考图按集独立生成，无冲突

每个 design-agent 完成后写入 `state/{ep}-phase3.json`。

Phase 3 完成后自动通过（批量模式默认 `--auto-approve`），无需人工确认。

### 6. Phase 4 并行（音色配置）

**批量模式默认启用 `auto_voice_match`，无交互，可安全并行。**

```
[ep01] spawn voice-agent（auto_voice_match: true）
[ep02] spawn voice-agent（auto_voice_match: true，自动复用已有音色）
[ep03] spawn voice-agent（auto_voice_match: true）
等待所有 voice-agent 完成
```

并行安全保证：
- 自动匹配模式无用户交互，不会冲突
- 每个 voice-agent 读取 `assets/characters/voices/` 检查已有音色
- 同一角色的音色由首次遇到的 voice-agent 写入，后续复用

每个 voice-agent 完成后写入 `state/{ep}-phase4.json`。

### 7. Phase 5 视频生成

首先读取 `config/platforms/seedance-v2.yaml` 的 `generation_backend` 字段。

**backend = "api"（默认，并行）**

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

**backend = "browser"（串行，Seedance 2.0 via 即梦 Web UI）**

所有剧本的所有镜次串行生成（浏览器同时只能做一件事）：

```
for each ep in episodes:
  for each shot in ep.shots:
    spawn browser-gen-worker (shot params)
    等待完成
    等待 wait_between 秒
```

注意：browser 模式下批量处理速度远慢于 API 模式。

每个 gen-worker / browser-gen-worker 写入独立状态文件 `state/{ep}-shot-{N}.json`，无并发冲突。

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
| 角色预扫描 | 串行 | 构建全局角色注册表（轻量，仅文本扫描） |
| Phase 3 美术 | **并行** | 角色注册表保证每个角色只由一个 agent 生成 |
| Phase 4 音色 | **并行** | 自动匹配模式无交互，无冲突 |
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