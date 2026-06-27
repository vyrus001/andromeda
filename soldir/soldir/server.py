from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import asynccontextmanager
import json
import os
import random
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from soldir.chat import ChatProviderError, complete_chat
from soldir.graph_store import GraphStore
from soldir.models import BytecodeJob, BytecodeJobRequest, ChatRequest, CheckInPayload, model_dump, utc_now_iso
from soldir.tinkr_service import TinkrBuildError, TinkrService


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "soldir.db"
NODE_MODULES = ROOT / "node_modules"
TEST_MODE_ENV = "SOLDIR_TEST_MODE"

store = GraphStore(DB_PATH)
tinkr = TinkrService()
tailor_clients: dict[str, WebSocket] = {}
tailor_profiles: dict[str, dict[str, Any]] = {}
tailor_targets: dict[str, str] = {}
jobs: dict[str, BytecodeJob] = {}
pending_jobs: dict[str, list[dict[str, Any]]] = {}


def is_test_mode() -> bool:
    return os.getenv(TEST_MODE_ENV, "").lower() in {"1", "true", "yes", "on"}


class WebSocketHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for client in list(self._clients):
            try:
                await client.send_json(payload)
            except RuntimeError:
                stale.append(client)
        for client in stale:
            self.disconnect(client)


hub = WebSocketHub()
ux_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if is_test_mode():
        await start_ux_test()
    try:
        yield
    finally:
        await stop_ux_test()


app = FastAPI(title="Soldir", lifespan=lifespan)


def _mount_static() -> None:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    d3_dist = NODE_MODULES / "d3" / "dist"
    if d3_dist.exists():
        app.mount("/vendor/d3", StaticFiles(directory=d3_dist), name="d3")

    os_logo_candidates = [
        NODE_MODULES / "@egoistdeveloper" / "operating-system-logos" / "src",
        NODE_MODULES / "operating-system-logos" / "src",
    ]
    for candidate in os_logo_candidates:
        if candidate.exists():
            app.mount("/vendor/os-logos", StaticFiles(directory=candidate), name="os-logos")
            break


_mount_static()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "nodes": len(store.snapshot()["nodes"]),
        "tailor_clients": sorted(tailor_clients),
    }


@app.get("/api/graph")
async def get_graph() -> dict[str, Any]:
    return store.snapshot()


@app.post("/api/checkins")
async def post_checkin(request: Request, checkin: CheckInPayload) -> dict[str, Any]:
    snapshot = store.upsert_checkin(checkin)
    instance_id = checkin.node_id
    if checkin.profile is not None:
        tailor_profiles[instance_id] = checkin.profile
    if checkin.target_triple:
        tailor_targets[instance_id] = checkin.target_triple
    await hub.broadcast({"type": "graph_update", "graph": snapshot})
    return {
        "ok": True,
        "graph": snapshot,
        "tailor_ws_url": tailor_ws_url(request, instance_id),
        "tailor_ws_path": f"/ws/tailor/{quote(instance_id, safe='')}",
    }


@app.post("/api/jobs/macos-say-smoke")
async def post_macos_say_smoke(request: BytecodeJobRequest) -> dict[str, Any]:
    if request.mode != "macos_say":
        raise HTTPException(status_code=400, detail=f"Unsupported job mode: {request.mode}")

    target_instance_id = choose_tailor_target(request)
    job_id = uuid.uuid4().hex
    job = BytecodeJob(
        id=job_id,
        target_instance_id=target_instance_id,
        target_triple=request.target_triple,
        mode=request.mode,
        message=request.message,
        status="building",
        created_at=utc_now_iso(),
        metadata={**request.metadata},
    )
    jobs[job_id] = job

    try:
        artifact = await tinkr.build_macos_say_blob(
            message=request.message,
            target_triple=request.target_triple,
            job_id=job_id,
        )
    except TinkrBuildError as exc:
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = utc_now_iso()
        return {"ok": False, "job": model_dump(job)}

    job.metadata.update(
        {
            "blob_size": len(artifact.blob),
            "source_path": str(artifact.source_path),
            "blob_path": str(artifact.blob_path),
            "tinkr_stdout": artifact.stdout,
            "tinkr_stderr": artifact.stderr,
        }
    )
    payload = {
        "type": "execute_bytecode",
        "job_id": job.id,
        "target_triple": job.target_triple,
        "mode": job.mode,
        "label": f"macOS say: {job.message}",
        "bytecode_b64": base64.b64encode(artifact.blob).decode("ascii"),
        "metadata": {
            "message": job.message,
            "blob_size": len(artifact.blob),
            **request.metadata,
        },
    }
    await dispatch_tailor_job(target_instance_id, payload)
    return {"ok": True, "job": model_dump(job)}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": model_dump(job)}


@app.get("/api/jobs")
async def list_jobs() -> dict[str, Any]:
    return {"ok": True, "jobs": [model_dump(job) for job in jobs.values()]}



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await hub.connect(websocket)
    await websocket.send_json(
        {
            "type": "hello",
            "test_mode": is_test_mode(),
            "ux_test": ux_task is not None and not ux_task.done(),
        }
    )
    await websocket.send_json({"type": "graph_snapshot", "graph": store.snapshot()})
    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            await handle_ws_message(websocket, message)
    except WebSocketDisconnect:
        hub.disconnect(websocket)


@app.websocket("/ws/tailor/{instance_id}")
async def tailor_websocket_endpoint(websocket: WebSocket, instance_id: str) -> None:
    await websocket.accept()
    tailor_clients[instance_id] = websocket
    await websocket.send_json(
        {
            "type": "hello",
            "instance_id": instance_id,
            "pending_jobs": len(pending_jobs.get(instance_id, [])),
        }
    )
    await flush_pending_tailor_jobs(instance_id)
    try:
        while True:
            message = await websocket.receive_json()
            await handle_tailor_message(instance_id, message)
    except WebSocketDisconnect:
        if tailor_clients.get(instance_id) is websocket:
            del tailor_clients[instance_id]


async def handle_ws_message(websocket: WebSocket, message: dict[str, Any]) -> None:
    message_type = message.get("type")
    if message_type == "checkin":
        payload = CheckInPayload(**message.get("payload", {}))
        snapshot = store.upsert_checkin(payload)
        await hub.broadcast({"type": "graph_update", "graph": snapshot})
        return

    if message_type == "chat":
        request = ChatRequest(**message.get("payload", {}))
        await websocket.send_json({"type": "chat_started", "provider": request.provider})
        try:
            response = await complete_chat(request, store.snapshot())
        except ChatProviderError as exc:
            await websocket.send_json({"type": "chat_error", "message": str(exc)})
            return
        await websocket.send_json(
            {
                "type": "chat_response",
                "provider": request.provider,
                "message": response,
            }
        )


async def handle_tailor_message(instance_id: str, message: dict[str, Any]) -> None:
    if message.get("type") != "execution_result":
        return
    job_id = str(message.get("job_id", ""))
    job = jobs.get(job_id)
    if not job:
        return
    job.status = "completed" if int(message.get("returncode", 1) or 0) == 0 else "failed"
    job.completed_at = utc_now_iso()
    job.returncode = int(message.get("returncode", 0) or 0)
    job.stdout = str(message.get("stdout", ""))
    job.stderr = str(message.get("stderr", ""))
    job.metadata.update({"completed_by": instance_id})
    await hub.broadcast({"type": "job_update", "job": model_dump(job)})


def tailor_ws_url(request: Request, instance_id: str) -> str:
    scheme = "wss" if request.url.scheme == "https" else "ws"
    encoded = quote(instance_id, safe="")
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}/ws/tailor/{encoded}"


def choose_tailor_target(request: BytecodeJobRequest) -> str:
    if request.target_instance_id:
        return request.target_instance_id
    for instance_id, target_triple in tailor_targets.items():
        if target_triple == request.target_triple and instance_id in tailor_clients:
            return instance_id
    for instance_id, target_triple in tailor_targets.items():
        if target_triple == request.target_triple:
            return instance_id
    for instance_id in tailor_clients:
        return instance_id
    raise HTTPException(
        status_code=409,
        detail="No Tailor instance is checked in. Start tools/tailor-listen.py on the host first.",
    )


async def dispatch_tailor_job(instance_id: str, payload: dict[str, Any]) -> None:
    job = jobs[payload["job_id"]]
    websocket = tailor_clients.get(instance_id)
    if websocket is None:
        pending_jobs.setdefault(instance_id, []).append(payload)
        job.status = "queued"
        return
    await websocket.send_json(payload)
    job.status = "dispatched"
    job.dispatched_at = utc_now_iso()
    await hub.broadcast({"type": "job_update", "job": model_dump(job)})


async def flush_pending_tailor_jobs(instance_id: str) -> None:
    queued = pending_jobs.pop(instance_id, [])
    for payload in queued:
        await dispatch_tailor_job(instance_id, payload)


async def start_ux_test() -> dict[str, Any]:
    global ux_task
    if ux_task is not None and not ux_task.done():
        return {"ok": True, "running": True}
    await seed_ux_graph()
    ux_task = asyncio.create_task(ux_loop())
    await hub.broadcast({"type": "ux_status", "running": True})
    return {"ok": True, "running": True}


async def stop_ux_test() -> dict[str, Any]:
    global ux_task
    if ux_task is not None and not ux_task.done():
        ux_task.cancel()
        try:
            await ux_task
        except asyncio.CancelledError:
            pass
    ux_task = None
    await hub.broadcast({"type": "ux_status", "running": False})
    return {"ok": True, "running": False}


UX_NODES = [
    {
        "instance_id": "neon-mac-01",
        "hostname": "neon-mac-01",
        "os": "macos",
        "arch": "arm64",
        "ip_addresses": ["10.7.0.10"],
        "communicated_with": ["debian-relay-02", "win-build-04"],
        "metadata": {"role": "operator"},
    },
    {
        "instance_id": "debian-relay-02",
        "hostname": "debian-relay-02",
        "os": "debian",
        "arch": "x86_64",
        "ip_addresses": ["10.7.0.20"],
        "reachable_by": ["neon-mac-01"],
        "communicated_with": ["ubuntu-sensor-03", "arch-lab-05"],
        "metadata": {"role": "relay"},
    },
    {
        "instance_id": "ubuntu-sensor-03",
        "hostname": "ubuntu-sensor-03",
        "os": "ubuntu",
        "arch": "aarch64",
        "ip_addresses": ["10.7.0.30"],
        "reachable_by": ["debian-relay-02"],
        "metadata": {"role": "sensor"},
    },
    {
        "instance_id": "win-build-04",
        "hostname": "win-build-04",
        "os": "windows",
        "arch": "x86_64",
        "ip_addresses": ["10.7.0.40"],
        "reachable_by": ["neon-mac-01"],
        "metadata": {"role": "build"},
    },
    {
        "instance_id": "arch-lab-05",
        "hostname": "arch-lab-05",
        "os": "arch",
        "arch": "x86_64",
        "ip_addresses": ["10.7.0.50"],
        "communicated_with": ["freebsd-store-06"],
        "metadata": {"role": "lab"},
    },
    {
        "instance_id": "freebsd-store-06",
        "hostname": "freebsd-store-06",
        "os": "freebsd",
        "arch": "x86_64",
        "ip_addresses": ["10.7.0.60"],
        "reachable_by": ["arch-lab-05", "debian-relay-02"],
        "metadata": {"role": "storage"},
    },
]


async def seed_ux_graph() -> None:
    for node in UX_NODES:
        store.upsert_checkin(CheckInPayload(**node))
    await hub.broadcast({"type": "graph_update", "graph": store.snapshot()})


async def ux_loop() -> None:
    while True:
        await asyncio.sleep(3.5)
        source = random.choice(UX_NODES)
        candidates = [node for node in UX_NODES if node["instance_id"] != source["instance_id"]]
        target = random.choice(candidates)
        edge_type = random.choice(["HAS_COMMUNICATED_WITH", "IS_REACHABLE_BY"])
        payload = dict(source)
        payload["edges"] = [
            {
                "source": source["instance_id"],
                "target": target["instance_id"],
                "type": edge_type,
                "protocol": random.choice(["ssh", "https", "grpc", "tailor"]),
                "port": random.choice([22, 443, 8080, 9000]),
                "metadata": {"ux_test": True},
            }
        ]
        snapshot = store.upsert_checkin(CheckInPayload(**payload))
        await hub.broadcast({"type": "graph_update", "graph": snapshot})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Soldir.")
    parser.add_argument("--test-mode", action="store_true", help="enable UX test graph at startup")
    parser.add_argument("--host", default=os.getenv("SOLDIR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SOLDIR_PORT", "8765")))
    args = parser.parse_args()
    if args.test_mode:
        os.environ[TEST_MODE_ENV] = "1"

    uvicorn.run(
        "soldir.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
