# LocalMart Web (React frontend)

The web app for Vyapaar-Mitra / LocalMart. It is a pure frontend — **all data
comes from the FastAPI backend in the repo root** (`app/api/web.py`, prefix
`/api/v1`), which is the same backend that runs the Telegram bot.

## Dev

```bash
# 1. Start the backend (repo root) — MongoDB must be running
cd ..
cp .env.example .env
python -m app.main          # http://localhost:8000

# 2. Start the web app
cd web
npm install
npm run dev                 # http://localhost:3000 (proxies /api -> :8000)
```

## Build (served by FastAPI)

```bash
npm run build   # outputs web/dist
```

When `web/dist` exists, the backend serves the app at `/` with SPA fallback —
one process serves frontend, REST API and Telegram bot together.
