FROM python:3.12-slim AS api
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY simulation-core/ ./simulation-core/
ENV SIMCORE_PATH=/app/simulation-core PYTHONPATH=/app/simulation-core
EXPOSE 8000
CMD ["uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8000"]
