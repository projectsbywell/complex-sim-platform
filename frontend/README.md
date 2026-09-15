# Frontend — ComplexSim SPA

Sem build. Offline-first com fallback local.

## Rodar

```bash
python -m http.server 5173 --directory /root/scripts/complex-sim-platform/frontend
# abrir http://localhost:5173/index.html
```

Com backend:

```bash
# terminal 1
pip install -r ../backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
# terminal 2: servir frontend (acima). Faça Login (admin/admin) para ativar modo remoto (REST+WS).
```

## Recursos
- 5 kinds, canvas 60fps, parâmetros em tempo real, run/pause/step/reset
- Save (localStorage + JSON), Load (arquivo), Export CSV/JSON (+Parquet/HDF5 via backend), Report com gráfico
- i18n 7 idiomas via `../i18n/*.json`, dark/light mode, responsivo
