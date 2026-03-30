# ~trace — Agent 可观测性查询

查看 agent 过程日志、session 路径标签、失败回溯诊断。

## 使用方式

```
~trace                              # 最近一次 session 的路径概览
~trace <session-id>                 # 指定 session 的路径概览
~trace <ep>                         # 某集的完整 agent 链路
~trace <ep> phase<N>                # 某集某阶段的详细步骤
~trace <ep> shot-<N>                # 某 shot 的生成追溯
~trace --backtrack <ep> shot-<N>    # 从失败 shot 反向追溯到根因
~trace --summary <session-id>       # 查看/重新生成 LLM 摘要
```

## 执行流程

### 1. 定位 Session

**无参数 / 无 session-id**：找最新的 session 目录：
```bash
ls -t state/traces/ | head -1
```

**有 session-id**：直接使用 `state/traces/{session-id}/`。

如果目录不存在：
```
❌ 未找到 trace 记录。运行 ~start 或 ~batch 后会自动记录。
```

**索引加速**：定位 session 后，先检查 `state/traces/{session-id}/index.json` 是否存在：
- 如果存在：直接从索引读取 episode/phase/shot 映射，O(1) 定位
- 如果不存在：按原有逻辑扫描 JSONL 文件，并自动生成 `index.json` 供下次使用

### 2. 路径概览（默认模式）

读取 `session.jsonl`，汇总每个 episode 的 phase 链路：

```
━━━ Session: batch-20260329-143000 ━━━
时长：5m 00s | 3 集 | 30 镜次 | 成功 28 | 失败 2

路径标签：
ep01: 合规(2改写) → 视觉(12镜次) → 校验(0缺失) → 音色(3角色) → 生成(10/12✅ 2❌)
ep02: 合规(0改写) → 视觉(8镜次) → 校验(0缺失) → 音色(2角色) → 生成(8/8✅)
ep03: 合规(1改写) → 视觉(10镜次) → 校验(0缺失) → 音色(3角色) → 生成(10/10✅)

⚠️ 异常标记：
- ep01 shot-03: API 拒绝 5次 + 改写 3轮后失败（content policy: violence）
- ep01 shot-10: 改写 2轮后成功（原始 prompt 过长）

📊 Trace 详情：state/traces/batch-20260329-143000/
```

构建方法：
1. 从 `session.jsonl` 提取所有 `complete` 事件，按 ep 分组
2. 从 `complete` 事件的 `summary` 字段提取关键指标
3. 从 `error` 事件提取异常

### 3. 单集详情（~trace ep01）

读取该集所有 trace 文件，按时间线展示：

```
━━━ ep01 Agent 链路 ━━━

14:30:01 [Phase 1] comply-agent (9s)
  ├─ read_input: script/ep01.md, 1234 字
  ├─ layer1_scan: 45 段落, 2 命中 (血腥, 自杀)
  ├─ layer2_llm: violence=3, sexual=1, hate=0, self_harm=4
  ├─ rewrite: 2 处改写
  ├─ layer3_moderation: flagged=false, max=self_harm:0.12
  └─ write_output: render-script.md, compliance-report.md

14:30:10 [Phase 2] visual-agent (50s)
  ├─ read_input: render-script.md
  ├─ analyze_scenes: 4 场景
  ├─ generate_shots: 12 镜次, 总时长 96s
  ├─ assign_refs: 3 角色 × 形态, 4 场景 × 时间
  ├─ assemble_prompts: avg 800字, max 1500字
  └─ write_output: visual-direction.yaml

...
```

### 4. 单 Phase 详情（~trace ep01 phase1）

读取 `{ep}-phase1-trace.jsonl`，展示每个步骤的完整 JSON：

```
━━━ ep01 Phase 1 详细步骤 ━━━

[14:30:01] read_input
  input: script/ep01.md
  size: 1234

[14:30:02] layer1_scan
  paragraphs: 45
  hits: 2
  keywords: ["血腥", "自杀"]

[14:30:03] layer2_llm
  scores: {violence: 3, sexual: 1, hate: 0, self_harm: 4}
  decision: "self_harm borderline，继续检查"

...
```

### 5. 单 Shot 详情（~trace ep01 shot-03）

读取 `{ep}-shot-03-trace.jsonl`：

```
━━━ ep01 shot-03 生成追溯 ━━━

[14:31:21] start
  prompt: "男子倒在血泊中，女子尖叫..."（前100字）
  duration: 8s
  mode: text_to_video

[14:31:22] api_submit (call #1)
  task_id: cgt-20260329-143122-abc

[14:31:52] api_result → FAILED
  rejection: "content policy: violence detected"

[14:31:53] retry (attempt 2, same_prompt)
...
[14:32:30] rewrite (round 1)
  old: "男子倒在血泊中..."
  new: "男子倒地不动..."
  reason: "removed violence descriptor"
...
[14:33:45] fail
  total_api_calls: 14
  error: "视频生成失败：3轮改写后仍被拒绝"
  last_rejection: "content policy: violence detected"
```

### 6. Backtrack 诊断（~trace --backtrack ep01 shot-03）

**核心功能**：从失败 shot 反向追溯到根因。

步骤：
1. 先检查 `index.json` 的 `failures` 数组，直接定位失败 shot 的 trace 文件（O(1)）
   - 如果 `index.json` 不存在，按原有逻辑扫描 JSONL 文件
2. 读取 `{ep}-shot-03-trace.jsonl`，获取失败原因和最终 prompt
3. 读取 `{ep}-phase2-trace.jsonl`，找到 shot-03 的 prompt 来源（assign_refs、assemble_prompts）
4. 读取 `{ep}-phase1-trace.jsonl`，检查是否有改写操作影响了该段内容
5. 对比原文 → 改写后 → prompt → API 拒绝，构建因果链

输出格式：

```
━━━ 回溯诊断：ep01 shot-03 ━━━

❌ Phase 5 (gen-worker): 失败
   最终拒绝：content policy: violence detected
   重试：5次原始 + 3轮改写 = 14次 API 调用
   最终 prompt: "男子倒在血泊中，女子尖叫..."

⬆️ Phase 2 (visual-agent): prompt 来源
   shot-03 prompt 基于 render-script.md 第 15-18 行
   生成模式: text_to_video
   包含关键词: "倒在血泊中" ← 可能触发 content policy

⬆️ Phase 1 (comply-agent): 合规改写记录
   第 15 行: 原文 "鲜血喷涌" → 改写为 "倒在血泊中"
   ⚠️ 改写不充分：保留了 "血泊" 意象

🔍 根因分析：
   comply-agent Layer 1 命中 "鲜血" 但改写后仍含暴力意象 "血泊"
   → visual-agent 据此生成 prompt 仍含 violence descriptor
   → Seedance API content policy 拒绝

💡 建议：
   1. 更新 comply-agent 改写策略："血泊" 类意象应改为反应镜头
   2. 或在 visual-agent 添加 prompt 安全检查层
```

### 7. LLM 摘要（~trace --summary）

**查看已有摘要**：读取 `state/traces/{session-id}/summary.md` 并展示。

**重新生成**：
```bash
./scripts/api-caller.sh trace-summary state/traces/{session-id}
```

需要 `DEEPSEEK_API_KEY` 环境变量。如果未设置：
```
⚠️ 未配置 DEEPSEEK_API_KEY，无法生成 LLM 摘要。
设置后运行 ~trace --summary {session-id} 重新生成。
```

### 8. 索引生成

当 session 结束时（或 `~trace` 首次查询该 session 时），自动生成 `state/traces/{session-id}/index.json`：

```json
{
  "session_id": "{session-id}",
  "created_at": "{ISO8601}",
  "episodes": {
    "ep01": {
      "phases": {
        "phase1": "ep01-phase1-trace.jsonl",
        "phase2": "ep01-phase2-trace.jsonl",
        "phase3": "ep01-phase3-trace.jsonl",
        "phase4": "ep01-phase4-trace.jsonl"
      },
      "shots": {
        "shot-01": "ep01-shot-01-trace.jsonl",
        "shot-02": "ep01-shot-02-trace.jsonl"
      }
    }
  },
  "failures": [
    {
      "ep": "ep01",
      "shot": "shot-03",
      "trace_file": "ep01-shot-03-trace.jsonl",
      "error": "content policy: violence detected",
      "total_retries": 14
    }
  ],
  "stats": {
    "total_episodes": 3,
    "total_shots": 30,
    "succeeded": 28,
    "failed": 2
  }
}
```

索引生成方式：
1. 扫描 session 目录下所有 `*-trace.jsonl` 文件
2. 按 `{ep}-phase{N}` 和 `{ep}-shot-{N}` 模式分类
3. 从各 trace 文件提取 `fail` 事件，汇总到 `failures` 数组
4. 统计 shot 成功/失败数，写入 `stats`

## Trace 数据来源

| 查询模式 | 读取文件 |
|---------|---------|
| 路径概览 | `index.json`（优先） → `session.jsonl` |
| 单集详情 | `index.json`（定位） + `{ep}-phase{1-4}-trace.jsonl` + `{ep}-shot-*-trace.jsonl` |
| 单 Phase | `{ep}-phase{N}-trace.jsonl` |
| 单 Shot | `{ep}-shot-{N}-trace.jsonl` |
| Backtrack | `index.json`（定位 failures） + `{ep}-shot-{N}-trace.jsonl` + `{ep}-phase2-trace.jsonl` + `{ep}-phase1-trace.jsonl` |
| LLM 摘要 | `summary.md`（或调用 api-caller.sh 生成） |
| 索引生成 | 扫描所有 `*-trace.jsonl` → 输出 `index.json` |
