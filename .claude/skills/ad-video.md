---
name: ad-video
description: 广告片生产工作流。先设定广告总时长，再搭广告结构、生成 storyboard、固定人物参考，最后交给 Seedance 2.0 执行并迭代素材。
user_invocable: true
---

# ~ad-video — 广告片生产工作流

广告片不要直接从文生视频开始。这个入口先把广告拆成可执行结构，再让图像模型和视频模型按导演方案执行。

## 使用方式

```bash
~ad-video --project mybrand --product "产品名" --duration 15 --cta "立即领取试用"
~ad-video --project mybrand --product "产品名" --duration 60 --ratio 9:16 --selling-point "卖点1" --selling-point "卖点2"
~ad-video --compile projects/mybrand/ads/launch/brief.yaml
```

## 必填配置

开始时必须先确定：

| 参数 | 说明 |
|------|------|
| `--project` | 项目名，写入 `projects/{project}/` |
| `--product` | 产品名 |
| `--duration` | 广告总时长。可以是 15 秒、30 秒、60 秒等，由用户当次设定 |
| `--cta` | 最后一屏行动指令 |

可选参数：

| 参数 | 说明 |
|------|------|
| `--brand` | 品牌名 |
| `--ratio` | `9:16` / `16:9` / `1:1` 等 |
| `--audience` | 目标人群 |
| `--selling-point` | 卖点，可重复 |
| `--proof` | 信任证明，可重复 |
| `--character-ref` | 固定人物参考图 URL 或本地路径 |
| `--style` | 视觉风格 |

## 工作流

### Phase 1 — 广告结构

先运行：

```bash
python3 scripts/ad-workflow.py init \
  --project "{project}" \
  --product "{product}" \
  --duration "{duration}" \
  --cta "{cta}" \
  --ratio "9:16"
```

输出：

- `projects/{project}/ads/{ad_id}/brief.yaml`
- `projects/{project}/outputs/ads/{ad_id}/ad-structure.yaml`
- `projects/{project}/state/ads/{ad_id}-phase1.json`

结构固定为 5 个广告 beat：

```text
hook → product → function → trust → cta
```

注意：`duration` 是广告总时长，不是单个 beat 时长。脚本会把 5 个 beat 映射到 Seedance 2.0 可执行的 4-15 秒 segments；15 秒广告可以是 1 个 Seedance segment，60 秒广告通常拆成 4 个 segment。

### Phase 2 — ChatGPT-image-2 Storyboard

读取：

```text
projects/{project}/outputs/ads/{ad_id}/storyboard/storyboard-prompt.md
projects/{project}/outputs/ads/{ad_id}/storyboard/tuzi-storyboard-payload.json
```

生成一张广告 storyboard，保存为：

```text
projects/{project}/outputs/ads/{ad_id}/storyboard/ad-storyboard.png
```

图里必须包含：

- 5 个镜头格
- 时间轴
- 人物动作
- 字幕/台词
- 转场逻辑
- 品牌信息

这一步不是做漂亮图，而是把广告脚本可视化。

### Phase 3 — 固定人物参考

如果用户提供 `--character-ref`，后续 Seedance payload 会把它和 storyboard 一起传入。没有外部参考时，prompt 必须要求同一真人演员外貌、服装、发型、年龄和气质贯穿全片。

广告片最怕的不是不够真实，而是每段不像同一个世界。人物、产品、品牌、字幕样式都必须稳定。

### Phase 4 — Seedance 2.0 执行

脚本会生成：

```text
projects/{project}/outputs/ads/{ad_id}/seedance-payloads/{ad_id}-seg-01.dreamina.json
projects/{project}/outputs/ads/{ad_id}/seedance-payloads/{ad_id}-seg-02.dreamina.json
...
```

逐段执行：

```bash
./scripts/api-caller.sh dreamina submit projects/{project}/outputs/ads/{ad_id}/seedance-payloads/{ad_id}-seg-01.dreamina.json
```

每段 payload 都遵守 Seedance 2.0 的 4-15 秒限制，但广告结构仍保留完整的 `hook/product/function/trust/cta`。

### Phase 5 — 素材迭代

广告片最有价值的是素材系统，不是一条片子。每次迭代只改一个维度：

- 不同开头
- 不同卖点顺序
- 不同字幕表达
- 不同人物风格
- 不同 CTA 收口

迭代项记录在 `ad-structure.yaml` 的 `iteration_slots`，不要覆盖原始结构。

## 与短剧工作流的区别

短剧工作流以 `episode / world-model / shot-packet / continuity` 为中心。

广告片工作流以 `brief / funnel / storyboard / material iteration` 为中心。它复用现有图像生成、Seedance、trace、输出目录，但不进入短剧的 `~scriptwriter → ~preprocess → ~design → ~batch` 链路。
