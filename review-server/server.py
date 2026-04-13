"""
Review Server — 审核 UI + Webhook 接收 + Trace 查看
三合一轻量 FastAPI 服务

启动方式:
  cd review-server
  pip install -r requirements.txt
  uvicorn server:app --host 0.0.0.0 --port 8080 --reload

环境变量:
  REVIEW_SERVER_URL   — 外部可访问的 URL（默认 http://localhost:8080）
  PROJECT_ROOT        — 项目根目录（默认 ..）
  CLAUDE_TRIGGER_ID   — Claude Code Remote Trigger ID
  CLAUDE_TRIGGER_TOKEN — Claude Code API Token
"""

import json
import os
import glob
import asyncio
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx

# --- Config ---

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent.parent)).resolve()
STATE_DIR = PROJECT_ROOT / "state"
REVIEWS_DIR = STATE_DIR / "reviews"
TRACES_DIR = STATE_DIR / "traces"
ASSETS_DIR = PROJECT_ROOT / "assets"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

CLAUDE_TRIGGER_ID = os.getenv("CLAUDE_TRIGGER_ID", "")
CLAUDE_TRIGGER_TOKEN = os.getenv("CLAUDE_TRIGGER_TOKEN", "")
REVIEW_SERVER_URL = os.getenv("REVIEW_SERVER_URL", "http://localhost:8080")

# --- App ---

app = FastAPI(title="Aladdin Review Server", version="1.0.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Ensure reviews dir exists
REVIEWS_DIR.mkdir(parents=True, exist_ok=True)


# --- Helpers ---

def read_review(review_id: str) -> dict:
    review_file = REVIEWS_DIR / f"{review_id}.json"
    if not review_file.exists():
        raise HTTPException(status_code=404, detail=f"Review not found: {review_id}")
    return json.loads(review_file.read_text())


def write_review(review_id: str, data: dict):
    review_file = REVIEWS_DIR / f"{review_id}.json"
    review_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))


PENDING_TRIGGERS_FILE = STATE_DIR / "pending_triggers.json"
PENDING_TRIGGERS_LOCK = STATE_DIR / "pending_triggers.lock"


def _read_pending_triggers_unlocked() -> dict[str, dict]:
    if not PENDING_TRIGGERS_FILE.exists():
        return {}
    try:
        return json.loads(PENDING_TRIGGERS_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _write_pending_triggers_unlocked(pending: dict[str, dict]) -> None:
    PENDING_TRIGGERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = PENDING_TRIGGERS_FILE.with_suffix(".tmp")
    if pending:
        tmp_file.write_text(json.dumps(pending, ensure_ascii=False, indent=2))
        os.replace(tmp_file, PENDING_TRIGGERS_FILE)
        return

    if tmp_file.exists():
        tmp_file.unlink()
    if PENDING_TRIGGERS_FILE.exists():
        PENDING_TRIGGERS_FILE.unlink()


def _update_pending_triggers(mutator):
    PENDING_TRIGGERS_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_TRIGGERS_LOCK, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        pending = _read_pending_triggers_unlocked()
        result = mutator(pending)
        _write_pending_triggers_unlocked(pending)
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        return result


async def trigger_resume_with_retry(project: str, max_retries: int = 3) -> bool:
    """Fire Remote Trigger with exponential backoff retry."""
    if not CLAUDE_TRIGGER_ID or not CLAUDE_TRIGGER_TOKEN:
        print(f"[WARN] Remote Trigger not configured, skipping resume for {project}")
        return False

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://api.claude.ai/v1/code/triggers/{CLAUDE_TRIGGER_ID}/run",
                    headers={
                        "Authorization": f"Bearer {CLAUDE_TRIGGER_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    json={"prompt": f"~scriptwriter-to-video --resume {project}"},
                    timeout=30,
                )
                resp.raise_for_status()
            print(f"[INFO] Remote Trigger fired for {project}: {resp.status_code}")
            _remove_pending_trigger(project)
            return True
        except httpx.HTTPError as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f"[WARN] Trigger attempt {attempt+1}/{max_retries} failed for {project}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(wait)

    print(f"[ERROR] All {max_retries} trigger attempts failed for {project}")
    _save_pending_trigger(project)
    return False


def _save_pending_trigger(project: str):
    def mutate(pending: dict[str, dict]):
        pending[project] = {
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "retries_exhausted": 3,
        }

    _update_pending_triggers(mutate)


def _remove_pending_trigger(project: str):
    def mutate(pending: dict[str, dict]):
        pending.pop(project, None)

    _update_pending_triggers(mutate)


# --- Review Routes ---

@app.get("/review/{review_id}", response_class=HTMLResponse)
async def review_page(request: Request, review_id: str):
    """Render review page based on review type."""
    review = read_review(review_id)
    review_type = review.get("type", "text")

    # Resolve asset URLs
    assets = []
    for asset_path in review.get("assets", []):
        full_path = PROJECT_ROOT / asset_path
        if full_path.exists():
            assets.append({
                "path": asset_path,
                "url": f"/assets/{asset_path}",
                "name": full_path.name,
            })

    template_name = f"{review_type}_review.html"
    if not (Path(__file__).parent / "templates" / template_name).exists():
        template_name = "text_review.html"

    return templates.TemplateResponse(template_name, {
        "request": request,
        "review": review,
        "assets": assets,
        "review_id": review_id,
    })


@app.post("/review/{review_id}/approve")
async def approve_review(review_id: str):
    """Approve a review checkpoint."""
    review = read_review(review_id)

    if review["status"] not in ("pending", "redo"):
        raise HTTPException(400, f"Review {review_id} is not pending (status: {review['status']})")

    review["status"] = "approved"
    review["response"] = {
        "action": "approve",
        "responded_at": datetime.now(timezone.utc).isoformat(),
    }
    write_review(review_id, review)

    await trigger_resume_with_retry(review["project"])
    return {"status": "ok", "action": "approve", "review_id": review_id}


@app.post("/review/{review_id}/redo")
async def redo_review(review_id: str, request: Request):
    """Request redo with reason."""
    review = read_review(review_id)
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}

    reason = body.get("reason", "")
    selected_items = body.get("selected_items", [])

    if review["status"] not in ("pending", "redo"):
        raise HTTPException(400, f"Review {review_id} is not pending")

    max_iter = review.get("max_iterations", 5)
    if review["iteration"] >= max_iter:
        raise HTTPException(400, f"Review {review_id} reached max iterations ({max_iter})")

    # Save current to history
    if "history" not in review:
        review["history"] = []
    review["history"].append({
        "iteration": review["iteration"],
        "action": "redo",
        "reason": reason,
        "selected_items": selected_items,
        "responded_at": datetime.now(timezone.utc).isoformat(),
    })

    review["iteration"] += 1
    review["status"] = "redo"
    review["response"] = {
        "action": "redo",
        "reason": reason,
        "selected_items": selected_items,
        "responded_at": datetime.now(timezone.utc).isoformat(),
        "iteration": review["iteration"],
    }
    write_review(review_id, review)

    await trigger_resume_with_retry(review["project"])
    return {"status": "ok", "action": "redo", "review_id": review_id, "iteration": review["iteration"]}


@app.post("/review/{review_id}/terminate")
async def terminate_review(review_id: str):
    """Terminate the project."""
    review = read_review(review_id)

    review["status"] = "terminated"
    review["response"] = {
        "action": "terminate",
        "responded_at": datetime.now(timezone.utc).isoformat(),
    }
    write_review(review_id, review)

    await trigger_resume_with_retry(review["project"])
    return {"status": "ok", "action": "terminate", "review_id": review_id}


# --- Webhook Route (Lark Card Callback) ---

@app.post("/webhook/lark")
async def lark_webhook(request: Request):
    """Handle Lark interactive card button callbacks."""
    body = await request.json()

    # Lark card action callback format
    action = body.get("action", {})
    value = action.get("value", {})

    review_id = value.get("review_id")
    action_type = value.get("action")

    if not review_id or not action_type:
        # Might be a verification challenge
        if "challenge" in body:
            return {"challenge": body["challenge"]}
        raise HTTPException(400, "Missing review_id or action")

    if action_type == "approve":
        return await approve_review(review_id)
    elif action_type == "redo":
        # For card buttons, reason comes from the confirm dialog input
        reason = value.get("reason", body.get("action", {}).get("input", ""))
        review = read_review(review_id)
        body_data = {"reason": reason, "selected_items": []}

        # Manually handle redo logic
        if "history" not in review:
            review["history"] = []
        review["history"].append({
            "iteration": review["iteration"],
            "action": "redo",
            "reason": reason,
            "responded_at": datetime.now(timezone.utc).isoformat(),
        })
        review["iteration"] += 1
        review["status"] = "redo"
        review["response"] = {
            "action": "redo",
            "reason": reason,
            "responded_at": datetime.now(timezone.utc).isoformat(),
            "iteration": review["iteration"],
        }
        write_review(review_id, review)
        await trigger_resume_with_retry(review["project"])
        return {"status": "ok", "action": "redo", "review_id": review_id}
    elif action_type == "terminate":
        return await terminate_review(review_id)
    else:
        raise HTTPException(400, f"Unknown action: {action_type}")


# --- Asset Proxy ---

@app.get("/assets/{path:path}")
async def serve_asset(path: str):
    """Serve project assets (images, videos, etc.)."""
    full_path = PROJECT_ROOT / path
    if not full_path.exists():
        raise HTTPException(404, f"Asset not found: {path}")
    # Security: ensure path is within project
    if not str(full_path.resolve()).startswith(str(PROJECT_ROOT)):
        raise HTTPException(403, "Access denied")
    return FileResponse(full_path)


# --- Trace Viewer ---

@app.get("/trace/{session_id}", response_class=HTMLResponse)
async def trace_overview(request: Request, session_id: str):
    """View trace session overview."""
    session_dir = TRACES_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(404, f"Trace session not found: {session_id}")

    # Read session.jsonl
    session_events = []
    session_file = session_dir / "session.jsonl"
    if session_file.exists():
        for line in session_file.read_text().strip().split("\n"):
            if line:
                session_events.append(json.loads(line))

    # Read summary if exists
    summary = ""
    summary_file = session_dir / "summary.md"
    if summary_file.exists():
        summary = summary_file.read_text()

    # List all trace files
    trace_files = sorted([f.name for f in session_dir.glob("*.jsonl") if f.name != "session.jsonl"])

    return templates.TemplateResponse("trace.html", {
        "request": request,
        "session_id": session_id,
        "events": session_events,
        "summary": summary,
        "trace_files": trace_files,
    })


# --- Health Check ---

@app.get("/health")
async def health():
    return {"status": "ok", "project_root": str(PROJECT_ROOT)}


@app.post("/admin/retry-triggers")
async def retry_pending_triggers():
    """Retry all pending triggers that previously failed."""
    pending = _read_pending_triggers_unlocked()
    if not pending:
        return {"message": "no pending triggers", "count": 0}

    retried = []
    failed = []
    for project in list(pending.keys()):
        if await trigger_resume_with_retry(project):
            retried.append(project)
        else:
            failed.append(project)

    return {"retried": retried, "failed": failed, "count": len(retried)}


# --- List Reviews ---

@app.get("/reviews")
async def list_reviews():
    """List all reviews."""
    reviews = []
    for f in sorted(REVIEWS_DIR.glob("*.json")):
        data = json.loads(f.read_text())
        reviews.append({
            "id": data["id"],
            "project": data["project"],
            "checkpoint": data["checkpoint"],
            "status": data["status"],
            "iteration": data["iteration"],
            "type": data["type"],
        })
    return {"reviews": reviews}
