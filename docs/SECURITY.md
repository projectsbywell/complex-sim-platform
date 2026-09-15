# Security — complex-sim-platform

## Security Architecture Summary

### Overview

complex-sim-platform implements a defense-in-depth security model
with multiple layers of protection across the entire stack.

---

## Layer 1: Network Security

### TLS/SSL Encryption

All external communications are encrypted with TLS 1.3:
- REST API endpoints served over HTTPS
- WebSocket connections over WSS
- Database connections with TLS
- Inter-service communication mTLS

**Configuration:**
```python
# TLS configuration in backend/main.py
ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ssl_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
```

### Firewall Rules

- Only ports 443 (HTTPS) and 80 (redirect) exposed externally
- Internal services communicate on private network only
- Database port 5432 accessible only from backend
- Redis port 6379 accessible only from backend and cache

---

## Layer 2: Application Security

### Authentication

JWT-based authentication with refresh tokens:

```python
# Token generation
token = create_access_token(
    data={"sub": user_id, "role": "researcher"},
    expires_delta=timedelta(hours=1),
)

# Token verification
payload = verify_token(token, secret=JWT_SECRET)
```

### Authorization

Role-based access control (RBAC):
- **admin**: Full system access
- **researcher**: Create/run simulations, access own data
- **viewer**: Read-only access
- **pipeline**: Service account for automated pipeline execution

```python
from backend.middleware.auth import require_role

@app.get("/api/v1/simulations")
@require_role("researcher")
async def list_simulations():
    ...
```

### Input Sanitization

All user inputs are validated and sanitized:
- Pydantic models validate all request bodies
- String inputs are checked for injection patterns
- File uploads are type-checked and size-limited
- Numeric inputs are range-checked

### CSRF Protection

- Anti-CSRF tokens for state-changing requests
- SameSite cookies for session management
- Origin header validation

### CORS Configuration

Strict CORS policy limiting origins:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://platform.example.com"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## Layer 3: Data Security

### Encryption at Rest

- Database encryption using AES-256
- Checkpoint files encrypted with per-user keys
- Object storage with server-side encryption

### Encryption in Transit

- All internal service communication encrypted
- PostgreSQL connections with SSL
- Redis connections with TLS

### Data Retention

- Simulation data automatically purged after retention period
- Audit logs retained for compliance
- User data subject to GDPR-style deletion rights

### SQL Injection Prevention

- All database queries use parameterized queries
- ORM prevents raw SQL injection
- Input validation rejects SQL keywords in text fields

### Dependency Security

- Regular `pip audit` runs
- GitHub Dependabot for automated dependency updates
- `safety check` in CI pipeline

---

## Layer 4: Infrastructure Security

### Container Security

- Docker containers run as non-root user
- Read-only root filesystem
- Minimal base images (python:3.11-slim)
- No unnecessary packages installed

```dockerfile
RUN useradd -m simuser && \
    chown -R simuser:simuser /app
USER simuser
```

### Secrets Management

- Secrets stored in environment variables (12-factor)
- Never committed to version control
- `.env` files in `.gitignore`
- Secret rotation policies

### Rate Limiting

Token-bucket algorithm protecting endpoints:

```python
from backend.middleware.rate_limit import RateLimitMiddleware

app.add_middleware(
    RateLimitMiddleware,
    limits={
        "default": "100/minute",
        "/api/v1/simulations": "10/minute",
        "/api/v1/models/train": "5/hour",
    }
)
```

---

## Layer 5: Audit and Monitoring

### Audit Logging

All security-relevant events are logged:
- Authentication attempts (success/failure)
- Authorization decisions
- Data access and modifications
- Configuration changes

```json
{"timestamp": "...", "event": "auth_failure", "user": "...",
 "ip": "...", "reason": "invalid_token"}
```

### Intrusion Detection

- Failed login attempts tracked and alerted
- Rate limit violations trigger alerts
- Unusual data access patterns flagged

### Vulnerability Scanning

- Regular dependency vulnerability scanning
- Container image scanning
- Periodic penetration testing

---

## Security Checklist

Before deployment, verify:

- [ ] TLS 1.3 enabled on all endpoints
- [ ] JWT secret is 256-bit random value
- [ ] Database credentials in environment variables
- [ ] CORS restricted to known origins
- [ ] Rate limiting configured on all endpoints
- [ ] Input validation on all request bodies
- [ ] Container runs as non-root
- [ ] Secrets not in version control
- [ ] Audit logging enabled
- [ ] Dependency vulnerabilities addressed
- [ ] Health check endpoint implemented
- [ ] Error handling does not leak stack traces

---

## Responsible Disclosure

Security issues should be reported privately:
- Email: security@complex-sim-platform.dev
- Include: vulnerability description, reproduction steps, impact
- Response time: 48 hours initial acknowledgment
- Patch timeline: 30 days for critical vulnerabilities
