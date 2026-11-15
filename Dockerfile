FROM node:24-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY scripts/init_demo.py ./scripts/init_demo.py
COPY demo_data/ ./demo_data/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 learnpilot
USER learnpilot
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
