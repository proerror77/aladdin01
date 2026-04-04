# ~status — 进度查看

查看当前所有剧本的生产进度。

## 使用方式

```
~status                    # 全局进度总览
~status ep01              # 查看特定剧本的详细进度
~status --mine            # 只查看分配给我的剧本进度
~status alice             # 查看某人的剧本进度
```

## 状态文件结构

每个 agent 写入独立状态文件，避免并发写入冲突：
- `state/progress.json` — 索引文件（只读汇总）
- `projects/{project}/state/{ep}-phase{N}.json` — 各阶段状态
- `projects/{project}/state/{ep}-shot-{N}.json` — 各镜次状态

## 执行流程

### 无参数（总览）

1. 读取 `state/progress.json` 获取剧本列表
2. 遍历每个剧本，读取其各阶段状态文件

状态文件读取优先级：
1. `projects/{project}/state/{ep}-phase4.json` 存在且完成 → 检查 shot 文件判断 Phase 5 进度
2. `projects/{project}/state/{ep}-phase4.json` → Phase 4 状态
3. `projects/{project}/state/{ep}-phase3.json` → Phase 3 状态
4. `projects/{project}/state/{ep}-phase2.json` → Phase 2 状态
5. `projects/{project}/state/{ep}-phase1.json` → Phase 1 状态

**注意**：Phase 5 没有独立的 `phase5.json`，进度通过汇总 `projects/{project}/state/{ep}-shot-*.json` 计算：
- 已完成镜次数 / 总镜次数（来自 phase2.json 的 data.shot_count）

**A/B 模式检测**：如果存在 `projects/{project}/state/{ep}-shot-*-ab-result.json` 文件，说明本集使用了 A/B 模式。
此时 Phase 5 进度改为汇总 `-a.json` 和 `-b.json` 文件（各变体独立计数），并额外显示评分进度：
```
ep01  [████████░░] 80%  Phase 5: A/B 视频生成中 (16/22 变体完成)
                        A/B 评分：5/11 镜次已评分
```

输出：

```
━━━ 生产进度总览 ━━━

ep01  [████████░░] 80%  Phase 5: 视频生成中 (8/10 完成)
ep02  [██████░░░░] 60%  Phase 4: 音色配置完成，等待确认
ep03  [████░░░░░░] 40%  Phase 3: 美术校验中

阶段说明：
Phase 1 合规预检 → Phase 2 视觉指导 → Phase 3 美术校验 → Phase 4 音色配置 → Phase 5 视频生成
```

### 按人查看（~status --mine 或 ~status alice）

**~status --mine**：只显示分配给当前用户的剧本进度。

1. 读取 `state/task-board.json`，找到 `assigned_to` 为当前用户的任务
2. 提取任务包含的集数列表
3. 对每个集数，读取状态文件并计算进度
4. 输出格式同总览，但只显示分配给自己的剧本

**~status alice**：查看指定用户的剧本进度。

1. 读取 `state/task-board.json`，找到 `assigned_to` 为 `alice` 的任务
2. 提取任务包含的集数列表
3. 对每个集数，读取状态文件并计算进度
4. 输出格式：

```
━━━ alice 的进度 ━━━

ep01  [████████░░] 80%  Phase 5: 视频生成中 (8/10 完成)
ep02  [██████░░░░] 60%  Phase 4: 音色配置完成，等待确认

总计：2 个剧本，平均进度 70%
```

### 带参数（单剧本详情）

```
~status ep01
```

1. 读取所有 `state/ep01-phase*.json` 文件
2. 读取所有 `state/ep01-shot-*.json` 文件
3. 汇总展示

输出：

```
━━━ ep01 详细进度 ━━━

✅ Phase 1 合规预检    改写点：3 处
✅ Phase 2 视觉指导    镜次数：12
✅ Phase 3 美术校验    新角色：2，复用：1，场景：3
✅ Phase 4 音色配置    角色：3
🔄 Phase 5 视频生成    进行中

镜次状态：
shot-01  ✅ 完成（0次重试）
shot-02  ✅ 完成（2次重试）
shot-03  🔄 生成中
shot-04  ⏳ 等待
...
shot-10  ❌ 失败（5次重试 + 3轮改写）

输出目录：outputs/ep01/videos/
```

## 进度百分比计算

| 阶段完成 | 百分比 |
|---------|--------|
| Phase 1 完成 | 20% |
| Phase 2 完成 | 40% |
| Phase 3 完成 | 60% |
| Phase 4 完成 | 80% |
| Phase 5 完成 | 100% |

Phase 5 的细分进度 = 80% + (已完成镜次数 / 总镜次数) × 20%

## 阶段状态说明

| 状态 | 含义 |
|------|------|
| pending | 未开始（无状态文件） |
| in_progress | 进行中 |
| awaiting_review | 等待人工确认 |
| generating | 视频生成中（仅 Phase 5） |
| completed | 已完成 |
| failed | 失败 |

## 字段映射表

| 状态文件 | 读取字段 |
|---------|---------|
| {ep}-phase1.json | data.rewrites_count |
| {ep}-phase2.json | data.shot_count, data.total_duration |
| {ep}-phase3.json | data.new_characters, data.reused_characters, data.scenes |
| {ep}-phase4.json | data.voice_count |
| {ep}-shot-{N}.json | status, original_retries, rewrite_rounds |

## 多人协作模式

### 按人查看（~status --mine 或 ~status alice）

1. 读取 `state/task-board.json`
2. 筛选属于指定用户的剧本
3. 只展示这些剧本的进度

输出：
```
━━━ alice 的进度 ━━━

ep01-ep20  [████████░░] 80%  Phase 5: 视频生成中 (160/200)
ep41-ep60  [████░░░░░░] 40%  Phase 3: 美术校验完成

━━━ 摘要 ━━━
负责：40 集
完成：0 集
进行中：2 组
```