# Security — Complex Sim Platform

Módulo de segurança transversal: sanitização, criptografia em repouso, auditoria, detecção de anomalias e resposta a incidentes.

## Estrutura

```
security/
├── README.md
├── middleware.py          # sanitize_sql, escape_html, CSRF, headers
├── crypto.py              # AES-GCM (cryptography) ou fallback XOR+base64 + hashing + TLS checklist
├── audit.py               # AuditLogger JSON lines
├── anomaly.py             # AnomalyDetector (z-score + taxa)
├── incident_response.md   # playbook 6 fases
└── incident_response.py   # cria incidente + severidade + notificação
```

## Uso rápido

```python
from security.middleware import sanitize_sql, escape_html, csrf_token, verify_csrf, security_headers
from security.crypto import encrypt_at_rest, decrypt_at_rest, hash_password, verify_password
from security.audit import AuditLogger
from security.anomaly import AnomalyDetector
from security.incident_response import create_incident

# sanitização
safe = sanitize_sql("admin' OR 1=1 --")  # neutraliza injeção
html = escape_html("<script>alert(1)</script>")

# CSRF
token = csrf_token()
assert verify_csrf(token, token)

# headers
headers = security_headers()  # dict pronto para resposta HTTP

# criptografia
ct = encrypt_at_rest("dado sensível", key=os.getenv("APP_ENCRYPTION_KEY"))
pt = decrypt_at_rest(ct, key=os.getenv("APP_ENCRYPTION_KEY"))

# auditoria
logger = AuditLogger("audit.log")
logger.log(actor="alice", action="create_sim", resource="sim:42")

# anomalia
det = AnomalyDetector(window=100, z_threshold=3.0, rate_threshold=60)
det.observe("login", value=1.2)
if det.is_anomaly("login", 99): ...

# incidente
inc = create_incident("Brute force detectado", severity="high", indicators=["ip:1.2.3.4"])
```

## Variáveis de ambiente

```env
APP_ENCRYPTION_KEY=<32 bytes base64 ou passphrase>  # nunca hardcodar
AUDIT_LOG_PATH=./logs/audit.log
HMAC_SECRET=<secret para CSRF>
```

## Princípios

- **Sem segredos hardcoded**: chaves lidas de env; fallback gera aviso.
- **Defesa em profundidade**: sanitização + prepared statements + CSP headers.
- **Fail-closed**: CSRF inválido → rejeita; descriptografia falha → erro, não dado parcial.
- **Observabilidade**: tudo auditado em JSON lines (actor/action/resource/timestamp).

## TLS Checklist

Ver `crypto.TLS_CHECKLIST` e `crypto.tls_self_check()` — valida cert, HSTS, cipher suites.

## Playbook

Ver `incident_response.md` — 6 fases (Preparação → Identificação → Contenção → Erradicação → Recuperação → Lições).
