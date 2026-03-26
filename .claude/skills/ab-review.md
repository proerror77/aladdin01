# ~ab-review — A/B 测试评分

对 A/B 测试生成的视频对进行人工评分，选出每个镜次的胜者。

## 使用方式

```
~ab-review              # 评分所有待评分镜次
~ab-review {ep}         # 评分特定剧本
~ab-review report {ep}  # 仅生成报告（不重新评分）
```

## 执行流程

### 1. 扫描待评分镜次

**`~ab-review report {ep}` 子命令**：如果没有任何 `state/{ep}-shot-*-ab-result.json` 文件，输出：
```
没有找到 {ep} 的 A/B 测试结果文件。请先运行 ~start --ab {ep}。
```
然后退出，不生成报告。

**评分模式**：扫描 `state/{ep}-shot-*-ab-result.json`，筛选 `scoring.scored == false` 的镜次。

如果没有待评分镜次：
```
当前没有待评分的 A/B 测试结果。
请先运行 ~start --ab 生成 A/B 视频。
```

如果 `config/ab-testing/scoring.yaml` 不存在：
```
ERROR: 找不到评分配置 config/ab-testing/scoring.yaml。请检查配置文件是否存在。
```
然后退出。

**跳过规则**：
- 任一变体 `status == failed` → 跳过评分，记录到报告「失败镜次」部分
- **两个变体均 `status == failed`** → 跳过评分，并在评分结束后额外输出：
  ```
  ⚠️  WARNING: Shot {N} 的两个变体均生成失败，该镜次将缺失于最终视频。
      请重新运行 ~start --ab 并指定该镜次重新生成。
  ```

### 2. 逐镜次评分

读取 `config/ab-testing/scoring.yaml` 获取评分维度和权重。

对每个未评分镜次，展示：

```
━━━ Shot {N} / {total} ━━━

变体 A ({variant_a_id}): outputs/{ep}/videos/shot-{N}-a.mp4
变体 B ({variant_b_id}): outputs/{ep}/videos/shot-{N}-b.mp4

提示词对比：
  A: {variant_a_prompt 前 100 字符}...
  B: {variant_b_prompt 前 100 字符}...
```

通过 AskUserQuestion 收集各维度评分（1-5 分）：
- 画面质量 — A: ___  B: ___
- 场景匹配 — A: ___  B: ___
- 角色一致 — A: ___  B: ___
- 动作自然 — A: ___  B: ___
- 唇形同步 — A: ___  B: ___（无对白镜次跳过）
- 备注（可选）

### 3. 计算加权分和胜者

**有对白镜次**（`generate_audio: true`）：使用标准权重
```
visual_quality: 0.25, scene_match: 0.20, character_consistency: 0.20,
motion_quality: 0.20, lip_sync: 0.15
```

**无对白镜次**：使用 `no_dialogue_weights`（lip_sync 权重重分配）
```
visual_quality: 0.30, scene_match: 0.25, character_consistency: 0.25, motion_quality: 0.20
```

计算：
```
weighted_a = sum(score_a[dim] * weight[dim])
weighted_b = sum(score_b[dim] * weight[dim])
```

胜者判定：
- `abs(weighted_a - weighted_b) <= winner_threshold (0.0)` → 平局，按 `tie_policy: "variant_a"` 处理
- 否则取加权分更高者

### 4. 写入 ab-result.json

更新 `state/{ep}-shot-{N}-ab-result.json` 的 `scoring` 字段：

```json
{
  "scoring": {
    "scored": true,
    "variant_a_scores": {
      "visual_quality": 4,
      "scene_match": 3,
      "character_consistency": 4,
      "motion_quality": 3,
      "lip_sync": 4
    },
    "variant_b_scores": { ... },
    "variant_a_weighted": 3.65,
    "variant_b_weighted": 4.10,
    "winner": "b",
    "notes": "B 的光影效果明显更好"
  }
}
```

### 5. 生成报告

所有镜次评分完成后，生成 `outputs/{ep}/ab-report.md`：

```markdown
# A/B 测试报告 - {ep}

## 测试配置

- 变体 A: {variant_a_id} — {variant_a_name}
- 变体 B: {variant_b_id} — {variant_b_name}
- 评分时间: {timestamp}
- 总镜次: {N}（评分: {scored}，跳过: {skipped}）

## 总览

| 指标 | 变体 A | 变体 B |
|------|--------|--------|
| 胜出镜次 | {X} | {Y} |
| 平局 | {Z} | {Z} |
| 胜率 | {X/scored}% | {Y/scored}% |
| 平均加权分 | {avg_a:.2f} | {avg_b:.2f} |

## 各维度平均分

| 维度 | 变体 A | 变体 B | 差异 |
|------|--------|--------|------|
| 画面质量 | {avg} | {avg} | {+/-diff} |
| 场景匹配 | {avg} | {avg} | {+/-diff} |
| 角色一致 | {avg} | {avg} | {+/-diff} |
| 动作自然 | {avg} | {avg} | {+/-diff} |
| 唇形同步 | {avg} | {avg} | {+/-diff} |

## 逐镜次结果

| 镜次 | 场景 | 胜者 | A 加权分 | B 加权分 | 备注 |
|------|------|------|----------|----------|------|
| shot-01 | ... | B | 3.40 | 4.10 | ... |

## 失败镜次（跳过评分）

| 镜次 | 失败变体 | 原因 |
|------|---------|------|

## 建议

基于评分数据自动生成：
- 如果变体 B 在「画面质量」维度显著优于 A（差异 > 0.5）：建议后续生成采用 {variant_b_id} 策略
- 如果某维度两者无显著差异（差异 < 0.2）：该维度提示词改写效果不明显
- 如果变体 B 整体胜率 > 60%：建议将 {variant_b_id} 设为新的 baseline
```

## 注意事项

- 评分完成后自动生成报告，无需手动触发
- `~ab-review report {ep}` 可在不重新评分的情况下重新生成报告
- 评分数据持久化在 `state/{ep}-shot-*-ab-result.json`，可随时重新生成报告
