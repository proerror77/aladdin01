# Trace Protocol — Agent 可观测性事件格式规范

本文档定义 Agent Trace Log 的事件格式，供所有 agent 和 skill 参考。

## 概述

每次 `~start` / `~batch` 运行产生一个 session，所有 trace 事件存储在 `state/traces/{session-id}/` 下。

- **格式**：JSONL（每行一个 JSON 对象）
- **写入方式**：`./scripts/trace.sh <session-id> <trace-file> <step> [json-detail]`
- **并行安全**：每个 agent 写独立文件，无共享写入

## Session ID 命名

`{type}-{YYYYMMDD}-{HHMMSS}`

| type | 触发来源 |
|------|---------|
| `start` | `~start` 单剧本模式 |
| `batch` | `~batch` 批量模式 |

示例：`batch-20260329-143000`、`start-20260329-150000`

## 文件结构

```
state/traces/{session-id}/
├── session.jsonl                # Session 级事件（team-lead 写）
├── {ep}-phase{N}-trace.jsonl    # Agent 步骤日志（各 agent 写）
├── {ep}-shot-{N}-trace.jsonl    # Shot 生成日志（gen-worker 写）
└── summary.md                   # LLM 生成的摘要报告
```

## 公共字段

每条事件必含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `ts` | string | ISO8601 UTC 时间戳（由 trace.sh 自动添加） |
| `step` | string | 步骤名称 |

## Session 事件（session.jsonl）

由 team-lead（~start / ~batch skill）写入。

### session_start

```json
{"ts":"...","step":"session_start","type":"batch","episodes":["ep01","ep02"],"config":{"visual_style":"写实电影感","ratio":"9:16","backend":"api"}}
```

### spawn

```json
{"ts":"...","step":"spawn","agent":"comply-agent","ep":"ep01","phase":1}
```

### complete

```json
{"ts":"...","step":"complete","agent":"comply-agent","ep":"ep01","phase":1,"duration_s":9,"summary":"合规通过，改写2处"}
```

### error

```json
{"ts":"...","step":"error","agent":"gen-worker","ep":"ep01","shot":"shot-03","phase":5,"error":"API rejected: content policy"}
```

### session_end

```json
{"ts":"...","step":"session_end","duration_s":300,"stats":{"total_shots":30,"succeeded":28,"failed":2}}
```

## Agent 步骤事件

### comply-agent（Phase 1）

文件：`{ep}-phase1-trace.jsonl`

| step | 必含字段 | 说明 |
|------|---------|------|
| `read_input` | `input`, `size` | 读取剧本文件 |
| `layer1_scan` | `paragraphs`, `hits`, `keywords` | 关键词扫描结果 |
| `layer2_llm` | `scores`{violence,sexual,hate,self_harm}, `decision` | LLM 语义评分 |
| `rewrite` | `count`, `changes`[{from,to,reason}] | 改写操作 |
| `layer3_moderation` | `flagged`, `max_score` | OpenAI Moderation 结果 |
| `write_output` | `files` | 写入的产出文件列表 |

### visual-agent（Phase 2）

文件：`{ep}-phase2-trace.jsonl`

| step | 必含字段 | 说明 |
|------|---------|------|
| `read_input` | `render_script`, `platform_config` | 读取输入 |
| `analyze_scenes` | `scene_count`, `scenes` | 场景分析 |
| `generate_shots` | `shot_count`, `total_duration` | 镜次拆分 |
| `assign_refs` | `characters`[{name,variant_id}], `scenes`[{name,time_of_day}] | 参考图分配 |
| `assemble_prompts` | `avg_prompt_len`, `max_prompt_len` | 提示词组装统计 |
| `write_output` | `files` | 写入的产出文件列表 |

### design-agent（Phase 3）

文件：`{ep}-phase3-trace.jsonl`

| step | 必含字段 | 说明 |
|------|---------|------|
| `read_input` | `visual_direction`, `design_lock` | 读取输入 |
| `check_characters` | `total`, `found`, `missing`[] | 角色图校验 |
| `check_scenes` | `total`, `found`, `missing`[] | 场景图校验 |
| `write_output` | `files`, `all_valid` | 校验结果 |

### voice-agent（Phase 4）

文件：`{ep}-phase4-trace.jsonl`

| step | 必含字段 | 说明 |
|------|---------|------|
| `read_input` | `render_script`, `visual_direction` | 读取输入 |
| `extract_characters` | `count`, `characters`[] | 提取有对白的角色 |
| `match_voices` | `matches`[{character,voice_source,confidence}] | 音色匹配决策 |
| `write_configs` | `configs`[{character,path}] | 写入音色配置 |
| `write_output` | `files` | 写入的产出文件列表 |

### gen-worker（Phase 5 — API 模式）

文件：`{ep}-shot-{N}-trace.jsonl`

| step | 必含字段 | 说明 |
|------|---------|------|
| `start` | `prompt`(前100字), `duration`, `mode`, `ref_image` | 开始生成 |
| `api_submit` | `task_id`, `api_call` | 提交 API 请求 |
| `api_poll` | `task_id`, `status`, `poll_count`, `elapsed_s` | 轮询结果 |
| `api_result` | `status`, `rejection`(如失败) | API 返回结果 |
| `retry` | `attempt`, `strategy`(same_prompt/rewrite) | 重试 |
| `rewrite` | `round`, `old_prompt`(前50字), `new_prompt`(前50字), `change_reason` | 提示词改写 |
| `download` | `video_path`, `file_size` | 下载视频 |
| `complete` | `total_api_calls`, `original_retries`, `rewrite_rounds` | 成功完成 |
| `fail` | `total_api_calls`, `error`, `last_rejection` | 最终失败 |

### browser-gen-worker（Phase 5 — 浏览器模式）

文件：`{ep}-shot-{N}-trace.jsonl`

| step | 必含字段 | 说明 |
|------|---------|------|
| `start` | `prompt`(前100字), `duration`, `mode`, `ref_image` | 开始生成 |
| `browser_submit` | `submit_attempt` | 浏览器提交 |
| `browser_wait` | `elapsed_s`, `status` | 等待生成完成 |
| `browser_download` | `video_path`, `download_attempt` | 下载视频 |
| `complete` | `submit_retries`, `download_retries` | 成功完成 |
| `fail` | `error`, `submit_retries`, `download_retries` | 最终失败 |

## Backtrack 关联字段

为支持跨 phase 回溯，以下字段建立关联链：

| Phase | 写入字段 | 关联到 |
|-------|---------|--------|
| Phase 1 (comply) | `changes[].from/to` | 原始剧本 → render-script 映射 |
| Phase 2 (visual) | `assign_refs` 中的 character/scene | Phase 3 校验引用 |
| Phase 2 (visual) | `assemble_prompts` | Phase 5 生成使用的 prompt |
| Phase 5 (gen) | `prompt` | 可回溯到 Phase 2 的 visual-direction.yaml |
| Phase 5 (gen) | `rejection` | 可回溯到 Phase 1 的改写决策 |

## LLM 摘要

Session 结束后调用 `./scripts/api-caller.sh trace-summary <session-dir>` 生成 `summary.md`。

摘要包含：
1. **路径标签**：每集的 phase 链路 + 关键指标
2. **关键决策点**：影响最终结果的 agent 决策
3. **异常标记**：失败、高重试、改写等
4. **质量评估**：成功率、重试率、合规覆盖率
5. **优化建议**：基于异常模式的改进方向
