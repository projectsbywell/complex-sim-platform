"""Simulation routes: kinds, CRUD, step, export, report."""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from .auth import get_current_user
from .cache import _MISS, cache
from .sim_service import ExportUnavailableError, WorkLimitError, service
from .store import Simulation, store

router = APIRouter(prefix="/api/simulations", tags=["simulations"])

KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
ExportFormat = Literal["csv", "json", "parquet", "hdf5"]


# ---------------------------------------------------------------------------
# Request validation (anti-injection: bounded depth, keys, lengths)
# ---------------------------------------------------------------------------


def validate_params(value: Any, depth: int = 0) -> None:
    """Recursively validate simulation params: shape, keys and scalar bounds."""
    if depth > 4:
        raise ValueError("params nested deeper than 4 levels")
    if isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("params dict has more than 64 keys")
        for key, item in value.items():
            if not isinstance(key, str) or not KEY_RE.match(key):
                raise ValueError(f"invalid params key {key!r}")
            if len(key) > 64:
                raise ValueError("params key too long")
            validate_params(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 10_000:
            raise ValueError("params list longer than 10_000 items")
        for item in value:
            validate_params(item, depth + 1)
    elif isinstance(value, str):
        if len(value) > 256:
            raise ValueError("params string longer than 256 chars")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError("non-finite numbers are not allowed in params")
    elif isinstance(value, bool) or value is None:
        pass
    else:
        raise ValueError(f"unsupported params value type {type(value).__name__}")


class CreateSimRequest(BaseModel):
    kind: str = Field(..., min_length=1, max_length=32)
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _kind_ok(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in service.kinds():
            raise ValueError(
                f"unknown simulation kind {value!r}; allowed: {service.kinds()}"
            )
        return value

    @field_validator("params")
    @classmethod
    def _params_ok(cls, value: dict) -> dict:
        validate_params(value)
        return value


class StepRequest(BaseModel):
    dt: float = Field(default=0.016, gt=0.0, le=10.0)
    steps: int = Field(default=1, ge=1, le=10_000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sim_or_404(sim_id: str) -> Simulation:
    sim = store.get_simulation(sim_id)
    if sim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulation not found")
    return sim


def _authorize(sim: Simulation, user) -> Simulation:
    """Owner or admin only; non-matching ids surface as 404 (no enumeration)."""
    if user.role != "admin" and sim.owner != user.username:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulation not found")
    return sim


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/kinds",
    summary="List supported simulation kinds",
    description="Public; returns the bare list the frontend contract expects.",
)
def list_kinds():
    return service.kinds()


@router.get("", summary="List simulations (admin sees all, users see their own)")
def list_simulations(user=Depends(get_current_user)) -> list[dict]:
    if user.role == "admin":
        sims = store.list_simulations()
    else:
        sims = store.list_simulations(owner=user.username)
    sims.sort(key=lambda s: s.updated_at, reverse=True)
    return [s.to_dict(include_state=False) for s in sims]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a simulation")
def create_simulation(req: CreateSimRequest, user=Depends(get_current_user)) -> dict:
    try:
        sim = service.create(req.kind, req.params, user.username)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return sim.to_dict()


@router.get("/{sim_id}", summary="Get simulation state (cached 60s)")
def get_simulation(sim_id: str, user=Depends(get_current_user)) -> dict:
    sim = _authorize(_sim_or_404(sim_id), user)
    hit = cache.get(f"sim:{sim_id}")
    if hit is not _MISS:
        return hit
    payload = sim.to_dict()
    cache.put(f"sim:{sim_id}", payload)
    return payload


@router.post("/{sim_id}/step", summary="Advance the simulation by dt x steps")
def step_simulation(
    sim_id: str, req: StepRequest, user=Depends(get_current_user)
) -> dict:
    _authorize(_sim_or_404(sim_id), user)
    try:
        state, steps_done, t = service.step(sim_id, req.dt, req.steps)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulation not found")
    except WorkLimitError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"{exc} (work budget exceeded; reduza steps ou dt)",
            headers={"retry-after": "60"},
        )
    return {
        "state": state,
        "steps_done": steps_done,
        "dt": req.dt,
        "steps": req.steps,
        "t": t,
    }


@router.get("/{sim_id}/export", summary="Export simulation data as a file download")
def export_simulation(
    sim_id: str,
    format: ExportFormat = Query("json", description="csv | json | parquet | hdf5"),
    user=Depends(get_current_user),
) -> Response:
    _authorize(_sim_or_404(sim_id), user)
    try:
        filename, media, payload = service.export_file(sim_id, format)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulation not found")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except ExportUnavailableError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc))
    return Response(
        content=payload,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{sim_id}/report", summary="Generate summary, stats and charts data")
def report_simulation(sim_id: str, user=Depends(get_current_user)) -> dict:
    _authorize(_sim_or_404(sim_id), user)
    try:
        return service.report(sim_id)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Simulation not found")


@router.delete("/{sim_id}", summary="Delete a simulation")
def delete_simulation(sim_id: str, user=Depends(get_current_user)) -> dict:
    _authorize(_sim_or_404(sim_id), user)
    service.delete(sim_id)
    return {"deleted": True, "id": sim_id}
