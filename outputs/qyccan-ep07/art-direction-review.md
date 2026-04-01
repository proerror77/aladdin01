# 美术校验报告 - qyccan-ep07

**检测时间**: 2026-04-01
**基于**: outputs/qyccan-ep07/visual-direction.yaml
**检测内容**: visual-direction.yaml 引用的资产是否存在于 assets/packs/

---

## 角色资产检查

| 角色 | variant_id | 预期资产路径 | 存在状态 |
|------|-----------|------------|---------|
| 苏夜 | bilinse | assets/packs/characters/suye-bilinse-front.png | 存在 |
| 苏夜 | bilinse | assets/packs/characters/suye-bilinse-side.png | 存在 |
| 苏夜 | bilinse | assets/packs/characters/suye-bilinse-back.png | 存在 |
| 苏夜 | xuanming_python | assets/packs/characters/suye-xuanmingmang-front.png | 存在 |
| 苏夜 | xuanming_python | assets/packs/characters/suye-xuanmingmang-side.png | 存在 |
| 苏夜 | xuanming_python | assets/packs/characters/suye-xuanmingmang-back.png | 存在 |
| 叶红衣 | default | assets/packs/characters/yehongyi-default-front.png | 存在 |
| 叶红衣 | default | assets/packs/characters/yehongyi-default-side.png | 存在 |
| 叶如烟 | default | assets/packs/characters/yeruyan-default-front.png | 缺失 |
| 双头魔狼 | default/berserk | assets/packs/characters/shuangtou-molang-front.png | 缺失 |
| 长老席 | default | assets/packs/characters/elders-default-front.png | 缺失 |

---

## 场景资产检查

| 场景 | time_of_day | 预期资产路径 | 存在状态 |
|------|------------|------------|---------|
| 擂台 | day | assets/packs/scenes/arena-day.png | 缺失 |

---

## 道具资产检查

| 道具 | 预期资产路径 | 存在状态 |
|------|------------|---------|
| 狂暴丹（红色珠子） | assets/packs/props/kuangbao-dan.png | 缺失 |

---

## 汇总

- **完整资产**: 6 项（苏夜全部 variant 已完整）
- **缺失资产**: 6 项（叶如烟、双头魔狼、长老席、擂台场景、道具）
- **影响评估**: 苏夜为核心角色，其资产完整，主线镜次不受影响。缺失资产为配角和场景图，可使用 text2video 模式降级处理或补图后重跑。

---

## 建议

- shot-01 ~ shot-04、shot-10：涉及叶如烟/双头魔狼，建议补充参考图
- shot-09、shot-12：苏夜玄冥蟒形态，参考图完整，重点镜次可优先保障
- 缺失场景图（擂台 day）：建议补充 assets/packs/scenes/arena-day.png

---

## 美术校验状态

通过（降级）- 主角苏夜资产完整，配角资产缺失，视频生成可进行，建议补图提升一致性
