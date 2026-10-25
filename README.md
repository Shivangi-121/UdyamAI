# UdyamAI

UdyamAI is a merchant-first business assistant. The existing lightweight frontend is preserved, with an optional FastAPI backend for persistent records, transparent calculations, assistant recommendations, campaign drafts, and controlled task checklists.

## Run locally

### Backend

PowerShell:

```powershell
cd C:\Users\shiva\UdyamAI\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

The copied `.env.example` is configured for the local SQLite development database and demo-only merchant tokens. For a PostgreSQL database, change `DATABASE_URL` in `.env` to a PostgreSQL SQLAlchemy URL and make sure that server/database is available.

Run migrations, seed the two illustrative merchants, and start the API:

```powershell
python -m alembic upgrade head
python -m app.seed
python -m uvicorn app.main:app --reload
```

The API is at `http://127.0.0.1:8000`. OpenAPI docs are at `http://127.0.0.1:8000/docs`; health is at `http://127.0.0.1:8000/api/health`.

### Frontend

In a second PowerShell window:

```powershell
cd C:\Users\shiva\UdyamAI\frontend
py -3.12 -m http.server 5173 --bind 127.0.0.1
```

Open `http://127.0.0.1:5173`. The frontend can still be opened directly as `frontend\index.html` and used offline with browser-local storage. For backend use, serve it over HTTP as above (the restricted CORS policy does not allow the `file://` origin), then open **Settings → Connect to the backend**, keep the URL at `http://127.0.0.1:8000`, and enter the token for the selected merchant from your local `.env`. The development examples are `dev-personal-token`, `dev-coconut-token`, and `dev-kirana-token`. Tokens are held in memory only and cleared on refresh. Demo merchants are read-only.

## Configuration and AI behavior

Backend configuration is loaded from environment variables or `backend\.env`. See [backend/.env.example](./backend/.env.example) for the available settings. API credentials for an OpenAI-compatible chat-completions endpoint are backend-only:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `AI_TIMEOUT_SECONDS`
- `AI_REQUESTS_PER_MINUTE`

Without both `LLM_API_KEY` and `LLM_MODEL`, the assistant and campaign generator explicitly report demo mode and use deterministic local responses. With configuration, the backend makes one bounded LLM call per assistant or campaign-generation request. Calculation results are produced by deterministic Python code, not the model.

## Backend layout

- `backend/app/api/` — authenticated REST endpoints and request limits.
- `backend/app/schemas/` — Pydantic input/output validation.
- `backend/app/models/` — SQLAlchemy merchant and business entities.
- `backend/app/db/` — database engine and session lifecycle.
- `backend/app/services/` — deterministic financial calculations and replaceable LLM integration.
- `backend/app/agents/` — modular Growth, Inventory, Profit, Marketing, and Coordinator evidence workflow.
- `backend/migrations/` — Alembic migrations.
- `backend/app/seed.py` — separate coconut-vendor and kirana demo records plus an empty personal merchant.
- `backend/tests/` — calculation and API tests.

The existing vanilla HTML/CSS/JavaScript UI remains in [frontend/](./frontend/). It has not been rebuilt as React: preserving its working merchant-oriented screens and standalone use avoids an unrelated frontend rewrite. [frontend/api.js](./frontend/api.js) centralizes optional API calls.

## API overview

Business endpoints are scoped to `/api/merchants/{merchant_id}` and require that merchant's configured `Authorization: Bearer …` token:

- `GET/PATCH /merchants/{id}` — read or update an authorized merchant.
- `GET/POST/PATCH/DELETE /merchants/{id}/products` — product list and product management (item routes take `/{product_id}`).
- `GET/POST/DELETE /merchants/{id}/sales` and `/expenses` — append/list records and delete by ID; linked sale creation checks inventory and records cost of goods when known.
- `POST /merchants/{id}/products/{product_id}/inventory`, `GET` same path — record and list inventory counts.
- `GET /merchants/{id}/summary?on=YYYY-MM-DD` — recorded daily totals; gross profit is omitted when sale costs are incomplete, and recorded expenses are not treated as net profit.
- `POST /merchants/{id}/scenarios/calculate` — deterministic Business Twin simulation; `POST/GET/DELETE /scenarios` — save/list/delete simulations.
- `POST /merchants/{id}/assistant`, `GET /recommendations` — one structured recommendation and its history.
- `POST /merchants/{id}/campaigns/generate` — editable generated/mock copy; `GET/POST/PATCH/DELETE /campaigns` — draft lifecycle only.
- `GET/POST /merchants/{id}/tasks`, `POST /tasks/plan`, `PATCH/DELETE /tasks/{task_id}`, `GET /tasks/history` — proposal, approval/rejection, checklist status, and action history. Approval never executes an external action.

Errors use a consistent JSON envelope (`error` and `message`; validation errors also include safe field details). Swagger lists the request and response schemas.

## Data, access, and limitations

- PostgreSQL is supported via SQLAlchemy; SQLite is the zero-setup local development default. Apply schema changes through Alembic migrations.
- Demo merchants are seeded separately and are read-only. Personal records use the `personal` merchant ID.
- The current bearer-token map is a **development authorization foundation**, not a complete production identity system. Configure a unique random token per merchant. Do not use the bundled development tokens outside a local demo. Before deploying for real users, integrate a proper identity provider, secure tenant provisioning and token rotation, enforce HTTPS, and configure production CORS and rate limiting.
- LLM provider calls, if configured, send the user's question and authorized merchant context from the backend. Never place LLM credentials in the frontend.
- Demand is user-entered in Business Twin scenarios; it is not forecast from history. Gross profit excludes operating expenses and unsold stock remains inventory. No net-profit claim is made.
- The demo agent coordinator produces structured evidence from the merchant's records; its role outputs are deterministic workflow results rather than separate LLM personas/calls.
- Campaigns are saved drafts only. Tasks are checklists only. No supplier orders, messages, payments, or third-party business actions are executed.
- In offline mode the frontend continues to use localStorage and its existing deterministic mock services. Backend connection is opt-in under Settings. Backend mutations update the server first, and local UI state only after success.
- Voice recognition, payment integrations, customer records, reliable demand forecasting, merchant self-registration, and production-grade user login are not implemented.

## Verify

```powershell
cd C:\Users\shiva\UdyamAI\backend
python -m pytest -q
```

The tests cover financial edge cases, validation, merchant-scoped authorization, inventory-aware sale creation, scenario persistence, demo fallback responses, campaign persistence, and task approval history.
