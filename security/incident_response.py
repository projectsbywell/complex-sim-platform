"""
incident_response.py — cria incidente, classifica severidade e notifica via AuditLogger
Uso:
  python security/incident_response.py --title "XSS attempt" --severity high
  python -c "from security.incident_response import create_incident; create_incident('test', severity='medium')"
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from security.audit import AuditLogger

SEVERITIES = ("low", "medium", "high", "critical")
SEVERITY_SCORE = {"low": 1, "medium": 2, "high": 3, "critical": 4}

INCIDENTS_DIR = Path(os.getenv("INCIDENTS_DIR") or Path(__file__).parent.parent / "incidents")
AUDIT_PATH = os.getenv("AUDIT_LOG_PATH") or str(Path(__file__).parent.parent / "logs" / "audit.log")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_incident(
    title: str,
    severity: str = "medium",
    description: str = "",
    indicators: Optional[List[str]] = None,
    actor: str = "system",
    notify: bool = True,
    audit_path: Optional[str] = None,
) -> Dict[str, Any]:
    severity = severity.lower()
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    incident_id = f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    incident: Dict[str, Any] = {
        "id": incident_id,
        "title": title,
        "severity": severity,
        "severity_score": SEVERITY_SCORE[severity],
        "description": description or title,
        "indicators": indicators or [],
        "status": "open",
        "created_at": _now_iso(),
        "actor": actor,
        "phase": "identification",
        "next_steps": _next_steps(severity),
    }
    # persiste arquivo
    INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INCIDENTS_DIR / f"{incident_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(incident, f, indent=2, ensure_ascii=False)

    # também markdown resumo
    md_path = INCIDENTS_DIR / f"{incident_id}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {incident_id} — {title}\n\n")
        f.write(f"- **Severity**: {severity} ({SEVERITY_SCORE[severity]}/4)\n")
        f.write(f"- **Status**: open\n- **Created**: {incident['created_at']}\n")
        f.write(f"- **Indicators**: {', '.join(indicators or ['-'])}\n\n")
        f.write(f"## Description\n{incident['description']}\n\n")
        f.write("## Next steps\n")
        for s in incident["next_steps"]:
            f.write(f"- [ ] {s}\n")

    if notify:
        logger = AuditLogger(path=audit_path or AUDIT_PATH)
        logger.log(
            actor=actor,
            action="incident_created",
            resource=incident_id,
            details={"title": title, "severity": severity, "indicators": indicators or []},
        )
        # log extra para critical/high
        if severity in ("high", "critical"):
            print(f"[ALERT] {incident_id} severity={severity} — notificação registrada em audit log")

    print(f"[incident] {incident_id} criado em {out_path}")
    return incident


def _next_steps(severity: str) -> List[str]:
    base = ["Preservar evidência (copiar audit.log, metrics)", "Classificar e atribuir owner", "Conter (isolar host/IP)"]
    if severity in ("high", "critical"):
        base += ["Erradicar causa raiz + rebuild imagens", "Rotacionar segredos", "Comunicar stakeholders"]
    base += ["Recuperar de backup íntegro se necessário", "Postmortem em 5 dias"]
    return base


def update_incident(incident_id: str, status: Optional[str] = None, phase: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    path = INCIDENTS_DIR / f"{incident_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"incidente não encontrado: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if status:
        data["status"] = status
    if phase:
        data["phase"] = phase
    if notes:
        data.setdefault("notes", []).append({"at": _now_iso(), "text": notes})
    data["updated_at"] = _now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Incident response CLI")
    p.add_argument("--title", required=True, help="título do incidente")
    p.add_argument("--severity", default="medium", choices=SEVERITIES)
    p.add_argument("--description", default="")
    p.add_argument("--indicators", nargs="*", default=[])
    p.add_argument("--actor", default="sec-cli")
    args = p.parse_args()
    create_incident(args.title, severity=args.severity, description=args.description, indicators=args.indicators, actor=args.actor)
