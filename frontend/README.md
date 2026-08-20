# VibeGuard Frontend

Next.js (App Router) + TypeScript + Tailwind UI for VibeGuard: login/signup,
scan submission, scan status polling, and the report view (findings, scores,
score trend).

## Run

```bash
npm install
npm run dev
```

Open http://localhost:3000.

## Configuration

Needs `NEXT_PUBLIC_API_URL` pointing at the backend, e.g.:

```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

See `../backend/README.md` for running the backend it talks to.
