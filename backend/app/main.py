"""NOVA's local API and page. Only reachable from this computer (127.0.0.1)."""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.assistant import Assistant, AssistantError
from app.config import load_config

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="NOVA")
# Refuse requests addressed to any other host name (blocks DNS-rebinding tricks).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
assistant = Assistant(load_config())


def require_nova_header(x_nova: str | None = Header(default=None)) -> None:
    """Other websites can't send this header without our permission, so they can't press buttons."""
    if x_nova != "1":
        raise HTTPException(status_code=403, detail="Missing X-Nova header.")


class CommandIn(BaseModel):
    text: str = Field(max_length=300)


def _run(action, *args) -> dict:
    try:
        action(*args)
    except AssistantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return assistant.status()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status() -> dict:
    return assistant.status()


@app.post("/api/listen/start", dependencies=[Depends(require_nova_header)])
def listen_start() -> dict:
    return _run(assistant.start_listening)


@app.post("/api/listen/stop", dependencies=[Depends(require_nova_header)])
def listen_stop() -> dict:
    return _run(assistant.stop_listening)


@app.post("/api/handsfree/start", dependencies=[Depends(require_nova_header)])
def handsfree_start() -> dict:
    return _run(assistant.start_hands_free)


@app.post("/api/handsfree/stop", dependencies=[Depends(require_nova_header)])
def handsfree_stop() -> dict:
    return _run(assistant.stop_hands_free)


@app.post("/api/command", dependencies=[Depends(require_nova_header)])
def command(body: CommandIn) -> dict:
    return _run(assistant.submit_text, body.text)


@app.post("/api/cancel", dependencies=[Depends(require_nova_header)])
def cancel() -> dict:
    return _run(assistant.cancel)