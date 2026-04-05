# 配置参考

本目录包含项目的所有配置文件，按功能分子目录组织。

## 目录结构

```
config/
├── platforms/           # 视频生成平台配置
├── compliance/          # 合规检测配置
├── scoring/             # 自动评分配置
├── voices/              # 音色模板
├── nanobanana/          # Nanobanana 图像生成配置（v2.0）
├── ontology/            # 本体论 schema（v2.0）
├── shot-packet/         # Shot Packet schema（v2.0）
├── ab-testing/          # A/B 测试配置
├── lark/                # 飞书集成配置
└── api-endpoints.yaml   # API 端点地址
```

## platforms/

### seedance-v2.yaml

Seedance 视频生成平台的核心配置。

| 字段 | 说明 |
|------|------|
| `default_model` | 当前使用的模型 ID |
| `models` | 可用模型列表 |
| `max_prompt_length` | 提示词最大长度（2000） |
| `prompt_formula` | 提示词格式（text\_to\_video / image\_to\_video） |
| `generation_duration` | 各模型时长范围 |
| `ratio_options` | 可用宽高比 |
| `generation_backend` | `"api"` 或 `"browser"`（切换视频生成方式） |
| `max_concurrent_workers` | 最大并发数（默认 30） |
| `browser_backend.concurrency` | 浏览器模式并行标签页数（1-3） |

## compliance/

### blocklist.yaml

敏感词表，用于合规层第一层精确匹配。

### policy-rules.yaml

LLM 语义判断规则，用于合规层第二层。定义评分维度和阈值。

### rewrite-patterns.yaml

合规改写策略：

- 暴力 → 反应镜头
- 性 → 情绪氛围
- 辱骂 → 中性冲突
- 违法细节 → 删除

## scoring/

### auto-gate-rules.yaml

Auto-Gate 自动评分配置。

| 字段 | 说明 |
|------|------|
| `auto_pass_threshold` | 自动过关阈值（默认 85） |
| `auto_reject_threshold` | 自动退回阈值（默认 50） |
| `force_human_review_after` | 连续自动过关 N 次后强制人审（默认 10） |
| `scoring_types` | 各类评分维度和权重 |

评分类型：

| 类型 | 适用场景 |
|------|---------|
| `text_scoring.outline` | 大纲确认 |
| `text_scoring.episode_quality` | 质量报告 |
| `prompt_scoring.visual_direction` | 视觉指导 |
| `visual_scoring.character_design` | 主角形象 |

## voices/

音色模板文件（YAML），每个文件定义一种音色的参数。

| 文件 | 音色 |
|------|------|
| `young-male-gentle.yaml` | 年轻男性温柔 |
| `middle-aged-male.yaml` | 中年男性 |
| `young-female-sweet.yaml` | 年轻女性甜美 |
| `young-female-cool.yaml` | 年轻女性酷 |
| `middle-aged-female.yaml` | 中年女性 |

## nanobanana/（v2.0）

### nanobanana-config.yaml

Nanobanana 图像生成 API 配置。

| 字段 | 说明 |
|------|------|
| `api.model` | 使用的模型 |
| `api.base_url` | API 基础 URL |
| `use_enhanced_prompts` | 是否启用提示词增强（默认 true） |

### prompt-enhancement-rules.yaml

提示词增强规则，定义如何自动优化图像生成提示词。

## ontology/（v2.0）

### world-model-schema.yaml

世界本体模型的 JSON Schema，定义实体（角色/场景/道具）、关系、物理规则、叙事约束的结构。

## shot-packet/（v2.0）

### shot-packet-schema.yaml

Shot Packet 的 JSON Schema，定义镜次编译后的完整数据结构。

## ab-testing/

### scoring.yaml

A/B 测试评分配置，定义 5 个评分维度及权重：

| 维度 | 权重 |
|------|------|
| 画面质量 | 0.25 |
| 场景匹配 | 0.20 |
| 角色一致 | 0.20 |
| 动作自然 | 0.20 |
| 唇形同步 | 0.15 |

### variants/

A/B 测试变体定义。每个 YAML 文件定义一种提示词变体。

| 字段 | 说明 |
|------|------|
| `transform_type: passthrough` | 直接使用原始提示词 |
| `transform_type: llm_rewrite` | LLM 按指令改写 |

新增变体只需添加 YAML 文件，无需改代码。

## lark/

### lark-config.yaml

飞书集成配置：应用信息、审核群、Review Server URL。

### card-templates/

飞书消息卡片模板（text-review、visual-review、alert）。

## api-endpoints.yaml

API 端点地址模板。只存 URL 模板，不存 Key。
