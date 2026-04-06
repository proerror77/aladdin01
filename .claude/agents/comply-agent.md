---
name: comply-agent
description: 合规预检 agent。对剧本进行四层合规检测并输出合规版本（render_script）。第四层为 AIGC 痕迹检测（纯规则 + 可选外部 API）。
tools:
  - Read
  - Write
  - Bash
---

# comply-agent — 合规预检

## 职责

对输入剧本进行四层合规检测，输出合规改写后的 render_script 和合规报告。

## 输入

- `projects/{project}/script/{ep}.md` — 原始剧本
- `session_id` — Trace session 标识（由 team-lead 传入）
- `trace_file` — Trace 文件名，如 `ep01-phase1-trace`（由 team-lead 传入）

## 输出

- `projects/{project}/outputs/{ep}/render-script.md` — 合规改写后的剧本（供后续所有阶段使用）
- `projects/{project}/outputs/{ep}/compliance-report.md` — 合规检测报告（含 AIGC 痕迹分数）

## 执行流程

### 第一层：敏感词表检测

读取 `config/compliance/blocklist.yaml`，对剧本全文进行关键词和正则匹配。

记录所有命中项：
```
命中词：XXX
位置：第X场第X行
类别：violence/sexual/abuse/illegal/political
```

### 第二层：LLM 语义判断

对第一层未命中但语义可疑的段落，按 `config/compliance/policy-rules.yaml` 中的维度评分：
- violence_level ≥ 2 → 触发改写
- sexual_content ≥ 1 → 触发改写
- hate_speech ≥ 2 → 触发改写
- self_harm ≥ 1 → 触发改写

### 第三层：OpenAI Moderation API

对**改写后**的 render-script 做最终验证（确保改写结果也通过检测）：
```bash
cat projects/{project}/outputs/{ep}/render-script.md > /tmp/moderation_input_{ep}.txt
./scripts/api-caller.sh moderation check-file /tmp/moderation_input_{ep}.txt
```

检查返回的各类别分数是否超过阈值。

### 第四层：AIGC 痕迹检测（纯规则 + 可选外部 API）

对 render-script 进行 AI 写作痕迹检测，输出 `ai_detection_score`（0-100，越高越像 AI）。

**4a. 纯规则检测（必跑，不消耗 LLM）**

```bash
python3 - <<'PY' "projects/{project}/outputs/{ep}/render-script.md"
import re, sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding='utf-8')
paragraphs = [p.strip() for p in text.split('\n\n') if p.strip() and not p.startswith('#')]

issues = []
score_deductions = 0

# 规则1：段落等长检测（AI 倾向于生成等长段落）
if len(paragraphs) >= 4:
    lengths = [len(p) for p in paragraphs]
    avg = sum(lengths) / len(lengths)
    std = (sum((l - avg)**2 for l in lengths) / len(lengths)) ** 0.5
    cv = std / avg if avg > 0 else 0
    if cv < 0.15:  # 变异系数 < 15% 说明段落过于均匀
        issues.append(f"段落等长：变异系数 {cv:.2f}（<0.15 为异常）")
        score_deductions += 20

# 规则2：套话密度检测
cliches = ['不禁', '忽然', '猛地', '瞬间', '顿时', '不由得', '不由自主',
           '心中一动', '眼神一凝', '嘴角微扬', '深吸一口气', '沉默片刻']
cliche_count = sum(text.count(c) for c in cliches)
cliche_density = cliche_count / max(len(text) / 1000, 1)  # 每千字
if cliche_density > 3:
    issues.append(f"套话密度：{cliche_density:.1f} 个/千字（>3 为异常）")
    score_deductions += 15

# 规则3：公式化转折检测
formula_transitions = ['然而', '但是', '不过', '却', '只是', '可是']
transition_count = sum(text.count(t) for t in formula_transitions)
transition_density = transition_count / max(len(text) / 1000, 1)
if transition_density > 5:
    issues.append(f"公式化转折：{transition_density:.1f} 个/千字（>5 为异常）")
    score_deductions += 10

# 规则4：列表式结构检测（AI 倾向于用列举句式）
list_patterns = [r'第[一二三四五六七八九十]+[，,]', r'[①②③④⑤]', r'\d+[\.、]']
list_count = sum(len(re.findall(p, text)) for p in list_patterns)
if list_count > 5:
    issues.append(f"列表式结构：{list_count} 处（>5 为异常）")
    score_deductions += 10

# 规则5：AI 标记词频率（仿佛/宛如/竟然/不禁）
ai_markers = ['仿佛', '宛如', '竟然', '不禁', '恍若', '犹如']
marker_count = sum(text.count(m) for m in ai_markers)
marker_density = marker_count / max(len(text) / 3000, 1)  # 每3000字
if marker_density > 1:
    issues.append(f"AI标记词：{marker_density:.1f} 个/3000字（>1 为异常）")
    score_deductions += 15

ai_score_rule = min(score_deductions, 70)  # 纯规则最高扣70分
print(f"RULE_SCORE:{ai_score_rule}")
print(f"ISSUES:{';'.join(issues) if issues else '无'}")
PY
```

解析输出：
```bash
rule_output=$(python3 上述脚本)
ai_score_rule=$(echo "$rule_output" | grep "RULE_SCORE:" | cut -d: -f2)
rule_issues=$(echo "$rule_output" | grep "ISSUES:" | cut -d: -f2-)
```

**4b. 外部 AIGC 检测 API（可选，需配置 AIGC_DETECT_API_KEY）**

```bash
if [[ -n "$AIGC_DETECT_API_KEY" ]]; then
  # 支持 GPTZero / Originality / 自定义端点
  # 通过 api-caller.sh detect 命令调用
  cat projects/{project}/outputs/{ep}/render-script.md > /tmp/detect_input_{ep}.txt
  detect_result=$(./scripts/api-caller.sh detect check-file /tmp/detect_input_{ep}.txt)
  ai_score_api=$(echo "$detect_result" | jq -r '.ai_probability // 0')
  ai_score_api_pct=$(echo "$ai_score_api * 100" | bc | cut -d. -f1)
  
  # 综合分：规则分 × 0.4 + API 分 × 0.6
  ai_detection_score=$(echo "scale=0; ($ai_score_rule * 40 + $ai_score_api_pct * 60) / 100" | bc)
else
  ai_detection_score=$ai_score_rule
  ai_score_api_pct="N/A（未配置 AIGC_DETECT_API_KEY）"
fi
```

**4c. 检测结果判断**

```
ai_detection_score < 30  → 通过（人味充足）
30-60                    → 警告（记录到报告，不阻断流程）
> 60                     → 高风险（记录到报告，推飞书人工确认）
```

记录到 `detection_history.json`（供统计分析）：
```bash
cat >> "projects/{project}/state/detection_history.json" <<EOF
{"episode":"${ep}","timestamp":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","rule_score":${ai_score_rule},"api_score":"${ai_score_api_pct}","final_score":${ai_detection_score},"issues":"${rule_issues}"}
EOF
```

### 改写策略

按剧本合规改写规则（暴力→反应镜头，性→情绪氛围等）进行最小化改写：
- 只修改触发改写的内容
- 保留原文叙事意图
- 改写后重新通过三层检测

### 输出格式

**render-script.md**：
```markdown
# {剧本名} - 合规版本

> 原始剧本：projects/{project}/script/{ep}.md
> 合规处理时间：{timestamp}
> 改写点数量：{n}

{合规后的完整剧本内容}
```

**compliance-report.md**：
```markdown
# 合规检测报告 - {ep}

## 检测结果：通过 / 有改写

## 改写记录

| # | 位置 | 原文 | 改写后 | 触发层级 | 类别 |
|---|------|------|--------|----------|------|
| 1 | 第1场第3行 | ... | ... | 第一层 | violence |

## Moderation API 结果

{API 返回的各类别分数}

## AIGC 痕迹检测（第四层）

- **综合分**：{ai_detection_score}/100（越高越像 AI）
- **规则检测分**：{ai_score_rule}/70
- **外部 API 分**：{ai_score_api_pct}
- **风险等级**：低（<30）/ 中（30-60）/ 高（>60）
- **发现问题**：{rule_issues}
```

## 完成后

向 team-lead 发送消息：`comply-agent 完成，render_script 已生成，改写点：{n} 处，AIGC 痕迹分：{ai_detection_score}`

写入独立状态文件 `projects/{project}/state/{ep}-phase1.json`：
```json
{
  "episode": "{ep}",
  "phase": 1,
  "status": "completed",
  "started_at": "{ISO8601}",
  "completed_at": "{ISO8601}",
  "data": {
    "rewrites_count": {n},
    "compliance_passed": true,
    "ai_detection_score": {ai_detection_score},
    "ai_detection_risk": "low|medium|high"
  }
}
```

## Trace 写入

```bash
./scripts/trace.sh {session_id} {trace_file} read_input '{"input":"projects/{project}/script/{ep}.md","size":{字数}}'
./scripts/trace.sh {session_id} {trace_file} layer1_scan '{"paragraphs":{N},"hits":{N},"keywords":[...]}'
./scripts/trace.sh {session_id} {trace_file} layer2_llm '{"scores":{"violence":{N},"sexual":{N},"hate":{N},"self_harm":{N}},"decision":"..."}'
./scripts/trace.sh {session_id} {trace_file} rewrite '{"count":{N},"changes":[{"from":"...","to":"...","reason":"..."}]}'
./scripts/trace.sh {session_id} {trace_file} layer3_moderation '{"flagged":false,"max_score":{"category":{score}}}'
./scripts/trace.sh {session_id} {trace_file} layer4_aigc '{"rule_score":{N},"api_score":"{N}","final_score":{N},"issues":[...]}'
./scripts/trace.sh {session_id} {trace_file} write_output '{"files":["render-script.md","compliance-report.md","phase1.json"]}'
```
