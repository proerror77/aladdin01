# 状态机重构计划

## 问题诊断

### P0 Bug：信号机制死循环
`repair-agent` 写 `repair-needs-gen-*.json` 信号文件后等待删除，但 `start.md` 里没有任何读取/删除信号的逻辑。
结果：repair-agent 永远等待，Phase 6 卡死。

### P1 Bug：Phase 流转靠 LLM 理解 700 行伪代码
`~start` 是 700 行 Markdown，team-lead 每次都要重新"理解"流程，没有强制约束，容易漂移。

### P2 问题：workflow-sync.py 是孤岛
45KB 的修复工具，不在任何 Phase 里自动触发，只能手动运行。

---

## 架构方案：混合状态机（Option C）

```
~start / ~batch (薄包装)
    ↓ 调用
pipeline-runner.py (Python 状态机)
    ├── Episode 状态机：Phase 0→1→2→2.2→2.3→2.5→3→3.5→4→5→6
    ├── Shot 状态机：pending→generating→auditing→repairing→done/failed
    └── Signal Handler：repair-agent ↔ gen-worker 桥接
```

**分工原则**：
- Python 负责：状态读写、信号处理、Shot 生命周期、重试逻辑、进度报告
- Claude Code 负责：spawn agents、读取 agent 输出、人工确认点

---

## 实现计划

### Phase A：修复信号 Bug（P0，独立可部署）

**目标**：不重构架构，直接修复 repair-agent 信号死循环。

**修改文件**：`.claude/skills/start.md` Phase 6 段落

**改动**：在 Phase 6 的 for 循环里，spawn repair-agent 之前启动一个后台信号监听器：

```bash
# 启动信号监听（后台）
python3 scripts/signal-watcher.py \
  --project $PROJECT --ep $EP --session $SESSION_ID &
SIGNAL_WATCHER_PID=$!

# ... spawn repair-agent（现有逻辑）...

# 结束后关闭监听器
kill $SIGNAL_WATCHER_PID 2>/dev/null
```

**新建文件**：`scripts/signal-watcher.py`（~80 行）
- 轮询 `projects/{project}/state/signals/` 目录
- 发现 `repair-needs-gen-*.json` → spawn gen-worker → 删除信号文件
- 发现 `repair-needs-qa-*.json` → spawn qa-agent → 删除信号文件

---

### Phase B：Episode 状态机（核心重构）

**目标**：用 Python 状态机替代 start.md 里的 Phase 流转伪代码。

**新建文件**：`scripts/pipeline-runner.py`

#### 接口设计

```bash
# 查询当前状态
python3 scripts/pipeline-runner.py status --project qyccan --ep ep01

# 获取下一步动作（JSON 输出）
python3 scripts/pipeline-runner.py next --project qyccan --ep ep01

# 标记 Phase 完成
python3 scripts/pipeline-runner.py complete --project qyccan --ep ep01 --phase 2

# 标记 Phase 失败（附原因）
python3 scripts/pipeline-runner.py fail --project qyccan --ep ep01 --phase 2 --reason "gate rejected"

# 重置到某个 Phase（断点续传）
python3 scripts/pipeline-runner.py reset --project qyccan --ep ep01 --from-phase 3
```

#### `next` 命令输出格式

```json
{
  "action": "spawn_agent",
  "agent": "visual-agent",
  "phase": 2,
  "inputs": {
    "render_script": "projects/qyccan/outputs/ep01/render-script.md",
    "world_model": "projects/qyccan/state/ontology/ep01-world-model.json"
  },
  "preconditions_met": true,
  "skip_reason": null
}
```

或：

```json
{
  "action": "skip",
  "phase": 0,
  "skip_reason": "world-model.json 不存在且 USE_V2=false",
  "next_phase": 1
}
```

或：

```json
{
  "action": "done",
  "episode": "ep01",
  "summary": "所有 Phase 完成，8/8 镜次成功"
}
```

#### Phase 定义（`config/pipeline/phases.yaml`）

```yaml
phases:
  - id: 0
    name: ontology-builder
    agent: ontology-builder-agent
    optional: true
    precondition: "USE_V2 == true"
    artifact: "projects/{project}/state/ontology/{ep}-world-model.json"
    state_file: "projects/{project}/state/{ep}-phase0.json"

  - id: 1
    name: comply
    agent: comply-agent
    optional: false
    precondition: "script_exists"
    artifact: "projects/{project}/outputs/{ep}/render-script.md"
    state_file: "projects/{project}/state/{ep}-phase1.json"

  - id: 2
    name: visual
    agent: visual-agent
    optional: false
    precondition: "phase_1_completed"
    artifact: "projects/{project}/outputs/{ep}/visual-direction.yaml"
    state_file: "projects/{project}/state/{ep}-phase2.json"
    retry:
      max: 2
      on_failure: "gate_rejected"

  # ... 2.2, 2.3, 2.5, 3, 3.5, 4, 5, 6
```

#### 内部状态机逻辑

```python
class EpisodePipeline:
    PHASES = [0, 1, 2, 2.2, 2.3, 2.5, 3, 3.5, 4, 5, 6]

    def get_next_action(self) -> dict:
        for phase_id in self.PHASES:
            phase = self.phase_defs[phase_id]
            state = self.read_phase_state(phase_id)

            if state.status == "completed":
                continue  # 已完成，跳过

            if not self.check_precondition(phase):
                if phase.optional:
                    continue  # 可选 Phase，跳过
                else:
                    return {"action": "error", "reason": f"Phase {phase_id} 前置条件不满足"}

            if state.status == "failed" and state.retry_count >= phase.max_retries:
                return {"action": "error", "reason": f"Phase {phase_id} 超过最大重试次数"}

            return {
                "action": "spawn_agent",
                "agent": phase.agent,
                "phase": phase_id,
                "inputs": self.resolve_inputs(phase),
            }

        return {"action": "done", "summary": self.build_summary()}
```

---

### Phase C：Shot 状态机

**目标**：用 Python 管理 Phase 5+6 的 Shot 生命周期，彻底解决信号 bug。

**扩展 `pipeline-runner.py`**：

```python
class ShotStateMachine:
    STATES = ["pending", "generating", "generated", "auditing", "audited",
              "repairing", "done", "failed"]

    def transition(self, shot_id: str, event: str) -> str:
        """
        事件驱动的状态转换：
        - gen_started → pending → generating
        - gen_success → generating → generated
        - gen_failed  → generating → failed (if retries exhausted)
        - audit_pass  → audited → done
        - audit_repair → audited → repairing
        - repair_done → repairing → generating (重新生成)
        - repair_failed → repairing → failed
        """
```

**信号处理内嵌到状态机**：

```python
def run_phase_6(self):
    """Phase 6 主循环：QA + Repair，信号驱动"""
    shots = self.get_all_shots()

    # 初始化所有 shot 为 pending
    for shot in shots:
        self.shot_sm.set_state(shot.id, "pending")

    # 启动信号监听线程
    signal_thread = threading.Thread(target=self._signal_loop, daemon=True)
    signal_thread.start()

    # 并行 spawn qa-agent（所有 shot）
    # qa-agent 完成后写 audit JSON
    # 状态机读取 audit JSON，决定 pass/repair/regenerate
    # repair-agent 写信号 → 信号线程捕获 → spawn gen-worker → 删除信号
    # gen-worker 完成 → 状态机更新 shot 状态 → 重新 spawn qa-agent

def _signal_loop(self):
    """后台线程：监听 repair-agent 信号，调度 gen-worker"""
    signals_dir = f"projects/{self.project}/state/signals/"
    while not self._stop_event.is_set():
        for sig_file in glob.glob(f"{signals_dir}repair-needs-gen-*.json"):
            self._handle_gen_signal(sig_file)
        time.sleep(2)
```

---

### Phase D：薄包装 Skill

**目标**：`~start` 和 `~batch` 变成 ~100 行，核心逻辑全在 pipeline-runner.py。

**`~start` 新结构**：

```
1. 解析参数（project, ep, flags）
2. 调用 pipeline-runner.py status → 显示当前状态
3. 循环：
   a. 调用 pipeline-runner.py next → 获取下一步动作
   b. 如果 action == "done" → 结束
   c. 如果 action == "spawn_agent" → spawn 对应 agent
   d. 等待 agent 完成
   e. 调用 pipeline-runner.py complete/fail → 更新状态
   f. 如果有人工确认点 → 推飞书/等待确认
4. 生成最终报告
```

**`~batch` 新结构**：

```
1. 扫描所有待处理 episode
2. 对每个 episode 并行调用 pipeline-runner.py
3. 汇总进度
```

---

## 实施顺序

| 阶段 | 工作 | 优先级 | 预计改动量 |
|------|------|--------|-----------|
| A | 修复信号 Bug（signal-watcher.py + start.md Phase 6） | P0，立即 | ~100 行 |
| B | Episode 状态机（pipeline-runner.py + phases.yaml） | P1 | ~400 行 |
| C | Shot 状态机（扩展 pipeline-runner.py） | P2 | ~200 行 |
| D | 薄包装 Skill（重写 start.md + batch.md） | P3 | 减少 ~1000 行 |

**建议**：A 和 B 可以并行，C 依赖 B，D 依赖 B+C。

---

## 关键约束

1. **不改变 agent 定义**：所有 `.claude/agents/*.md` 保持不变
2. **向后兼容**：现有状态文件格式（`{ep}-phase*.json`）保持不变
3. **断点续传**：pipeline-runner.py 读取现有状态文件，自动跳过已完成 Phase
4. **Claude Code 仍是 orchestrator**：Python 只管状态，agent spawn 仍由 Claude Code 执行
