"""
middleware.py — sanitização, XSS, CSRF e headers de segurança.
Stdlib apenas. Para uso em frameworks (FastAPI/Flask) como helpers puros.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import re
import secrets
import time
from typing import Dict, Optional

# --- SQL sanitização (defesa em profundidade; use prepared statements como principal) ---

_SQL_DANGEROUS = re.compile(
    r"(\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|EXEC|EXECUTE|TRUNCATE)\b|--|;|/\*|\*/|'|\"|\x00)",
    re.IGNORECASE,
)


def sanitize_sql(value: str, max_length: int = 1000) -> str:
    """
    Neutraliza padrões perigosos de SQL injection.
    NÃO substitui prepared statements; é camada extra.
    - Trunca em max_length
    - Escapa aspas simples dobrando ('->'')
    - Remove comentários -- e /* */
    - Remove null bytes
    """
    if not isinstance(value, str):
        value = str(value)
    # corta length primeiro para evitar DoS
    value = value[:max_length]
    # remove null bytes
    value = value.replace("\x00", "")
    # remove comentários SQL
    value = re.sub(r"--.*?$", "", value, flags=re.MULTILINE)
    value = re.sub(r"/\*.*?\*/", "", value, flags=re.DOTALL)
    # escapa aspas simples (padrão SQL)
    value = value.replace("'", "''")
    # remove ; solto que não foi capturado (mantém se for parte segura? -> remove)
    # Não removemos tudo, apenas sanitizamos; ideal é usar placeholder
    return value.strip()


def is_sql_safe(value: str) -> bool:
    """Retorna True se não contém padrões perigosos óbvios."""
    return not bool(_SQL_DANGEROUS.search(value))


# --- XSS ---


def escape_html(value: str) -> str:
    """Escapa HTML para mitigar XSS. Usa html.escape."""
    if not isinstance(value, str):
        value = str(value)
    return html.escape(value, quote=True)


def strip_tags(value: str) -> str:
    """Remove tags HTML simples (fallback)."""
    return re.sub(r"<[^>]*>", "", value)


# --- CSRF ---


def _hmac_secret() -> bytes:
    sec = os.getenv("HMAC_SECRET")
    if sec:
        return sec.encode()
    # fallback efêmero (aviso: tokens não persistirão entre restarts)
    return b"dev-only-hmac-secret-change-me"


def csrf_token(expires_in: int = 3600) -> str:
    """
    Gera token CSRF assinado: base64( timestamp . random . hmac )
    Formato: <ts>.<rand>.<sig>
    """
    ts = str(int(time.time()) + expires_in)
    rand = secrets.token_urlsafe(32)
    payload = f"{ts}.{rand}".encode()
    sig = hmac.new(_hmac_secret(), payload, hashlib.sha256).hexdigest()
    token = f"{ts}.{rand}.{sig}"
    return base64.urlsafe_b64encode(token.encode()).decode()


def verify_csrf(token: str, _unused: Optional[str] = None) -> bool:
    """Verifica token CSRF (assinatura + expiração)."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        # canonical-check: rejeita tokens adulterados (ex: token+"x")
        canonical = base64.urlsafe_b64encode(raw.encode()).decode()
        if not hmac.compare_digest(canonical, token):
            return False
        parts = raw.split(".")
        if len(parts) != 3:
            return False
        ts_str, rand, sig = parts
        payload = f"{ts_str}.{rand}".encode()
        expected = hmac.new(_hmac_secret(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return False
        if int(ts_str) < int(time.time()):
            return False  # expirado
        return True
    except Exception:
        return False


# --- Security Headers ---

security_headers: Dict[str, str] = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",  # noqa: E501
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-XSS-Protection": "0",  # desativa XSS auditor (CSP é preferido)
}


def get_security_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Retorna cópia dos headers com opcionais extras."""
    h = dict(security_headers)
    if extra:
        h.update(extra)
    return h


# Alias compatível com spec: security_headers dict + funções
# (mantém ditto acima)


# --- Rate limit helper simples (para middleware) ---
def is_rate_limited(
    timestamps: list[float],
    window_sec: int = 60,
    max_req: int = 60,
    now: Optional[float] = None,
) -> bool:
    now = now if now is not None else time.time()
    # conta requisições na janela
    count = sum(1 for t in timestamps if now - t < window_sec)
    return count > max_req
