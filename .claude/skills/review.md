# ~review — 人工审核

在人工确认点查看和审核当前阶段的产出。

## 模式说明

`~review` 有两种工作模式，取决于是否配置了飞书（Lark）：

**终端模式**（未配置 `LARK_APP_ID`）：
- `~review` → 显示待审核列表
- `~review approve` → 批准当前待审核项
- `~review reject {ep}` → 拒绝并附原因

**Lark 模式**（已配置 `LARK_APP_ID` + `LARK_APP_SECRET`）：
- 审核通过飞书卡片进行，`~review approve/reject` 在此模式下**无效**
- `~review` → 只读，显示当前待审核状态和飞书卡片链接
- 实际审核操作请在飞书中点击卡片按钮完成

## 使用方式

```
~review                 # 查看当前等待审核的内容
~review ep01            # 查看特定剧本的审核内容
~review approve         # 批准当前所有等待审核的内容
~review approve ep01    # 批准特定剧本
~review reject ep01     # 拒绝，需要修改后重新审核
~review revise ep01     # 进入修改模式（允许编辑输出文件）
```

## 状态文件结构

检查待审核内容时读取以下状态文件：
- `projects/{project}/state/{ep}-phase2.json` — 视觉指导状态（status: awaiting_review）
- `projects/{project}/state/{ep}-phase3.json` — 美术指导状态（status: awaiting_review）

## 执行流程

### ~review（查看待审核内容）

扫描 `state/` 目录，找出所有 `{ep}-phase{N}.json` 中 `status: awaiting_review` 的阶段。

**无待审核内容时**：
```
当前没有待审核的内容。
```

**视觉指导待审核**：
```
━━━ 待审核：视觉指导 (Phase 2) ━━━

ep01 — outputs/ep01/visual-direction.yaml
  镜次数：12，总时长约 96 秒
  [查看详情请打开文件]

ep02 — outputs/ep02/visual-direction.yaml
  镜次数：8，总时长约 64 秒

输入 '~review approve' 批准全部，或 '~review approve ep01' 单独批准
输入 '~review reject ep01' 拒绝并要求修改
```

**美术指导待审核**：
```
━━━ 待审核：参考图 (Phase 3) ━━━

ep01 — outputs/ep01/art-direction-review.md
  角色参考图：projects/{project}/assets/characters/images/
  场景参考图：projects/{project}/assets/scenes/images/

输入 '~review approve' 批准全部
```

### ~review approve（批准）

更新对应状态文件：
- `projects/{project}/state/{ep}-phase{N}.json` 中 `status: awaiting_review` → `status: completed`
- `state/progress.json` 中 `{ep}.current_phase` 更新

```
已批准 ep01 的视觉指导，继续 Phase 3 美术指导阶段...
```

### ~review approve {ep}（单独批准）

只批准指定剧本，其他剧本继续等待。

```
已批准 ep01 的 {阶段名}，ep01 继续下一阶段。
ep02、ep03 仍在等待审核。
```

### ~review reject {ep}（拒绝）

标记该阶段需要修改：

```
ep01 的视觉指导已标记为需修改。

您可以：
1. 手动编辑 outputs/ep01/visual-direction.yaml
2. 运行 '~review revise ep01' 进入修改模式
3. 修改完成后运行 '~review approve ep01' 批准
```

更新状态文件：
- `projects/{project}/state/{ep}-phase{N}.json` 中 `status: awaiting_review` → `status: needs_revision`

### ~review revise {ep}（修改模式）

进入交互式修改流程：

```
进入 ep01 视觉指导修改模式。

当前待修改文件：outputs/ep01/visual-direction.yaml

选项：
1. 显示当前内容摘要
2. 调整特定镜次
3. 重新运行 visual-agent
4. 完成修改，标记为待审核

请选择（1-4）：
```

**选项说明**：
1. 显示当前内容摘要 — 展示镜次列表和关键信息
2. 调整特定镜次 — 选择镜次进行编辑（时长、提示词等）
3. 重新运行 visual-agent — spawn visual-agent 重新生成
4. 完成修改 — 将状态改回 `awaiting_review`

## 批量模式下

批量模式有专门的审核点：

**批量审核点 1 — 视觉分析完成后**：
```
所有剧本的视觉分析已完成，请逐一审核：

━━━ ep01 ━━━
outputs/ep01/visual-direction.yaml
镜次数：12，总时长：96秒

━━━ ep02 ━━━
outputs/ep02/visual-direction.yaml
镜次数：8，总时长：64秒

━━━ ep03 ━━━
...

全部确认后继续美术指导？(yes/no)
如需修改某个剧本，请输入剧本名（如 ep01）进行单独调整。
```

输入 `ep01` 后进入单独调整流程：
```
ep01 单独调整模式：
1. 查看并批准
2. 拒绝并修改
3. 跳过 ep01，继续处理其他剧本

请选择：
```

## 字段映射表

| 阶段 | 状态文件 | 待审核文件 |
|------|---------|-----------|
| Phase 2 视觉指导 | {ep}-phase2.json | projects/{project}/outputs/{ep}/visual-direction.yaml |
| Phase 3 美术指导 | {ep}-phase3.json | projects/{project}/outputs/{ep}/art-direction-review.md |