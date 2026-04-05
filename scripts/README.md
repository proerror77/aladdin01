# Scripts 参考

本目录包含项目的所有 Shell 和 Python 脚本。

## Shell 脚本

### api-caller.sh — 统一 API 调用

核心脚本，封装所有外部 API 调用。

```bash
# Seedance 视频生成（火山方舟）
./scripts/api-caller.sh seedance create <payload.json>
./scripts/api-caller.sh seedance status <task_id>
./scripts/api-caller.sh seedance download <video_url> <output_file>

# 图像生成
./scripts/api-caller.sh image_gen generate <payload.json>
./scripts/api-caller.sh image_gen download <image_url> <output_file>

# OpenAI Moderation API（合规检测）
./scripts/api-caller.sh moderation check-file <text_file>

# Tuzi LLM / 图像
./scripts/api-caller.sh tuzi chat <payload.json>
./scripts/api-caller.sh tuzi image <payload.json>
./scripts/api-caller.sh tuzi models

# 环境检查
./scripts/api-caller.sh env-check

# Trace 摘要
./scripts/api-caller.sh trace-summary <session_dir>

# 即梦 Web UI（浏览器模式）
./scripts/api-caller.sh jimeng-web setup
```

**环境变量**：`ARK_API_KEY`、`TUZI_API_KEY`、`IMAGE_GEN_API_URL`、`IMAGE_GEN_API_KEY`、`OPENAI_API_KEY`

**超时配置**：连接 10s、Seedance 300s、图像生成 60s、Moderation 30s、下载 600s

### nanobanana-caller.sh — Nanobanana API 调用（v2.0）

资产工厂图像生成（角色定妆包、场景 styleframe、道具包）。

```bash
./scripts/nanobanana-caller.sh generate "<prompt>"
./scripts/nanobanana-caller.sh generate "<prompt>" output.png
```

**环境变量**：`TUZI_API_KEY` 或 `NANOBANANA_API_KEY`

**配置**：`config/nanobanana/nanobanana-config.yaml`

### jimeng-web.sh — 即梦 Web UI 浏览器操作

通过 Actionbook CLI + CDP 操作即梦 Web UI 生成视频。

```bash
./scripts/jimeng-web.sh setup                  # 首次登录
./scripts/jimeng-web.sh submit <payload.json>  # 提交任务
./scripts/jimeng-web.sh download <output.mp4>  # 下载视频
```

**依赖**：`actionbook` (>= 0.6.0)、`jq`、`python3`、`pip: websockets`

### concat-episode.sh — 视频拼接

将单集的所有镜次视频按顺序拼接为完整集数。

```bash
./scripts/concat-episode.sh ep01
```

**依赖**：`ffmpeg`

**注意**：Seedance 有/无音轨混合拼接时，需先补静音轨再 concat，脚本已内置处理。

### trace.sh — Agent Trace Log 写入

供 Agent 调用，写入结构化事件到 JSONL 文件。

```bash
./scripts/trace.sh <session-id> <trace-file> <step> [json-detail]

# 示例
./scripts/trace.sh batch-20260329-143000 session session_start '{"type":"batch"}'
./scripts/trace.sh batch-20260329-143000 ep01-phase1-trace read_input '{"input":"script/ep01.md"}'
```

**输出**：`state/traces/{session-id}/{trace-file}.jsonl`

### notify.sh — 飞书通知

发送飞书审核卡片和告警通知。

```bash
./scripts/notify.sh review <review-state-file>
./scripts/notify.sh alert <project> <title> <detail> [trace_url]
```

**环境变量**：`LARK_APP_ID`、`LARK_APP_SECRET`、`REVIEW_SERVER_URL`

**依赖**：`lark-cli`、`jq`

### migrate-to-v2-architecture.sh — v2.0 迁移

将 v1.0 状态文件和配置迁移到 v2.0 架构。一次性使用。

### design-generate-protagonists.sh — 主角参考图生成

`~design` skill 调用的辅助脚本，处理主角参考图的迭代审核流程。

## Python 脚本

### vectordb-manager.py — VectorDB 管理

LanceDB 语义检索数据库管理，供 `memory-agent` 使用。

```bash
python3 scripts/vectordb-manager.py init
python3 scripts/vectordb-manager.py index-assets projects/qyccan/assets
python3 scripts/vectordb-manager.py search-assets "苏夜 青玉蚕 正面" --type character --n 3
python3 scripts/vectordb-manager.py search-entities "黑雾森林 夜晚" --type scene --n 3
python3 scripts/vectordb-manager.py stats
```

### workflow-sync.py — 工作流修复与状态同步

修复 Phase 2.3 / 3.5 缺口，生成本地 fallback 分镜图，编译 shot packet，并同步状态文件。

```bash
python3 scripts/workflow-sync.py --project qyccan --episode ep01
python3 scripts/workflow-sync.py --project qyccan --episode ep01 --sync-vectordb
python3 scripts/workflow-sync.py --project qyccan --all-output-episodes
```

### design-generate-all.py — 全量参考图生成

`~design` skill 的主脚本，处理角色和场景参考图的批量生成。

### xlsx-to-script.py — Excel 转剧本

将 Excel 格式的剧本转换为 Markdown 格式。

```bash
python3 scripts/xlsx-to-script.py input.xlsx output_dir/
```

### compare_faces.py / compare_backgrounds.py — 图像对比

角色/场景参考图的相似度对比工具，用于一致性检查。

### design-gen-*.py — 参考图生成系列

| 脚本 | 用途 |
|------|------|
| `design-gen-protagonists.py` | 主角参考图 |
| `design-gen-supporting.py` | 配角参考图 |
| `design-gen-scenes.py` | 场景参考图 |
| `design-gen-turnarounds.py` | 角色三视图（v1） |
| `design-gen-turnarounds-v2.py` | 角色三视图（v2，增强） |
| `design-gen-turnarounds-v3.py` | 角色三视图（v3，最新） |

### gen-qyccan-assets.py — 项目资产生成

特定项目的资产批量生成脚本。

### test-phase6.sh — Phase 6 测试

Phase 6（Audit & Repair）的集成测试脚本。
