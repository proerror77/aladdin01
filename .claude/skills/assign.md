# ~assign — 任务分配

多人协作模式下分配剧本任务给操作者。

## 使用方式

```
~assign ep01-ep20 alice    # Producer 分配 ep01-ep20 给 alice
~assign ep41-ep60          # 操作者自己认领 ep41-ep60
~assign --list             # 查看未分配的集数
~assign --clear ep01       # 清除 ep01 的分配（释放回未分配池）
```

## 前置条件

- `state/task-board.json` 已存在（首次使用 ~assign 时自动创建）

## 执行流程

### 分配任务（~assign ep01-ep20 alice）

1. 检查 `state/task-board.json` 是否存在，不存在则创建初始结构
2. 验证集数范围格式（支持 `ep01-ep20`、`ep01,ep02,ep03`、`ep01` 单集）
3. 检查目标集数是否已被其他人锁定：
   ```
   ⚠️ 冲突：ep05 已被 bob 锁定（task-002）
   是否继续分配未锁定的集数？(yes/no)
   ```
4. 创建任务记录，写入 `state/task-board.json`
5. 输出确认：
   ```
   ✅ 任务已分配

   任务 ID: task-003
   集数: ep01-ep20（20 集）
   负责人: alice
   状态: pending

   alice 可以运行 ~batch --mine 开始处理
   ```

### 自己认领（~assign ep41-ep60）

不带用户名时，默认分配给当前操作者（从 git config user.name 读取，或询问）。

### 查看未分配（~assign --list）

```
━━━ 未分配集数 ━━━

ep21-ep40  (20 集)
ep61-ep80  (20 集)

已分配：
- ep01-ep20 → alice (task-001, 进行中)
- ep41-ep60 → bob (task-002, pending)
```

### 清除分配（~assign --clear ep01）

只有 Producer（任务创建者）或原负责人可以清除分配。

```
确认清除 ep01 的分配？(yes/no)
→ yes
✅ ep01 已释放回未分配池
```

## task-board.json 结构

```json
{
  "version": 1,
  "project": "jiuba",
  "created_at": "2026-03-27T12:00:00Z",
  "updated_at": "2026-03-27T14:30:00Z",
  "tasks": [
    {
      "id": "task-001",
      "episodes": ["jiuba-ep01", "jiuba-ep02", "...", "jiuba-ep20"],
      "owner": "alice",
      "role": "operator",
      "status": "in_progress",
      "current_phase": 3,
      "created_at": "2026-03-27T12:00:00Z",
      "updated_at": "2026-03-27T14:30:00Z"
    }
  ],
  "unassigned": ["jiuba-ep21", "...", "jiuba-ep40"]
}
```

## 任务状态

| 状态 | 含义 |
|------|------|
| pending | 已分配，未开始 |
| in_progress | 进行中 |
| completed | 已完成 |
| blocked | 被阻塞（需要帮助） |

## 权限说明

- **Producer**：可以分配、清除任何任务
- **Operator**：只能认领未分配的集数，清除自己负责的任务
- **Reviewer**：只读权限，可查看任务状态