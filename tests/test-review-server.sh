#!/usr/bin/env bash
# tests/test-review-server.sh — review-server helper regression tests

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" - <<'PY' "$ROOT_DIR"
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

root = Path(sys.argv[1])
tmp = Path(tempfile.mkdtemp(prefix="review-server-test-"))

fastapi = types.ModuleType("fastapi")

class DummyHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class DummyFastAPI:
    def __init__(self, *args, **kwargs):
        pass
    def mount(self, *args, **kwargs):
        return None
    def get(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator
    def post(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

fastapi.FastAPI = DummyFastAPI
fastapi.Request = object
fastapi.HTTPException = DummyHTTPException
sys.modules["fastapi"] = fastapi

responses = types.ModuleType("fastapi.responses")
responses.HTMLResponse = object
responses.FileResponse = object
responses.JSONResponse = object
sys.modules["fastapi.responses"] = responses

staticfiles = types.ModuleType("fastapi.staticfiles")
class DummyStaticFiles:
    def __init__(self, *args, **kwargs):
        pass
staticfiles.StaticFiles = DummyStaticFiles
sys.modules["fastapi.staticfiles"] = staticfiles

templating = types.ModuleType("fastapi.templating")
class DummyTemplates:
    def __init__(self, *args, **kwargs):
        pass
    def TemplateResponse(self, *args, **kwargs):
        return {"template": args[0]}
templating.Jinja2Templates = DummyTemplates
sys.modules["fastapi.templating"] = templating

os.environ["PROJECT_ROOT"] = str(tmp)
server_path = root / "review-server" / "server.py"
spec = importlib.util.spec_from_file_location("review_server_under_test", server_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

module.STATE_DIR = tmp / "state"
module.REVIEWS_DIR = module.STATE_DIR / "reviews"
module.TRACES_DIR = module.STATE_DIR / "traces"
module.PENDING_TRIGGERS_FILE = module.STATE_DIR / "pending_triggers.json"
module.REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
module.STATE_DIR.mkdir(parents=True, exist_ok=True)

module._save_pending_trigger("alpha")
module._save_pending_trigger("beta")
pending = json.loads(module.PENDING_TRIGGERS_FILE.read_text())
assert set(pending) == {"alpha", "beta"}, pending
module._remove_pending_trigger("alpha")
pending = json.loads(module.PENDING_TRIGGERS_FILE.read_text())
assert set(pending) == {"beta"}, pending

async def fake_retry(project: str, max_retries: int = 3) -> bool:
    return project == "beta"

module.trigger_resume_with_retry = fake_retry
result = asyncio.run(module.retry_pending_triggers())
assert result["retried"] == ["beta"], result
assert result["failed"] == [], result
assert result["count"] == 1, result

print("PASS: review-server")
PY
