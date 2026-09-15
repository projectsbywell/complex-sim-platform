# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] — 2026-09-15

### Added
- ADR-006: Semi-implicit Euler accepted as particle/physics integrator (divergence from ADR-002)
- ADR-007: Jacobi iteration for pressure solve in Stable Fluids
- `modules-simcore.md` updated to match actual code structure
- `security/incident_response.py` CLI for incident creation
- `database/timescale_queries.sql` — 10 example queries

### Changed
- `fluids.py` `_advect` vectorized (12.5x speedup: 29→360 steps/s at 32²)
- `crypto.py` removed passlib dependency; bcrypt direct usage
- `backend/auth.py` updated for bcrypt>=4.1 compatibility

### Fixed
- Auth incompatibility with passlib 1.7.4 + bcrypt>=4.1
- Frontend `app.js` empty file reimplemented
- Docker-compose missing Redis (added)
- `modules-simcore.md` out-of-sync with actual module names

## [1.0.0] — 2026-09-10

### Added
- 5 simulation engines: Particles, Fluids, Physics, Neural, Bio
- FastAPI backend with REST + WebSocket
- i18n: 7 languages
- Database: PostgreSQL 16 + TimescaleDB + MongoDB 7 + MinIO
- Security: middleware, crypto (AES-GCM), audit, anomaly
- 5 tutorials, 10 examples, FAQ (20), CONTRIBUTING, SECURITY, GLOSSARY
- CI/CD, Docker Compose, K8s, Terraform, Prometheus, Grafana, Nginx

### Known Limitations
- Particle integrator is semi-implicit Euler, not Velocity Verlet (ADR-006)
- Fluid pressure solver uses Jacobi, not Gauss-Seidel
- Dependencies pandas/pyarrow/h5py/psycopg2 optional with fallbacks
- Grafana dashboard panels minimal (3 panels only)
- K8s manifests incomplete (api-only deployment)
- Terraform minimal (local docker network only)
