# UdyamAI

**A merchant-first business copilot for everyday decisions.**

UdyamAI helps small-business owners keep track of sales, expenses, products, and practical next steps. It combines a lightweight, bilingual web interface with an optional FastAPI service for persistent records, evidence-based business insights, scenario calculations, assistant recommendations, campaign drafts, and task checklists.

The project is designed to be transparent: calculations use recorded data and deterministic business rules; demo data is labeled; and suggested campaigns or tasks never send messages, place orders, or spend money.

## Highlights

- **Simple business records:** Track sales, expenses, products, and stock counts.
- **Business overview:** Review daily totals, recent transactions, and supported business insights.
- **Business Twin:** Compare user-entered business scenarios with deterministic calculations.
- **Assistant:** Ask business questions in English or Hindi using local demo responses or the optional backend AI integration.
- **Voice assistant:** Open the persistent microphone control from any page. Where the browser supports the Web Speech API, speak a request, review or edit its transcript, and hear the assistant response. Text input remains available when speech recognition is unsupported or unavailable.
- **Campaign Studio:** Create, edit, and save promotional drafts. Drafts are never sent.
- **Action plan:** Turn a goal into a checklist that the merchant can review and manage.
- **Flexible storage:** Run entirely in the browser with local storage, or connect to the optional API and database.
- **Demo merchants:** Explore separate sample businesses without mixing their records with personal data.

## Architecture

```text
frontend/                 Static HTML, CSS, and JavaScript application
  index.html              Accessible application shell and screens
  app.js                  UI rendering, navigation, and interactions
  api.js                  Optional backend API client
  data.js, store.js        Demo data and browser-local storage
  services.js              Local deterministic assistant and business logic
  styles.css              Application styling

backend/
  app/api/                 FastAPI routes and authorization
  app/agents/              Evidence-based recommendation workflow
  app/core/                Application configuration
  app/db/                  SQLAlchemy database setup
  app/models/              Database entities
  app/schemas/             Request and response validation
  app/services/            Calculations, intelligence, and assistant services
  migrations/              Alembic database migrations
  tests/                   API and calculation tests
```

The frontend has no JavaScript package installation step. The backend uses SQLAlchemy and supports SQLite for local development and PostgreSQL for deployment.

## Requirements

- Python 3.12 (the commands below use the Python launcher on Windows)
- A modern browser
- Optional: an OpenAI-compatible chat-completions API key and model for live AI-generated responses

## Run locally

### 1. Set up the backend

From PowerShell:

```powershell
cd C:\Users\shiva\UdyamAI\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

The example configuration uses a local SQLite database and development-only merchant tokens. Apply migrations, load illustrative demo merchants, and start the API:

```powershell
python -m alembic upgrade head
python -m app.seed
python -m uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. Visit `http://127.0.0.1:8000/docs` for the interactive API reference or `http://127.0.0.1:8000/api/health` for the health check.

### 2. Serve the frontend

In a second PowerShell window:

```powershell
cd C:\Users\shiva\UdyamAI\frontend
py -3.12 -m http.server 5173 --bind 127.0.0.1
```

Open `http://127.0.0.1:5173`. The app can also be opened directly from `frontend\index.html` for browser-local use. A `file://` page cannot connect to the configured backend because of browser origin restrictions; use the local HTTP server when you want backend features.

### 3. Connect the app to the backend (optional)

In UdyamAI, open **Settings → Connect to the backend**:

1. Keep the backend address as `http://127.0.0.1:8000`.
2. Select the merchant you intend to use.
3. Enter that merchant's token from `backend\.env`.
4. Select **Connect and load records**.

The bundled `dev-personal-token`, `dev-coconut-token`, and `dev-kirana-token` values are for local development only. The frontend keeps the token in memory and clears it when the page is refreshed. Seeded demo merchants are read-only.

## Configuration

Backend settings are read from environment variables and `backend\.env`. See [`backend/.env.example`](./backend/.env.example).

| Setting | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL; defaults to local SQLite. |
| `CORS_ORIGINS` | Comma-separated frontend origins allowed to call the API. |
| `MERCHANT_TOKENS` | JSON map of merchant IDs to distinct bearer tokens. |
| `LLM_BASE_URL` | Base URL for an OpenAI-compatible chat-completions API. |
| `LLM_API_KEY` | Backend-only provider credential. |
| `LLM_MODEL` | Model name used for assistant and campaign generation. |
| `AI_TIMEOUT_SECONDS` | Maximum duration for a provider request. |
| `AI_REQUESTS_PER_MINUTE` | Per-merchant limit for assistant and campaign requests. |
| `INTELLIGENCE_CHANGE_THRESHOLD` | Relative change threshold for supported sales/expense insights. |

When both `LLM_API_KEY` and `LLM_MODEL` are set, the backend can use the configured provider for assistant recommendations and campaign copy. Without them, it returns clearly labeled deterministic demo responses. Financial metrics and scenario results are computed by application code, not invented by the language model. Never put provider credentials in frontend code.

## Voice assistant

The persistent microphone button is available on every application page. Select it to open the assistant, then start listening from the microphone control. The transcript can be reviewed or corrected before sending. The response is displayed in the panel and can be read aloud using browser speech synthesis; speech can be muted.

Speech recognition and speech synthesis depend on browser and device support. Microphone access is requested only after the user activates listening, and may require permission and a secure browser context. If recognition is unsupported or permission is denied, use the text-input fallback. Hindi recognition uses the browser's `hi-IN` locale when selected; English uses `en-US`. Mixed Hindi-English recognition quality and voice availability vary by browser and installed language packs.

Voice and typed questions share the existing assistant path. Connecting to the backend enables merchant-scoped server recommendations; without a backend, the interface uses local demo behavior. The assistant does not execute business actions through voice.

## Data and business logic

- Personal records can be stored in browser local storage or in the backend, depending on the selected mode.
- SQLite is the default local database. PostgreSQL is supported through SQLAlchemy; configure `DATABASE_URL` and ensure the database is available before running migrations.
- A recorded sales total is not the same as profit. Gross profit is reported only when sale-cost information is available and does not subtract operating expenses.
- Business Twin results use the assumptions entered by the user; they are scenarios, not forecasts.
- Business insights are generated from available recorded data and deterministic thresholds. Incomplete records can produce incomplete or unavailable findings.
- Inventory replenishment estimates require the necessary sales history, a stock count, and supplier lead-time information.
- Campaigns are editable drafts. Action plans are checklists. UdyamAI does not send promotions, place supplier orders, process payments, or contact customers.

## API overview

Business routes are scoped to `/api/merchants/{merchant_id}` and require the merchant's bearer token. The API validates request and response schemas and returns structured errors.

| Capability | Routes |
| --- | --- |
| Merchant, products, sales, expenses | `/merchants/{id}`, `/products`, `/sales`, `/expenses` |
| Summary and inventory | `/summary`, `/products/{product_id}/inventory`, `/inventory-risks` |
| Business intelligence | `/intelligence/analyze`, `/insights`, `/outcomes` |
| Business Twin | `/scenarios/calculate`, `/scenarios` |
| Assistant | `/assistant`, `/assistant/team`, `/recommendations` |
| Campaign drafts | `/campaigns/generate`, `/campaigns` |
| Tasks and checklists | `/tasks/plan`, `/tasks`, `/tasks/history` |

All routes are prefixed by `/api/merchants/{merchant_id}` unless otherwise noted in the interactive API documentation.

## Tests

Run the backend tests from the `backend` directory:

```powershell
cd C:\Users\shiva\UdyamAI\backend
python -m pytest -q
```

The test suite covers calculations, API validation, merchant scoping, record persistence, scenario handling, assistant fallback behavior, campaign drafts, task workflows, intelligence evidence, and outcomes.

## Security and deployment notes

The included token map is a local development foundation, not a production identity system. Before deploying for real merchants:

- Replace all development tokens with strong, unique credentials and establish secure provisioning and rotation.
- Integrate a production-grade identity provider and enforce tenant isolation.
- Serve the application over HTTPS and configure CORS to allow only trusted origins.
- Store provider credentials and database secrets in a managed secret store or protected environment configuration.
- Add production-appropriate rate limiting, monitoring, backups, and operational controls.

UdyamAI is a development project and does not provide accounting, tax, financial, or demand-forecasting guarantees.
