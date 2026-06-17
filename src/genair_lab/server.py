"""GenAIR Lab web server.

One FastAPI app that:
  - boots a single AI2-THOR robot on a dedicated worker thread (the simulator is
    not thread-safe, so every controller.step happens on that one thread),
  - streams the camera as MJPEG (`/video_feed`),
  - streams step-by-step events to the browser via SSE (`/events`),
  - takes user commands (`/chat`) and runs them through the transparent loop,
  - lets students read/edit the system prompt (`/prompt`).
"""

import asyncio
import json
import os
import queue
import threading
import time
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager

import cv2
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .abilities import parse_abilities
from .agent import Agent
from .eval_runner import parse_cases, run_eval
from .llm_wrapper import create_openai_client
from .powers import palette
from .simple import run_command
from .tool_executor import ToolExecutor

# paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
WEB_DIR = os.path.join(BASE_DIR, "web")
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "system_prompt.txt")
# Canonical default ships inside the package so "Reset to default" always works, even when prompts/ is a Docker volume.
DEFAULT_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "default_prompt.txt")

TASKS_DIR = os.getenv("TASKS_DIR", os.path.join(BASE_DIR, "tasks"))
EVAL_PATH = os.path.join(TASKS_DIR, "eval_cases.jsonl")
DEFAULT_EVAL_PATH = os.path.join(os.path.dirname(__file__), "default_eval_cases.jsonl")

ABILITIES_PATH = os.path.join(PROMPTS_DIR, "abilities.txt")
DEFAULT_ABILITIES_PATH = os.path.join(
    os.path.dirname(__file__), "default_abilities.txt"
)


def _read_packaged(path: str, fallback: str = "") -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return fallback


def _read_default_prompt() -> str:
    return _read_packaged(
        DEFAULT_PROMPT_PATH,
        "You are a household robot. Carry out the user's command by calling one tool at a time.",
    )


# global state
class State:
    def __init__(self):
        self.agent: Optional[Agent] = None
        self.executor: Optional[ToolExecutor] = None
        self.llm = None
        self.event_queue: "queue.Queue" = queue.Queue()
        self.command_queue: "queue.Queue" = queue.Queue()
        self.ready = threading.Event()  # set once the simulator is up
        self.stop_flag = threading.Event()  # set by /stop to interrupt a run
        self.shutting_down = False  # set on server shutdown so streams end
        self.busy = False
        self.history: list = []  # compact recaps of past commands (this scene)
        self.config = {
            "scene": os.getenv("SCENE", "FloorPlan1"),
            "model_name": os.getenv(
                "MODEL_NAME", os.getenv("ollama_model", "granite4.1:3b")
            ),
            "base_url": os.getenv(
                "MODEL_BASE_URL", os.getenv("ollama_url", "http://localhost:11434/v1")
            ),
            "max_steps": int(os.getenv("MAX_STEPS", "12")),
            "step_delay": float(os.getenv("STEP_DELAY", "1.0")),
            "think": os.getenv("THINK", "false").lower() not in ("0", "false", "no"),
        }


state = State()


def emit(event_type: str, message: str = "", data: Any = None):
    state.event_queue.put(
        {
            "type": event_type,
            "message": message,
            "data": data,
            "timestamp": time.time(),
        }
    )


# prompt file
def read_system_prompt() -> str:
    # Seed the active prompt from the packaged default on first run.
    if not os.path.exists(SYSTEM_PROMPT_PATH):
        write_system_prompt(_read_default_prompt())
    with open(SYSTEM_PROMPT_PATH, "r") as f:
        return f.read()


def write_system_prompt(text: str):
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    with open(SYSTEM_PROMPT_PATH, "w") as f:
        f.write(text)


def read_eval_text() -> str:
    if not os.path.exists(EVAL_PATH):
        write_eval_text(_read_packaged(DEFAULT_EVAL_PATH))
    return _read_packaged(EVAL_PATH)


def write_eval_text(text: str):
    os.makedirs(TASKS_DIR, exist_ok=True)
    with open(EVAL_PATH, "w") as f:
        f.write(text)


def read_abilities_text() -> str:
    if not os.path.exists(ABILITIES_PATH):
        write_abilities_text(_read_packaged(DEFAULT_ABILITIES_PATH))
    return _read_packaged(ABILITIES_PATH)


def write_abilities_text(text: str):
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    with open(ABILITIES_PATH, "w") as f:
        f.write(text)


def current_abilities():
    """Parse the equipped abilities, surfacing any errors to the UI."""
    ability_set, errors = parse_abilities(read_abilities_text())
    for e in errors:
        emit("SYSTEM_MSG", f"⚠ ability ignored - {e}")
    return ability_set


# the robot worker thread
def robot_worker():
    """Owns the AI2-THOR controller: builds it, then serves commands one at a time."""
    emit("SYSTEM_MSG", f"Starting simulator in {state.config['scene']} ...")
    try:
        state.agent = Agent(scene=state.config["scene"])
        state.executor = ToolExecutor(state.agent)
        state.llm = create_openai_client(
            model=state.config["model_name"],
            base_url=state.config["base_url"],
            think=state.config["think"],
        )
        state.ready.set()
        emit("SYSTEM_MSG", f"Robot ready. Model: {state.config['model_name']}")
    except Exception as e:
        emit("ERROR", f"Failed to start simulator: {e}")
        return

    while True:
        item = state.command_queue.get()
        if item is None:
            continue
        kind = item.get("kind")
        try:
            if kind == "command":
                state.busy = True
                state.stop_flag.clear()
                emit("CHAT_RESPONSE", item["message"])
                result = run_command(
                    item["message"],
                    agent=state.agent,
                    executor=state.executor,
                    abilities=current_abilities(),
                    llm=state.llm,
                    system_prompt=read_system_prompt(),
                    emit=emit,
                    should_stop=state.stop_flag.is_set,
                    max_steps=state.config["max_steps"],
                    step_delay=state.config["step_delay"],
                    history=state.history,
                )
                # Remember what just happened so the next command has context
                # (e.g. "put it back"). Keep only the recent few.
                if result.get("summary"):
                    state.history.append(result["summary"])
                    del state.history[:-6]
            elif kind == "reset":
                emit("SYSTEM_MSG", f"Resetting scene {state.config['scene']} ...")
                state.agent.controller.reset(scene=state.config["scene"])
                state.agent.held_object = None
                state.executor = ToolExecutor(state.agent)
                state.history.clear()  # the world changed - past recaps no longer apply
                emit("SYSTEM_MSG", "Scene reset.")
            elif kind == "eval":
                state.busy = True
                state.stop_flag.clear()
                run_eval(
                    item["cases"],
                    agent=state.agent,
                    make_executor=lambda: ToolExecutor(state.agent),
                    abilities=current_abilities(),
                    llm=state.llm,
                    system_prompt=read_system_prompt(),
                    scene=state.config["scene"],
                    emit=emit,
                    should_stop=state.stop_flag.is_set,
                    max_steps=state.config["max_steps"],
                    step_delay=min(state.config["step_delay"], 0.4),
                )
                # leave the scene fresh after the run
                state.agent.controller.reset(scene=state.config["scene"])
                state.agent.held_object = None
                state.executor = ToolExecutor(state.agent)
                state.history.clear()  # eval reset the world - drop chat recaps
        except Exception as e:
            emit("ERROR", f"{e}")
        finally:
            state.busy = False
            if kind in ("command", "eval"):
                emit("CHAT_FINISHED", "")


# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Boot the simulator on its own thread when the server starts (not at import).
    threading.Thread(target=robot_worker, daemon=True).start()
    yield
    # Shutdown: end the streaming loops and stop the simulator.
    state.shutting_down = True
    if state.agent:
        try:
            state.agent.stop()
        except Exception:
            pass


app = FastAPI(title="GenAIR Lab", lifespan=lifespan)

# Serve web/styles.css, web/app.js, etc. at /static/*
if os.path.isdir(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

# Serve the built MkDocs Guide at /guide (run `uv run mkdocs build` to produce it).
GUIDE_DIR = os.path.join(WEB_DIR, "guide")
if os.path.isdir(GUIDE_DIR):
    app.mount("/guide", StaticFiles(directory=GUIDE_DIR, html=True), name="guide")
else:

    @app.get("/guide", response_class=HTMLResponse)
    async def guide_not_built():
        return (
            "<h1>Guide not built yet</h1>"
            "<p>Run <code>uv run mkdocs build</code> and restart the server.</p>"
        )


class ChatRequest(BaseModel):
    message: str


class PromptRequest(BaseModel):
    prompt: str


class EvalCasesRequest(BaseModel):
    text: Optional[str] = None


class AbilitiesRequest(BaseModel):
    text: str


class ConfigRequest(BaseModel):
    scene: Optional[str] = None
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    step_delay: Optional[float] = None
    max_steps: Optional[int] = None
    think: Optional[bool] = None


@app.get("/", response_class=HTMLResponse)
async def index():
    path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return "<h1>web/index.html not found</h1>"


@app.get("/api")
async def list_api():
    """The robot's API - the fixed set of functions students equip as abilities."""
    return {"functions": palette()}


@app.get("/video_feed")
async def video_feed():
    def generate():
        # Wait for the simulator before streaming.
        state.ready.wait()
        while not state.shutting_down:
            frame = state.agent.controller.last_event.frame
            img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            ok, jpeg = cv2.imencode(".jpg", img)
            if ok:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + jpeg.tobytes()
                    + b"\r\n\r\n"
                )
            time.sleep(0.05)  # ~20 fps

    return StreamingResponse(
        generate(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/events")
async def events(request: Request):
    async def gen():
        while not state.shutting_down:
            if await request.is_disconnected():
                break
            try:
                event = state.event_queue.get_nowait()
                yield f"data: {json.dumps(event)}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/chat")
async def chat(req: ChatRequest):
    if not state.ready.is_set():
        return JSONResponse(
            {"status": "starting", "message": "Simulator still booting."},
            status_code=503,
        )
    if state.busy:
        return JSONResponse(
            {"status": "busy", "message": "Robot is already working on a command."},
            status_code=409,
        )
    state.command_queue.put({"kind": "command", "message": req.message})
    return {"status": "queued"}


@app.get("/prompt")
async def get_prompt():
    return {"prompt": read_system_prompt()}


@app.post("/prompt")
async def set_prompt(req: PromptRequest):
    write_system_prompt(req.prompt)
    return {"status": "saved"}


@app.post("/prompt/reset")
async def reset_prompt():
    default = _read_default_prompt()
    write_system_prompt(default)
    return {"prompt": default, "status": "reset"}


@app.get("/abilities")
async def get_abilities():
    text = read_abilities_text()
    _, errors = parse_abilities(text)
    return {"text": text, "errors": errors}


@app.post("/abilities")
async def set_abilities(req: AbilitiesRequest):
    write_abilities_text(req.text)
    _, errors = parse_abilities(req.text)
    return {"status": "saved", "errors": errors}


@app.post("/abilities/reset")
async def reset_abilities():
    default = _read_packaged(DEFAULT_ABILITIES_PATH)
    write_abilities_text(default)
    _, errors = parse_abilities(default)
    return {"text": default, "errors": errors, "status": "reset"}


@app.get("/eval/cases")
async def get_eval_cases():
    return {"text": read_eval_text()}


@app.post("/eval/cases")
async def set_eval_cases(req: EvalCasesRequest):
    write_eval_text(req.text)
    return {"status": "saved"}


@app.post("/eval/run")
async def run_eval_endpoint(req: EvalCasesRequest):
    if not state.ready.is_set():
        return JSONResponse({"status": "starting"}, status_code=503)
    if state.busy:
        return JSONResponse({"status": "busy"}, status_code=409)
    # If text was sent, save it first so the file stays in sync with what ran.
    if req.text is not None:
        write_eval_text(req.text)
    try:
        cases = parse_cases(req.text if req.text is not None else read_eval_text())
    except ValueError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    if not cases:
        return JSONResponse(
            {"status": "error", "message": "No cases to run."}, status_code=400
        )
    state.command_queue.put({"kind": "eval", "cases": cases})
    return {"status": "queued", "count": len(cases)}


def _native_base(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base.rstrip("/")


# Cache the Ollama check so /status polls don't probe on every tick (or block on
# a timeout). The TTL means it self-heals: if Ollama starts after the page loads,
# the next poll within a few seconds picks it up.
_ollama_check = {"base": None, "value": False, "at": 0.0}


def detect_ollama(base_url: str, ttl: float = 4.0) -> bool:
    """True if the model server looks like Ollama (has /api/tags)."""
    import urllib.request

    base = _native_base(base_url)
    now = time.time()
    if _ollama_check["base"] == base and now - _ollama_check["at"] < ttl:
        return _ollama_check["value"]
    try:
        urllib.request.urlopen(base + "/api/tags", timeout=2)
        value = True
    except Exception:
        value = False
    _ollama_check.update(base=base, value=value, at=now)
    return value


@app.get("/models")
async def list_models():
    """List models with their capabilities (for the UI dropdown + thinking toggle)."""
    try:
        import json as _json
        import urllib.request

        import openai

        client = openai.OpenAI(base_url=state.config["base_url"], api_key="ollama")
        ids = [m.id for m in client.models.list().data]

        # Per-model capabilities from Ollama's /api/show (ignored if not Ollama).
        native_base = _native_base(state.config["base_url"])
        show_url = native_base + "/api/show"
        is_ollama = detect_ollama(state.config["base_url"])

        models = []
        for mid in ids:
            caps = []
            try:
                req = urllib.request.Request(
                    show_url,
                    data=_json.dumps({"model": mid}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    caps = _json.load(r).get("capabilities", [])
            except Exception:
                pass
            models.append({"id": mid, "thinking": "thinking" in caps})

        return {"models": models, "is_ollama": is_ollama}
    except Exception as e:
        return {"models": [], "is_ollama": False, "error": str(e)}


@app.post("/stop")
async def stop():
    """Interrupt the current command or eval after the step in flight."""
    state.stop_flag.set()
    return {"status": "stopping"}


@app.post("/models/unload")
async def unload_model():
    """Unload the current model from Ollama memory via keep_alive=0."""
    import json as _json
    import urllib.request as _urlreq

    model = state.config["model_name"]
    base = state.config["base_url"].rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base.rstrip("/") + "/api/generate"
    try:
        body = _json.dumps({"model": model, "keep_alive": 0}).encode()
        req = _urlreq.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        with _urlreq.urlopen(req, timeout=10):
            pass
        return {"status": "ok", "message": f"Unloaded {model}"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)


@app.post("/reset")
async def reset():
    if not state.ready.is_set():
        return JSONResponse({"status": "starting"}, status_code=503)
    state.command_queue.put({"kind": "reset"})
    return {"status": "queued"}


@app.post("/chat/reset")
async def chat_reset():
    """Forget the conversation: clear the robot's memory of past commands.

    Does not touch the simulated world (use /reset for that) - just wipes the
    one-line recaps so the next command starts with a clean slate.
    """
    state.history.clear()
    if state.llm:
        state.llm.last_prompt_tokens = None  # reset the context readout
    emit("SYSTEM_MSG", "Chat history cleared.")
    return {"status": "ok"}


@app.post("/configure")
async def configure(req: ConfigRequest):
    changed = []
    if req.model_name or req.base_url or req.think is not None:
        state.config["model_name"] = req.model_name or state.config["model_name"]
        state.config["base_url"] = req.base_url or state.config["base_url"]
        if req.think is not None:
            state.config["think"] = req.think
            changed.append("thinking " + ("on" if req.think else "off"))
        if req.model_name or req.base_url:
            changed.append("model")
        state.llm = create_openai_client(
            model=state.config["model_name"],
            base_url=state.config["base_url"],
            think=state.config["think"],
        )
    if req.step_delay is not None:
        state.config["step_delay"] = req.step_delay
        changed.append("step_delay")
    if req.max_steps is not None:
        state.config["max_steps"] = req.max_steps
        changed.append("max_steps")
    if req.scene and req.scene != state.config["scene"]:
        state.config["scene"] = req.scene
        state.command_queue.put({"kind": "reset"})
        changed.append("scene")
    emit("SYSTEM_MSG", f"Updated: {', '.join(changed) or 'nothing'}")
    return {"status": "ok", "config": state.config}


@app.get("/status")
async def status():
    is_ollama = await asyncio.to_thread(detect_ollama, state.config["base_url"])
    return {
        "ready": state.ready.is_set(),
        "busy": state.busy,
        "config": state.config,
        "is_ollama": is_ollama,
        "context_tokens": getattr(state.llm, "last_prompt_tokens", None),
        "held_object": (
            state.agent.held_object.split("|")[0]
            if state.agent and state.agent.held_object
            else None
        ),
    }
