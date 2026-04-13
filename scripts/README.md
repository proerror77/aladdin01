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

# Dreamina CLI
./scripts/api-caller.sh dreamina submit <payload.json>
./scripts/api-caller.sh dreamina query <submit_id>
./scripts/api-caller.sh dreamina credit
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

### ~~jimeng-web.sh~~ — 已废弃

> **注**：即梦 Web UI 模式（jimeng-web.sh）已被 Dreamina CLI 取代。
> 请使用 `dreamina` 命令进行视频生成，详见 [CLAUDE.md](../CLAUDE.md) 中的 Dreamina CLI 章节。

### concat-episode.sh — 视频拼接

将单集的所有镜次视频按顺序拼接为完整集数。

```bash
./scripts/concat-episode.sh ep01
./scripts/concat-episode.sh --project qyccan ep01
```

**依赖**：`ffmpeg`

**注意**：Seedance 有/无音轨混合拼接时，需先补静音轨再 concat，脚本已内置处理。

**项目模式输出**：
- 最终成片：`projects/{project}/outputs/{ep}/deliverables/final.mp4`
- 逐镜成片：`projects/{project}/outputs/{ep}/deliverables/shots/`
- 清单：`projects/{project}/outputs/{ep}/deliverables/manifest.json`

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

### migrate-to-v2-architecture.sh — v2.0 迁移（已归档）

已移至 `scripts/archive/`。一次性迁移脚本，v2.0 已是当前架构。

### design-generate-protagonists.sh — 主角参考图生成

`~design` skill 调用的辅助脚本，处理主角参考图的迭代审核流程。

## Python 脚本

### vectordb-manager.py — VectorDB 管理

LanceDB 语义检索数据库管理，供 `memory-agent` / `qa-agent` / `repair-agent` 使用。

```bash
python3 scripts/vectordb-manager.py --project qyccan init
python3 scripts/vectordb-manager.py --project qyccan upsert-world-model projects/qyccan/state/ontology/ep01-world-model.json
python3 scripts/vectordb-manager.py --project qyccan index-assets projects/qyccan/assets
python3 scripts/vectordb-manager.py --project qyccan search-assets "苏夜 青玉蚕 正面" --type character --n 3
python3 scripts/vectordb-manager.py --project qyccan search-entities "黑雾森林 夜晚" --type scene --n 3
python3 scripts/vectordb-manager.py --project qyccan search-relations "suye yehongyi 契约" --episode ep01 --n 3
python3 scripts/vectordb-manager.py --project qyccan upsert-state projects/qyccan/state/shot-packets/ep01-shot-01.json
python3 scripts/vectordb-manager.py --project qyccan stats
```

**环境变量**：`VECTORDB_PATH` 可覆盖默认数据库目录（默认 `state/vectordb/lancedb`）。

**在线同步约定**：
- `gen-worker` 在生成开始 / 成功 / 失败时调用 `upsert-state`
- `qa-agent` 在审计结束时调用 `upsert-state`
- `repair-agent` 在修订 shot packet 后立即调用 `upsert-state`
- `search-relations` 用于关系证据检索，支撑 `memory-agent` 两段检索和 `qa-agent` 戏剧一致性检查

### workflow-sync.py — 工作流修复与状态同步

修复 Phase 2.3 / 3.5 缺口，生成本地 fallback 分镜图，编译 shot packet，并同步状态文件。
同时会整理一层人类可读输出：`deliverables/`、`review/`、`build/raw-videos/`。

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

### design-gen-*.py — 参考图生成系列（已归档）

已移至 `scripts/archive/`，被 `design-generate-all.py` 取代。使用 `~design` skill 替代。

### gen-qyccan-assets.py — 项目资产生成（已迁移）

已移至 `projects/qyccan/scripts/`。

### test-phase6.sh — Phase 6 测试

Phase 6（Audit & Repair）的集成测试脚本。
