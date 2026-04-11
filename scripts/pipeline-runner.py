#!/usr/bin/env python3
"""
pipeline-runner.py — Episode 状态机

用法：
  python3 scripts/pipeline-runner.py status  --project qyccan --ep ep01
  python3 scripts/pipeline-runner.py next    --project qyccan --ep ep01 [--use-v2]
  python3 scripts/pipeline-runner.py complete --project qyccan --ep ep01 --phase 2
  python3 scripts/pipeline-runner.py fail    --project qyccan --ep ep01 --phase 2 --reason "gate rejected"
  python3 scripts/pipeline-runner.py reset   --project qyccan --ep ep01 --from-phase 3
  python3 scripts/pipeline-runner.py shots   --project qyccan --ep ep01
"""

import argparse
import glob as globmod
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

import yaml

PHASE_ORDER = [0, 1, 2, 2.2, 2.3, 2.5, 3, 3.5, 4, 5, 6]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PHASES_CONFIG = os.path.join(PROJECT_ROOT, "config", "pipeline", "phases.yaml")


def _format_phase_id(phase_id: float) -> str:
    """Convert phase_id float to string for filenames: 2.0 -> '2', 2.2 -> '2.2'."""
    if phase_id == int(phase_id):
        return str(int(phase_id))
    return str(phase_id)


class EpisodePipeline:
    def __init__(self, project: str, ep: str, use_v2: bool = False):
        self.project = project
        self.ep = ep
        self.use_v2 = use_v2
        self.phases = self._load_phases()

    def _load_phases(self) -> list:
        with open(PHASES_CONFIG) as f:
            data = yaml.safe_load(f)
        return data["phases"]

    def _get_phase_def(self, phase_id: float) -> dict | None:
        for p in self.phases:
            if float(p["id"]) == phase_id:
                return p
        return None

    def _read_phase_state(self, phase_id: float) -> dict:
        phase_str = _format_phase_id(phase_id)
        state_file = os.path.join(
            PROJECT_ROOT,
            f"projects/{self.project}/state/{self.ep}-phase{phase_str}.json",
        )
        if not os.path.exists(state_file):
            return {"status": "pending", "retry_count": 0}
        with open(state_file) as f:
            return json.load(f)

    def _check_precondition(self, phase: dict) -> tuple:
        precond = phase.get("precondition", "")

        if precond == "use_v2":
            return self.use_v2, "use_v2=false"

        if precond == "script_exists":
            path = os.path.join(
                PROJECT_ROOT,
                f"projects/{self.project}/script/{self.ep}.md",
            )
            return os.path.exists(path), f"script not found: {path}"

        if precond == "use_v2_and_phase_3_completed":
            if not self.use_v2:
                return False, "use_v2=false"
            state = self._read_phase_state(3)
            return state["status"] == "completed", "phase_3 not completed"

        if precond == "use_v2_and_phase_5_completed":
            if not self.use_v2:
                return False, "use_v2=false"
            state = self._read_phase_state(5)
            return state["status"] == "completed", "phase_5 not completed"

        if precond.startswith("phase_") and precond.endswith("_completed"):
            phase_part = precond[len("phase_"):-len("_completed")]
            phase_num = float(phase_part)
            state = self._read_phase_state(phase_num)
            return state["status"] == "completed", f"phase_{phase_part} not completed"

        return True, ""

    def _resolve_inputs(self, phase: dict) -> dict:
        p = self.project
        e = self.ep
        base = {"project": p, "ep": e}
        name = phase["name"]

        if name == "comply":
            base["script"] = f"projects/{p}/script/{e}.md"
        elif name == "visual":
            base["render_script"] = f"projects/{p}/outputs/{e}/render-script.md"
            base["world_model"] = (
                f"projects/{p}/state/ontology/{e}-world-model.json"
                if self.use_v2
                else None
            )
        elif name == "narrative-review":
            base["visual_direction"] = f"projects/{p}/outputs/{e}/visual-direction.yaml"
            base["render_script"] = f"projects/{p}/outputs/{e}/render-script.md"
        elif name == "storyboard":
            base["visual_direction"] = f"projects/{p}/outputs/{e}/visual-direction.yaml"
        elif name == "design":
            base["visual_direction"] = f"projects/{p}/outputs/{e}/visual-direction.yaml"
            base["design_lock"] = f"projects/{p}/state/design-lock.json"
        elif name == "shot-compiler":
            base["visual_direction"] = f"projects/{p}/outputs/{e}/visual-direction.yaml"
            base["world_model"] = f"projects/{p}/state/ontology/{e}-world-model.json"
        elif name == "voice":
            base["render_script"] = f"projects/{p}/outputs/{e}/render-script.md"
            base["visual_direction"] = f"projects/{p}/outputs/{e}/visual-direction.yaml"
        elif name == "gen-worker":
            base["visual_direction"] = f"projects/{p}/outputs/{e}/visual-direction.yaml"
        elif name == "audit-repair":
            base["visual_direction"] = f"projects/{p}/outputs/{e}/visual-direction.yaml"
            base["world_model"] = f"projects/{p}/state/ontology/{e}-world-model.json"

        return base

    def get_next_action(self) -> dict:
        for phase_id in PHASE_ORDER:
            phase = self._get_phase_def(phase_id)
            if phase is None:
                continue

            state = self._read_phase_state(phase_id)

            if state["status"] == "completed":
                continue

            precond_met, reason = self._check_precondition(phase)
            if not precond_met:
                if phase.get("optional"):
                    continue
                return {
                    "action": "error",
                    "phase": phase_id,
                    "phase_name": phase["name"],
                    "reason": f"precondition not met: {reason}",
                }

            if state["status"] == "failed":
                retry_max = phase.get("retry", {}).get("max", 0)
                retry_count = state.get("retry_count", 0)
                if retry_count >= retry_max:
                    return {
                        "action": "error",
                        "phase": phase_id,
                        "phase_name": phase["name"],
                        "reason": f"max retries ({retry_max}) exceeded",
                    }

            return {
                "action": "spawn_agent",
                "agent": phase["agent"],
                "phase": phase_id,
                "phase_name": phase["name"],
                "inputs": self._resolve_inputs(phase),
                "preconditions_met": True,
                "skip_reason": None,
            }

        return {
            "action": "done",
            "episode": self.ep,
            "project": self.project,
            "summary": "所有 Phase 完成",
        }

    def mark_complete(self, phase_id: float, skip: bool = False):
        phase_str = _format_phase_id(phase_id)
        state_file = os.path.join(
            PROJECT_ROOT,
            f"projects/{self.project}/state/{self.ep}-phase{phase_str}.json",
        )

        if os.path.exists(state_file):
            with open(state_file) as f:
                state = json.load(f)
        else:
            state = {"episode": self.ep, "phase": phase_id}

        state["status"] = "skipped" if skip else "completed"
        state["completed_at"] = datetime.utcnow().isoformat() + "Z"

        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        label = "skipped" if skip else "completed"
        print(f"✓ Phase {phase_str} 标记为 {label}")

    def mark_fail(self, phase_id: float, reason: str):
        phase_str = _format_phase_id(phase_id)
        state_file = os.path.join(
            PROJECT_ROOT,
            f"projects/{self.project}/state/{self.ep}-phase{phase_str}.json",
        )

        if os.path.exists(state_file):
            with open(state_file) as f:
                state = json.load(f)
        else:
            state = {"episode": self.ep, "phase": phase_id}

        state["status"] = "failed"
        state["failed_at"] = datetime.utcnow().isoformat() + "Z"
        state["failure_reason"] = reason
        state["retry_count"] = state.get("retry_count", 0) + 1

        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        print(f"✗ Phase {phase_str} 标记为 failed (retry #{state['retry_count']}): {reason}")

    def reset_from_phase(self, from_phase: float):
        reset_phases = [p for p in PHASE_ORDER if p >= from_phase]

        for phase_id in reset_phases:
            phase_str = _format_phase_id(phase_id)
            state_file = os.path.join(
                PROJECT_ROOT,
                f"projects/{self.project}/state/{self.ep}-phase{phase_str}.json",
            )
            if os.path.exists(state_file):
                with open(state_file) as f:
                    state = json.load(f)
                state["status"] = "pending"
                state.pop("completed_at", None)
                state.pop("failed_at", None)
                state.pop("failure_reason", None)
                with open(state_file, "w") as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)
                print(f"  reset Phase {phase_str}")

        print(f"✓ 已重置 Phase {_format_phase_id(from_phase)} 及之后的所有 Phase")

    def print_status(self):
        print(f"\nEpisode: {self.ep} (project: {self.project})")
        print("─" * 50)

        for phase_id in PHASE_ORDER:
            phase = self._get_phase_def(phase_id)
            if phase is None:
                continue

            state = self._read_phase_state(phase_id)
            status = state.get("status", "pending")
            precond_met, reason = self._check_precondition(phase)

            if status == "completed":
                ts = state.get("completed_at", "")[:19]
                icon = "✓"
                detail = ts
            elif status == "skipped":
                icon = "─"
                detail = reason or "skipped"
            elif status == "failed":
                icon = "✗"
                detail = state.get("failure_reason", "failed")
            elif status == "running":
                icon = "⟳"
                detail = "running"
            else:
                if not precond_met and phase.get("optional"):
                    icon = "○"
                    detail = f"skip: {reason}"
                else:
                    icon = "·"
                    detail = "pending"

            phase_str = _format_phase_id(phase_id)
            phase_label = f"Phase {phase_str:<4} {phase['name']:<20}"
            print(f"  [{icon}] {phase_label} {detail}")

        print("─" * 50)
        next_action = self.get_next_action()
        if next_action["action"] == "done":
            print("  状态：全部完成 ✓")
        elif next_action["action"] == "spawn_agent":
            print(f"  下一步：Phase {next_action['phase']} ({next_action['agent']})")
        elif next_action["action"] == "error":
            print(f"  ❌ 错误：{next_action['reason']}")
        print()



class ShotStateMachine:
    """Shot 级别状态机：管理单个 shot 从生成到审计到修复的完整生命周期。"""

    STATES = [
        "pending", "generating", "generated",
        "auditing", "audited",
        "repairing", "done", "failed",
    ]

    TRANSITIONS = {
        ("pending",    "gen_started"):    "generating",
        ("generating", "gen_success"):    "generated",
        ("generating", "gen_failed"):     "failed",
        ("generated",  "audit_start"):    "auditing",
        ("auditing",   "audit_pass"):     "done",
        ("auditing",   "audit_repair"):   "repairing",
        ("auditing",   "audit_regen"):    "repairing",
        ("repairing",  "repair_done"):    "generating",   # 重新生成
        ("repairing",  "repair_failed"):  "failed",
    }

    def __init__(self, project: str, ep: str):
        self.project = project
        self.ep = ep

    def _state_file(self, shot_id: str) -> str:
        return os.path.join(
            PROJECT_ROOT,
            f"projects/{self.project}/state/{shot_id}.json",
        )

    def get_state(self, shot_id: str) -> str:
        sf = self._state_file(shot_id)
        if not os.path.exists(sf):
            return "pending"
        with open(sf) as f:
            data = json.load(f)
        # 现有文件用 gen_status 字段；新字段用 sm_state
        return data.get("sm_state", data.get("gen_status", "pending"))

    def transition(self, shot_id: str, event: str, reason: str = "") -> str:
        current = self.get_state(shot_id)
        key = (current, event)
        if key not in self.TRANSITIONS:
            raise ValueError(
                f"Invalid transition for {shot_id}: state={current!r} event={event!r}"
            )
        new_state = self.TRANSITIONS[key]
        self._write_state(shot_id, new_state, event, reason)
        return new_state

    def _write_state(self, shot_id: str, new_state: str, event: str, reason: str):
        sf = self._state_file(shot_id)
        if os.path.exists(sf):
            with open(sf) as f:
                data = json.load(f)
        else:
            data = {"episode": self.ep, "shot_id": shot_id}

        now = datetime.now(timezone.utc).isoformat()
        history = data.get("sm_history", [])
        history.append({
            "state": new_state,
            "event": event,
            "reason": reason,
            "ts": now,
        })

        data["sm_state"] = new_state
        data["sm_history"] = history
        data["updated_at"] = now

        if new_state == "failed":
            data["retry_count"] = data.get("retry_count", 0)
        if new_state == "generating" and event == "repair_done":
            data["retry_count"] = data.get("retry_count", 0) + 1

        os.makedirs(os.path.dirname(sf), exist_ok=True)
        with open(sf, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def print_status(self):
        pattern = os.path.join(
            PROJECT_ROOT,
            f"projects/{self.project}/state/{self.ep}-shot-*.json",
        )
        shot_files = sorted(globmod.glob(pattern))
        if not shot_files:
            print(f"No shot state files found for {self.ep}")
            return

        print(f"\nShots: {self.ep} (project: {self.project})")
        print("─" * 50)
        counts = {s: 0 for s in self.STATES}
        for sf in shot_files:
            with open(sf) as f:
                data = json.load(f)
            shot_id = os.path.basename(sf).replace(".json", "")
            state = data.get("sm_state", data.get("gen_status", "pending"))
            counts[state] = counts.get(state, 0) + 1
            icons = {
                "done": "✓", "failed": "✗", "generating": "⟳",
                "auditing": "⟳", "repairing": "⟳",
            }
            icon = icons.get(state, "·")
            retry = data.get("retry_count", 0)
            retry_str = f" (retry {retry})" if retry else ""
            print(f"  [{icon}] {shot_id:<20} {state}{retry_str}")

        print("─" * 50)
        done = counts.get("done", 0)
        failed = counts.get("failed", 0)
        total = len(shot_files)
        print(f"  {done}/{total} done, {failed} failed")
        print()


def watch_signals(project: str, ep: str, stop_event: threading.Event,
                  queue_file: str | None = None):
    """
    后台线程：监听 repair-agent 信号目录，将待处理请求写入 dispatch-queue.json。
    不直接 spawn agents（那是 Claude Code 的职责）。
    """
    signals_dir = os.path.join(PROJECT_ROOT, f"projects/{project}/state/signals")
    if queue_file is None:
        queue_file = os.path.join(signals_dir, "dispatch-queue.json")

    os.makedirs(signals_dir, exist_ok=True)

    while not stop_event.is_set():
        pending = []
        for sig_file in globmod.glob(
            os.path.join(signals_dir, f"repair-needs-gen-{ep}-*.json")
        ):
            try:
                with open(sig_file) as f:
                    sig = json.load(f)
                pending.append({
                    "type": "gen_worker",
                    "shot_id": sig.get("shot_id", ""),
                    "signal_file": sig_file,
                    "requested_at": sig.get("requested_at", ""),
                })
            except (json.JSONDecodeError, OSError):
                pass

        for sig_file in globmod.glob(
            os.path.join(signals_dir, f"repair-needs-qa-{ep}-*.json")
        ):
            try:
                with open(sig_file) as f:
                    sig = json.load(f)
                pending.append({
                    "type": "qa_agent",
                    "shot_id": sig.get("shot_id", ""),
                    "signal_file": sig_file,
                    "requested_at": sig.get("requested_at", ""),
                })
            except (json.JSONDecodeError, OSError):
                pass

        if pending:
            with open(queue_file, "w") as f:
                json.dump({
                    "pending": pending,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }, f, indent=2, ensure_ascii=False)

        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="Pipeline 状态机")
    parser.add_argument(
        "command",
        choices=["status", "next", "complete", "fail", "reset", "shots",
                 "shot-status", "shot-event", "watch-signals"],
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--ep", required=True)
    parser.add_argument("--use-v2", action="store_true")
    parser.add_argument("--phase", type=float)
    parser.add_argument("--from-phase", type=float)
    parser.add_argument("--reason", default="")
    parser.add_argument("--skip", action="store_true")
    # shot-level args
    parser.add_argument("--shot", help="Shot ID, e.g. ep01-shot-03")
    parser.add_argument("--event", help="Shot state machine event, e.g. gen_success")
    args = parser.parse_args()

    pipeline = EpisodePipeline(args.project, args.ep, use_v2=args.use_v2)

    if args.command == "status":
        pipeline.print_status()
    elif args.command == "next":
        result = pipeline.get_next_action()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "complete":
        if args.phase is None:
            print("错误: --phase 必填", file=sys.stderr)
            sys.exit(1)
        pipeline.mark_complete(args.phase, skip=args.skip)
    elif args.command == "fail":
        if args.phase is None:
            print("错误: --phase 必填", file=sys.stderr)
            sys.exit(1)
        pipeline.mark_fail(args.phase, args.reason)
    elif args.command == "reset":
        if args.from_phase is None:
            print("错误: --from-phase 必填", file=sys.stderr)
            sys.exit(1)
        pipeline.reset_from_phase(args.from_phase)
    elif args.command == "shots":
        sm = ShotStateMachine(args.project, args.ep)
        sm.print_status()
    elif args.command == "shot-status":
        if not args.shot:
            print("错误: --shot 必填", file=sys.stderr)
            sys.exit(1)
        sm = ShotStateMachine(args.project, args.ep)
        state = sm.get_state(args.shot)
        print(json.dumps({"shot_id": args.shot, "state": state}, ensure_ascii=False))
    elif args.command == "shot-event":
        if not args.shot or not args.event:
            print("错误: --shot 和 --event 必填", file=sys.stderr)
            sys.exit(1)
        sm = ShotStateMachine(args.project, args.ep)
        new_state = sm.transition(args.shot, args.event, reason=args.reason)
        print(json.dumps({
            "shot_id": args.shot,
            "event": args.event,
            "new_state": new_state,
        }, ensure_ascii=False))
    elif args.command == "watch-signals":
        stop = threading.Event()
        print(f"监听信号目录: projects/{args.project}/state/signals/")
        print("按 Ctrl+C 停止")
        try:
            watch_signals(args.project, args.ep, stop)
        except KeyboardInterrupt:
            stop.set()
            print("\n已停止")


if __name__ == "__main__":
    main()
