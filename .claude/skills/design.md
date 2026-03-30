---
name: design
description: 参考图全量生成。一步生成所有角色参考图（主角迭代审核 + 配角标准审核 + 路人自动过）和所有场景参考图（含时间变体）。在 ~batch 之前运行。
user_invocable: true
---

# ~design — 参考图全量生成（角色 + 场景，一步到位）

在 `~preprocess` 之后、`~batch` 之前运行。读取所有角色档案和场景档案，一步生成全部参考图。`~batch` 中不再生图，只引用。

## 使用方式

```bash
~design
~design --project jiuba
```

## 执行流程

### 1. 读取所有角色和场景

- 扫描 `assets/characters/profiles/*.yaml`，按 tier 分组（protagonist / supporting / minor）
- 扫描 `assets/scenes/profiles/*.yaml`
- 读取 `state/design-lock.json`（如果存在），跳过已锁定的条目
- 如果指定了 `--project`，只读取对应项目

### 2. 按优先级顺序生成

所有角色和场景在同一步完成，按以下顺序：

---

**阶段 A：主角（protagonist）— 迭代审核，无次数限制**

逐个处理，每个主角：

1. 读取 `appearance`（或 `forms` 中的各形态）
2. 生成三视图（正面/侧面/背面），多形态角色每个形态分别生成
3. 展示给用户审核：

```
━━━ 主角审核：{角色名}（第 {N} 轮）━━━

正面：assets/characters/images/{角色名}-front.png
侧面：assets/characters/images/{角色名}-side.png
背面：assets/characters/images/{角色名}-back.png

当前提示词：{提示词内容}

请选择：
1. 通过 — 锁定此形象
2. 不满意 — 请输入修改意见
3. 重新生成 — 相同提示词换随机种子
4. 跳过 — 稍后再处理
```

4. 通过 → 锁定，写入 `state/design-lock.json`
5. 不满意 → 调整提示词，重新生成（回到 2）
6. 重新生成 → 同提示词重新调用 API（回到 2）

---

**阶段 B：重要配角（supporting）— 标准审核，一轮修改机会**

批量生成所有配角的三视图（多形态角色每个形态分别生成），然后统一展示审核：

```
━━━ 配角审核（共 {N} 个）━━━

1. 阴阳师 — assets/characters/images/阴阳师-front.png — 通过 / 修改
2. 判官（虚影形态）— assets/characters/images/判官-default-front.png — 通过 / 修改
3. 判官（膨胀形态）— assets/characters/images/判官-膨胀-front.png — 通过 / 修改
...

输入需要修改的编号（如 "2,5"），或输入 "all" 全部通过：
```

- 全部通过 → 锁定
- 指定修改 → 用户给意见 → 重新生成一轮 → 锁定

---

**阶段 C：单集角色（minor）— 自动通过**

批量生成所有单集角色的正面图（仅 front），自动锁定，不需人工审核。

输出摘要：`{N} 个单集角色参考图已自动生成`

---

**阶段 D：场景参考图 — 含时间变体，标准审核**

从所有角色档案的 `episodes` 推断场景出现的时间段，或从场景档案的 `description` 推断。

为每个「场景 × 时间」组合生成参考图：
- `assets/scenes/images/{场景名}-night.png`
- `assets/scenes/images/{场景名}-day.png`
- 等等

统一展示审核，逻辑同阶段 B。

---

### 3. 写入锁定状态

全部完成后，写入 `state/design-lock.json`：

```json
{
  "project": "{project_name}",
  "locked_at": "{ISO8601}",
  "characters": {
    "凌霄": {
      "tier": "protagonist",
      "status": "locked",
      "rounds": 3,
      "forms": ["default"],
      "images": ["assets/characters/images/凌霄-front.png", "..."]
    },
    "判官": {
      "tier": "supporting",
      "status": "locked",
      "rounds": 1,
      "forms": ["default", "膨胀"],
      "images": ["assets/characters/images/判官-default-front.png", "..."]
    }
  },
  "scenes": {
    "清风酒吧": {
      "status": "locked",
      "variants": ["night", "day"],
      "images": ["assets/scenes/images/清风酒吧-night.png", "assets/scenes/images/清风酒吧-day.png"]
    }
  }
}
```

### 4. 输出摘要

```
━━━ 参考图全部就绪 ━━━

| 类别 | 数量 | 审核方式 |
|------|------|---------|
| 主角 | 4 个（含 0 个多形态） | 迭代审核 |
| 配角 | 28 个（含 3 个多形态） | 标准审核 |
| 路人 | 26 个 | 自动通过 |
| 场景 | 8 个（{N} 个时间变体） | 标准审核 |

所有参考图已锁定到 state/design-lock.json
现在可以运行 ~batch
```

### 5. 调用生图 API

读取 `config/api-endpoints.yaml` 获取 image_gen 配置。

```bash
./scripts/api-caller.sh image_gen generate <payload.json>
./scripts/api-caller.sh image_gen download "<image_url>" <output_path>
```

**payload.json 格式（OpenAI images 标准格式）**：
```json
{
  "model": "nano-banana-vip",
  "prompt": "角色/场景描述（英文，详细）",
  "n": 1,
  "size": "1024x1024"
}
```

> 注意：`IMAGE_GEN_API_URL` 未配置时自动 fallback 到 tuzi（`https://api.tu-zi.com/v1`），统一使用 `nano-banana-vip` 生成角色/场景参考图。

**图片命名规则：**

| 类型 | 命名 |
|------|------|
| 单形态角色三视图 | `{角色名}-front.png` / `-side.png` / `-back.png` |
| 多变体角色三视图 | `{角色名}-{variant_id}-front.png` / `-side.png` / `-back.png` |
| 单集角色正面图 | `{角色名}-front.png` |
| 场景时间变体 | `{场景名}-{time_of_day}.png` |

## 注意事项

- 主角形象是短剧的「门面」，直接影响流量，务必反复打磨
- 如果用户对某个角色始终不满意，可以 skip，后续 `~design` 会继续处理未锁定的条目
- 锁定后如需修改，删除 `state/design-lock.json` 中对应条目后重新运行 `~design`
- `~batch` 中的 Phase 3 (design-agent) 只做校验和引用，不再生图
