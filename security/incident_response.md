# Incident Response — Playbook (6 fases)

> NIST SP 800-61 adaptado para Complex Sim Platform.

## 1. Preparação

- **Time**: definir On-call, Sec Lead, Eng Lead, Comms.
- **Ferramentas**: `security/audit.py` (audit.log), `anomaly.py` alertas, `crypto.py` TLS checklist, backups (`database/backup.sh`).
- **Canais**: Slack #incidents, PagerDuty, email sec@.
- **Baseline**: inventário de assets (postgres, mongo, minio, pipeline), runbooks, contatos.
- **Treino**: tabletop trimestral; testar restore.

**Checklist preparação**
- [ ] `.env` com segredos rotacionados
- [ ] logs centralizados e imutáveis
- [ ] alertas de anomalia configurados
- [ ] backups testados

## 2. Identificação

- **Sinais**: anomalia z-score >3, rate > threshold, audit log action=failed_login repetido, WAF/IDS.
- **Triage**: confirmar verdadeiro/falso positivo via `AuditLogger.filter()` e `AnomalyDetector.check()`.
- **Classificação inicial**: severidade (ver `incident_response.py`).

```python
from security.audit import AuditLogger
lg = AuditLogger()
lg.filter(action="failed_login", limit=50)
```

- **Preservar evidência**: copiar audit.log, métricas Timescale, dumps sem alterar original.

## 3. Contenção

**Curto prazo (horas)**
- Isolar host/serviço: `docker compose -f docker-compose.db.yml stop <svc>` ou firewall.
- Revogar credenciais comprometidas; rotacionar `APP_ENCRYPTION_KEY`/`HMAC_SECRET` se vazadas.
- Bloquear IP malicioso no WAF/reverse proxy.

**Longo prazo (dias)**
- Segmentar rede (`simnet` isolada), aplicar patches, reforçar headers CSP/HSTS.

> Não erradicar antes de coletar evidência.

## 4. Erradicação

- Remover causa raiz: malware, payload, conta backdoor, dependência vulnerável (`pip audit`).
- Rebuild de imagens: `docker compose build --no-cache`.
- Resetar senhas, invalidar sessões/CSRF tokens.
- Validar com scan: `bandit`, `pip-audit`, `trivy image`.

## 5. Recuperação

- Restaurar de backup íntegro: `./database/restore.sh backups/pg_...sql.gz` (ver `replication.md`).
- Reativar serviços gradualmente; monitorar `anomaly.py` por 24-48h.
- Validar integridade: checksums, `SELECT count(*)`, testes E2E.
- Comunicar stakeholders (status page, postmortem draft).

## 6. Lições Aprendidas (Post-Incident)

- **Timeline**: quando detectado, quando contido, MTTR.
- **Root cause**: 5 whys.
- **Ações**: patch, regra de detecção nova, melhoria de log.
- **Documentar**: criar arquivo `incidents/<YYYY-MM-DD>-<slug>.md` via `incident_response.py`.

```bash
python security/incident_response.py --title "Brute force login" --severity high --actor "sec-bot"
```

- **Métricas**: MTTD, MTTR, recorrência.
- **Retro**: reunião blameless em 5 dias úteis.

---

## Severidades

| Nível | Exemplo | SLA |
|---|---|---|
| **critical** | vazamento de dados, RCE, exfiltração | 1h contenção |
| **high** | brute force bem-sucedido, privilégio elevado | 4h |
| **medium** | scan, tentativa bloqueada | 1 dia |
| **low** | falso positivo, info | backlog |

## Contatos (preencher)

- Sec Lead: ___
- On-call: ___
- Infra: ___

## Referências

- NIST 800-61 r2, SANS PICERL, OWASP Incident Response.
