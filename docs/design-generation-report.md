# 参考图生成完成报告

**项目**：qyccan（《开局青玉蚕：吞噬进化吊打诸天》）
**生成时间**：2026-03-31
**风格定义**：state/qyccan-style-guide.yaml

## 生成统计

| 类别 | 计划 | 完成 | 状态 |
|------|------|------|------|
| 主角 | 4 | 4 | ✅ 完成 |
| 重要配角 | 7 | 7 | ✅ 完成 |
| 场景（含白天/晚上） | 16 | 16 | ✅ 完成 |
| **总计** | **27** | **27** | **✅ 100% 完成** |

## 主角（4/4）✅

| 角色 | 变体 | 文件 | 状态 |
|------|------|------|------|
| 苏夜 | 青玉蚕 | 苏夜-qingyucan-turnaround-v3.png | ✅ |
| 苏夜 | 碧鳞蛇 | 苏夜-bilinse-turnaround-v3.png | ✅ |
| 苏夜 | 玄冥蟒 | 苏夜-xuanmingmang-turnaround-v3.png | ✅ |
| 叶红衣 | 常态 | 叶红衣-turnaround-v3.png | ✅ |

**风格修正**：
- v1/v2 使用了"Q版可爱风格"（不符合剧本气质）
- v3 统一使用"玄幻短剧风格、半写实画风、电影级质感、反派气质"
- 所有角色使用相同的 STYLE_SUFFIX，确保风格一致

## 重要配角（7/7）✅

| 角色 | 文件 | 状态 |
|------|------|------|
| 赵无极 | 赵无极-turnaround.png | ✅ |
| 王胖子 | 王胖子-turnaround.png | ✅ |
| 叶如烟 | 叶如烟-turnaround.png | ✅ |
| 萧凡 | 萧凡-turnaround.png | ✅ 已完成（需增加超时到 120s） |
| 青儿 | 青儿-turnaround.png | ✅ |
| 戒指老爷爷 | 戒指老爷爷-turnaround.png | ✅ |
| 系统 | 系统-interface.png | ✅ |

**萧凡生成问题**：
- 原因：默认 60 秒超时对复杂三视图提示词不够
- 解决：增加 `IMAGE_GEN_MAX_TIME=120` 后成功

## 场景（16/16）✅

| 场景 | 白天 | 晚上 |
|------|------|------|
| 黑雾森林 | 黑雾森林-day.png | 黑雾森林-night.png |
| 叶家府邸 | 叶家府邸-day.png | 叶家府邸-night.png |
| 叶红衣闺房 | 叶红衣闺房-day.png | 叶红衣闺房-night.png |
| 练武场 | 练武场-day.png | 练武场-night.png |
| 擂台 | 擂台-day.png | 擂台-night.png |
| 叶家大厅 | 叶家大厅-day.png | 叶家大厅-night.png |
| 天风学院广场 | 天风学院广场-day.png | 天风学院广场-night.png |
| 聚灵阁 | 聚灵阁-day.png | 聚灵阁-night.png |

**时间变体**：每个场景生成白天和晚上两个版本，支持 visual-agent 的 `time_of_day` 字段。

## 风格一致性检查

✅ **统一风格后缀**：所有角色和场景使用相同的风格标签
```
玄幻短剧风格，半写实画风，电影级质感，
高饱和度色彩，冷暖对比光影，戏剧化打光
```

✅ **气质匹配剧本**：
- 剧本类型：玄幻爽剧、反派主角、打脸装逼
- 主角气质：霸气、痞气、反派气质、腹黑（即使是动物形态）
- 女主气质：高冷御姐、倔强、坚韧
- 配角气质：符合各自人设（傲慢、憨厚、阴险、正义等）

✅ **禁止项**：所有提示词明确禁止"Q版可爱风格、萌系风格、卡通化"

## 下一步

### 立即可做

**开始视频生成**：
```bash
~batch
```

所有参考图已完成，可以开始批量生成 10 集视频。

### 长期改进（参考 docs/improvements/design-workflow-improvement.md）

- **P1**：创建 style-agent，自动分析剧本类型并定义全局风格
- **P1**：角色档案增加 `visual_style` 字段
- **P2**：风格一致性检查（gate-agent 扩展）
- **P2**：风格模板库（config/visual-styles/）

## 文件路径

- **角色图**：`assets/characters/images/`
- **场景图**：`assets/scenes/images/`
- **风格定义**：`state/qyccan-style-guide.yaml`
- **生成脚本**：
  - `scripts/design-gen-turnarounds-v3.py`（主角）
  - `scripts/design-gen-supporting.py`（配角）
  - `scripts/design-gen-scenes.py`（场景）
  - `scripts/design-gen-xiaofan-retry.py`（萧凡重试）
