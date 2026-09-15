"""WebSocket endpoint: real-time stepping with multi-client broadcast.

Client connects to ``/ws/simulations/{sim_id}?token=<jwt>`` (query params,
because browsers cannot set headers on WebSocket upgrade), receives the
current state, then sends ``{"dt": 0.016, "steps": 1}`` to advance the
simulation. The resulting state is broadcast to every client connected to the
same simulation room.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from . import monitoring
from .auth import decode_token
from .config import settings
from .ratelimit import WindowGuard
from .sim_service import WorkLimitError, service
from .store import store

logger = logging.getLogger("complex_sim.ws")


class ConnectionManager:
    """Per-simulation rooms of connected WebSockets."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._lock = threading.Lock()

    def connect(self, room: str, ws: WebSocket) -> None:
        with self._lock:
            self._rooms.setdefault(room, set()).add(ws)

    def disconnect(self, room: str, ws: WebSocket) -> None:
        with self._lock:
            room_set = self._rooms.get(room)
            if room_set:
                room_set.discard(ws)
                if not room_set:
                    self._rooms.pop(room, None)

    def room_size(self, room: str) -> int:
        with self._lock:
            return len(self._rooms.get(room, ()))

    async def broadcast(self, room: str, payload: dict) -> int:
        with self._lock:
            targets = list(self._rooms.get(room, ()))
        receivers = 0
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
                receivers += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(room, ws)
        return receivers


manager = ConnectionManager()
ws_guard = WindowGuard(limit=settings.ws_message_limit_per_minute, window=60.0)


def _extract_token(websocket: WebSocket) -> str | None:
    token = websocket.query_params.get("token")
    if token:
        return token
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def _authenticate(websocket: WebSocket) -> Any | None:
    token = _extract_token(websocket)
    if not token:
        return None
    try:
        payload = decode_token(token)
        username = payload.get("sub")
        if not username:
            return None
        return store.get_user(username)
    except Exception:
        return None


async def simulations_ws(websocket: WebSocket, sim_id: str) -> None:
    ip = websocket.client.host if websocket.client else "unknown"

    user = _authenticate(websocket)
    if user is None:
        await websocket.close(code=4401, reason="unauthorized")
        return

    sim = store.get_simulation(sim_id)
    if sim is None or (user.role != "admin" and sim.owner != user.username):
        await websocket.close(code=4403, reason="forbidden")
        return

    await websocket.accept()
    manager.connect(sim_id, websocket)
    monitoring.registry.incr("ws_connections")
    monitoring.registry.incr("ws_active")
    logger.info(
        "ws_connected",
        extra={"simulation_id": sim_id, "user": user.username, "ip": ip},
    )

    try:
        await websocket.send_json(
            {
                "type": "init",
                "simulation_id": sim_id,
                "kind": sim.kind,
                "steps_done": sim.steps_done,
                "state": sim.state,
                "clients": manager.room_size(sim_id),
            }
        )

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                await websocket.send_json(
                    {"type": "error", "detail": "invalid JSON message"}
                )
                continue
            if not isinstance(msg, dict):
                await websocket.send_json(
                    {"type": "error", "detail": "message must be a JSON object"}
                )
                continue

            action = msg.get("action", "step")

            if action == "get_state":
                current = store.get_simulation(sim_id)
                if current is None:
                    await websocket.send_json(
                        {"type": "error", "detail": "simulation deleted"}
                    )
                    break
                await websocket.send_json(
                    {
                        "type": "state",
                        "simulation_id": sim_id,
                        "dt": 0.0,
                        "steps": 0,
                        "steps_done": current.steps_done,
                        "t": float(current.state.get("t", 0.0)),
                        "state": current.state,
                        "clients": manager.room_size(sim_id),
                    }
                )
                continue

            if action != "step":
                await websocket.send_json(
                    {
                        "type": "error",
                        "detail": f"unknown action {action!r}; use 'step' or 'get_state'",
                    }
                )
                continue

            # per-connection message throttle
            if not ws_guard.allow(f"ws:{sim_id}:{ip}"):
                await websocket.send_json(
                    {
                        "type": "error",
                        "detail": "message rate limit exceeded",
                        "retry_after": 60,
                    }
                )
                await websocket.close(code=1008, reason="message rate limit")
                break

            try:
                dt = float(msg.get("dt", 0.016))
                steps = int(msg.get("steps", 1))
            except (TypeError, ValueError):
                await websocket.send_json(
                    {"type": "error", "detail": "dt and steps must be numbers"}
                )
                continue
            if not (0.0 < dt <= 10.0):
                await websocket.send_json(
                    {"type": "error", "detail": "dt must be in (0, 10]"}
                )
                continue
            if not (1 <= steps <= 10_000):
                await websocket.send_json(
                    {"type": "error", "detail": "steps must be in [1, 10000]"}
                )
                continue

            try:
                state, steps_done, t = await run_in_threadpool(
                    service.step, sim_id, dt, steps
                )
            except KeyError:
                await websocket.send_json(
                    {"type": "error", "detail": "simulation not found"}
                )
                break
            except WorkLimitError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                continue

            payload = {
                "type": "state",
                "simulation_id": sim_id,
                "dt": dt,
                "steps": steps,
                "steps_done": steps_done,
                "t": t,
                "state": state,
                "clients": manager.room_size(sim_id),
            }
            await manager.broadcast(sim_id, payload)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(
            "ws_error",
            extra={"simulation_id": sim_id, "user": user.username, "exc": repr(exc)},
        )
        try:
            await websocket.send_json(
                {"type": "error", "detail": f"server error: {exc}"}
            )
        except Exception:
            pass
    finally:
        manager.disconnect(sim_id, websocket)
        monitoring.registry.decr("ws_active")
        logger.info(
            "ws_disconnected",
            extra={"simulation_id": sim_id, "user": user.username, "ip": ip},
        )
