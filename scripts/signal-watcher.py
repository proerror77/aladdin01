#!/usr/bin/env python3
"""
signal-watcher.py — 监控 repair-agent 信号目录（调试工具）

用法：
  python3 scripts/signal-watcher.py --project qyccan --ep ep01
  python3 scripts/signal-watcher.py --project qyccan --ep ep01 --dry-run
  python3 scripts/signal-watcher.py --project qyccan --ep ep01 --once
"""
import argparse, glob, json, os, sys, time
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(
        description="监控 repair-agent 信号目录（调试工具）"
    )
    parser.add_argument("--project", required=True, help="项目名")
    parser.add_argument("--ep", required=True, help="剧本 ID（如 ep01）")
    parser.add_argument(
        "--dry-run", action="store_true", help="只显示，不删除信号文件"
    )
    parser.add_argument("--once", action="store_true", help="扫描一次后退出")
    args = parser.parse_args()

    signals_dir = f"projects/{args.project}/state/signals"

    if not os.path.isdir(signals_dir):
        print(f"信号目录不存在: {signals_dir}")
        if args.once:
            return
        print("等待目录创建...")

    while True:
        gen_signals = sorted(
            glob.glob(f"{signals_dir}/repair-needs-gen-{args.ep}-*.json")
        )
        qa_signals = sorted(
            glob.glob(f"{signals_dir}/repair-needs-qa-{args.ep}-*.json")
        )

        now = datetime.now().strftime("%H:%M:%S")

        if gen_signals or qa_signals:
            print(f"\n[{now}] 发现待处理信号：")
            for f in gen_signals:
                try:
                    data = json.load(open(f))
                except (json.JSONDecodeError, OSError):
                    data = {}
                shot = data.get("shot_id", os.path.basename(f))
                adj = data.get("adjustment", "unknown")
                print(f"  GEN  {shot} (adjustment={adj}) → 需要 spawn gen-worker")
                if not args.dry_run:
                    print(
                        "       [提示: 此工具不自动 spawn agents，请手动处理或使用 team-lead]"
                    )
            for f in qa_signals:
                try:
                    data = json.load(open(f))
                except (json.JSONDecodeError, OSError):
                    data = {}
                shot = data.get("shot_id", os.path.basename(f))
                print(f"  QA   {shot} → 需要 spawn qa-agent")
        else:
            print(f"[{now}] 无待处理信号", end="\r")

        if args.once:
            break
        time.sleep(3)


if __name__ == "__main__":
    main()
