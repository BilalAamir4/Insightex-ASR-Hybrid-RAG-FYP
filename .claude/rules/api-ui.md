---
paths:
  - "backend/src/insightex/api/**"
  - "backend/src/insightex/jobs/**"
  - "frontend/**"
  - "backend/tests/api/**"
---
# API + UI (M6) — loaded only when touching API or frontend code

- FastAPI serves on `127.0.0.1:8000` (loopback only). The frontend is static HTML/JS; there is no build step.
- Background work goes through the single worker. Never run GPU work inside a request handler.
- `seekTo(seconds)` is the single player integration point. Citations (M11), graph navigation (F5) and the highlight reel (F15) must all call it rather than adding new seek logic.
- Product rule: one video per session. Keep no cross-session or cross-student data and no user history.
- Still to build: ask box, top-3 citations that seek the video, and progress via SSE (M1).
