# UdyamAI

**A merchant-first business copilot for everyday decisions.**

UdyamAI helps small-business owners keep track of sales, expenses, products, and practical next steps. It combines a lightweight, bilingual web interface with an optional FastAPI service for persistent records, evidence-based business insights, scenario calculations, assistant recommendations, campaign drafts, and task checklists.

The project is designed to be transparent: calculations use recorded data and deterministic business rules; demo data is labeled; and suggested campaigns or tasks never send messages, place orders, or spend money.

See the [feature matrix](./docs/FEATURE_MATRIX.md) for implementation status and
known boundaries, and the [demo guide](./docs/DEMO_GUIDE.md) for a repeatable
judge-ready walkthrough.

## Highlights

- **Simple business records:** Track sales, expenses, products, and stock counts.
- **Business overview:** Review daily totals, recent transactions, and supported business insights.
- **Business Twin:** Compare user-entered business scenarios with deterministic calculations.
- **Assistant:** Ask business questions in English or Hindi using local demo responses or the optional backend AI integration.
- **Bilingual voice assistant:** With a backend Sarvam key configured, record Hindi, English, or code-mixed speech, send it through Saaras transcription, the shared merchant assistant, and Bulbul speech playback. Typed input remains available as a fallback.
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
- Optional: a Sarvam AI API key for backend speech recognition, chat, and speech synthesis. An OpenAI-compatible chat provider remains supported for text-only assistant and campaign generation.

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

To replace only seeded sample merchants and their demo records before a fresh
walkthrough, run `python -m app.seed --reset-demo` from `backend`. Personal
merchant records are preserved.

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

### 4. Create an account (optional)

Create an account on the entry screen before using the workspace; returning users can switch to **Sign in**. After successful registration or sign-in, UdyamAI opens the home screen. Account-owned business records are scoped to that account; account records are not copied into browser local storage. The onboarding flow can be resumed later and profile settings can be edited from Settings.

Onboarding and profile settings include business type and stage, sales channels and tracking, team size, goals, location, currency, preferred language, explanation detail, assistant interaction, notification preferences, and a Light, Dark, or System theme. The assistant receives relevant profile preferences from the server; they guide its wording and priorities but are not treated as measured business facts. Theme and language can also be changed from the existing app controls.

The account API uses a short-lived bearer access token plus a rotating, HttpOnly refresh cookie protected by a CSRF token. Password recovery sends a single-use link that expires after 30 minutes. Configure SMTP to enable recovery; without SMTP, the request returns a service error. The account routes are `/api/auth/register`, `/api/auth/login`, `/api/auth/session`, `/api/auth/profile`, `/api/auth/password-reset/request`, and `/api/auth/password-reset/complete`.

For deployment, set a unique `AUTH_SECRET_KEY` of at least 32 characters, set `APP_ENV=production`, serve the app over HTTPS, and set `CORS_ORIGINS` and `FRONTEND_URL` to the actual trusted frontend origin. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM_EMAIL` for password recovery. Run `python -m alembic upgrade head` after updating the application. Account rate limits are currently held in process memory; use a shared rate-limit store before running multiple API workers or instances.

## Configuration

Backend settings are read from environment variables and `backend\.env`. See [`backend/.env.example`](./backend/.env.example).

| Setting | Purpose |
| --- | --- |
| `APP_ENV` | Use `production` to enforce a non-development account signing secret and secure auth cookies. |
| `DATABASE_URL` | SQLAlchemy database URL; defaults to local SQLite. |
| `CORS_ORIGINS` | Comma-separated frontend origins allowed to call the API. |
| `AUTH_SECRET_KEY` | Secret used to sign account access tokens; use a unique value of at least 32 characters in production. |
| `AUTH_ACCESS_TOKEN_MINUTES` | Account access-token lifetime (1–60 minutes). |
| `AUTH_REFRESH_TOKEN_DAYS` | Refresh-session lifetime (1–90 days). |
| `FRONTEND_URL` | Trusted frontend base URL used to create password-reset links. |
| `SMTP_HOST`, `SMTP_PORT` | TLS-enabled SMTP server for password recovery. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Optional SMTP authentication credentials. |
| `SMTP_FROM_EMAIL` | Sender address for recovery messages. |
| `MERCHANT_TOKENS` | JSON map of merchant IDs to distinct bearer tokens. |
| `LLM_BASE_URL` | Base URL for an OpenAI-compatible chat-completions API. |
| `LLM_API_KEY` | Backend-only provider credential. |
| `LLM_MODEL` | Model name used for assistant and campaign generation. |
| `AI_TIMEOUT_SECONDS` | Maximum duration for a provider request. |
| `AI_REQUESTS_PER_MINUTE` | Per-merchant limit for assistant and campaign requests. |
| `SARVAM_API_KEY` | Backend-only API key; get one from the [Sarvam AI dashboard](https://dashboard.sarvam.ai/). |
| `SARVAM_CHAT_MODEL` | Sarvam chat model; defaults to `sarvam-105b`. |
| `SARVAM_STT_MODEL` | Speech transcription model; defaults to `saaras:v4`. |
| `SARVAM_TTS_MODEL` | Speech synthesis model; defaults to `bulbul:v4-flash`. |
| `SARVAM_TTS_SPEAKER` | Voice persona compatible with the selected TTS model; defaults to `shubh_enhi_ads`. |
| `SARVAM_TTS_ENABLED` | Enables spoken replies; defaults to `true`. |
| `SARVAM_MAX_AUDIO_BYTES` | Maximum uploaded recording size; defaults to 5,000,000 bytes. |
| `INTELLIGENCE_CHANGE_THRESHOLD` | Relative change threshold for supported sales/expense insights. |

When `SARVAM_API_KEY` is configured, Sarvam is used for assistant chat and campaign generation. Without it, the existing OpenAI-compatible provider can still generate text replies and campaign copy when both `LLM_API_KEY` and `LLM_MODEL` are set; otherwise the assistant uses clearly labeled deterministic demo responses. Financial metrics and scenario results are computed by application code, not invented by the language model. Keep provider credentials in the backend `.env` only; never add them to frontend files or browser settings.

## Voice assistant

The persistent microphone button is available on every application page. When connected to the authenticated backend, selecting the microphone records up to 60 seconds and uploads the audio to `/api/merchants/{merchant_id}/assistant/voice`. Saaras transcribes the recording; the transcript, response, and any playable Bulbul audio appear in the existing voice panel. The recording is held in memory for the request and is not stored by UdyamAI. The browser requests microphone permission only after activation and requires a secure context (HTTPS in deployment; localhost is suitable for local development).

Sarvam uses the documented `saaras:v4` model with language auto-detection, which preserves the spoken language and supports Hindi, English, and code-mixed speech. Saaras v4 automatically handles the available transcription formats; if configured to use Saaras v3, the integration requests its `codemix` mode. Chat uses `sarvam-105b`; speech output uses `bulbul:v4-flash` and the configured compatible persona. Response language follows the detected transcript language and the assistant's language instructions. Recognition and pronunciation quality can vary, especially for regional accents, names, and Roman-script Hinglish.

Voice and typed questions call the same merchant-scoped assistant and conversation-history path. The Sarvam model can use validated read-only tools for recorded sales, expenses, stock, saved Business Pulse insights, simulations, campaign draft generation, and existing Autopilot tasks. Simulations and campaign copy are not saved or executed; the assistant cannot create or edit financial records, change stock, publish or send campaigns, spend money, or execute tasks. Those write actions are not available through the assistant. When backend voice service is unavailable or microphone access is denied, type the request or use browser speech recognition where supported. If speech synthesis fails, the written response remains visible.

Sarvam calls are made only from the backend. Audio is sent to Sarvam for transcription and response text may be sent for speech generation; review Sarvam's current [API terms and privacy documentation](https://docs.sarvam.ai/api-reference/introduction) before using real merchant data. The configured per-merchant assistant request limit applies to voice and typed assistant requests. Normal automated tests mock provider calls and do not use paid API requests.

To verify all three live APIs with a short generated sample, set `SARVAM_API_KEY` in `backend\.env` and run this from the `backend` directory:

```powershell
python -m app.services.sarvam_smoke_test
```

This optional smoke test calls TTS, transcribes its generated MP3 with STT, and sends a short chat request. It may incur provider usage charges. No live API result is assumed unless you run it successfully with a valid key.

## Data and business logic

- Personal records can be stored in browser local storage or in the backend, depending on the selected mode.
- SQLite is the default local database. PostgreSQL is supported through SQLAlchemy; configure `DATABASE_URL` and ensure the database is available before running migrations.
- A recorded sales total is not the same as profit. Gross profit is reported only when sale-cost information is available and does not subtract operating expenses.
- Business Twin results use the assumptions entered by the user; they are scenarios, not forecasts.
- Business insights are generated from available recorded data and deterministic thresholds. Incomplete records can produce incomplete or unavailable findings.
- Inventory replenishment estimates require the necessary sales history, a stock count, and supplier lead-time information.
- Backend business-day calculations and browser demo dates use `Asia/Kolkata`.
- Campaigns are editable drafts. Action plans are checklists. UdyamAI does not send promotions, place supplier orders, process payments, or contact customers.

## API overview

Business routes are scoped to `/api/merchants/{merchant_id}` and require the merchant's bearer token. The API validates request and response schemas and returns structured errors.

| Capability | Routes |
| --- | --- |
| Merchant, products, sales, expenses | `/merchants/{id}`, `/products`, `/sales`, `/expenses` |
| Summary and inventory | `/summary`, `/products/{product_id}/inventory`, `/inventory-risks` |
| Business intelligence | `/intelligence/analyze`, `/insights`, `/outcomes` |
| Business Twin | `/scenarios/calculate`, `/scenarios` |
| Assistant | `/assistant`, `/assistant/voice`, `/assistant/team`, `/recommendations` |
| Campaign drafts | `/campaigns/generate`, `/campaigns` |
| Tasks and checklists | `/tasks/plan`, `/tasks`, `/tasks/history` |

All routes are prefixed by `/api/merchants/{merchant_id}` unless otherwise noted in the interactive API documentation.
The voice endpoint uses multipart form data and the same merchant bearer-token authorization as the typed assistant.
Account routes are under `/api/auth`; registration, login, and refresh return an access token and profile, while refresh/logout use the cookie and CSRF header. `GET` and `PATCH /api/auth/profile` read and update the authenticated account's business profile and preferences.

## Tests

Run the backend tests from the `backend` directory:

```powershell
cd C:\Users\shiva\UdyamAI\backend
python -m pytest -q
```

The test suite covers calculations, API validation, merchant scoping, record persistence, scenario handling, assistant fallback behavior, Sarvam request and response handling, voice upload validation, campaign drafts, task workflows, intelligence evidence, and outcomes. External Sarvam calls are mocked.

## Security and deployment notes

The account and merchant-token flows are a starting point, not a complete production identity and operations program. Before deploying for real merchants:

- Configure a unique production auth secret, replace development merchant tokens, and establish secure credential provisioning and rotation.
- Assess account recovery, abuse monitoring, and tenant isolation against the deployment's requirements.
- Serve the application over HTTPS and configure CORS to allow only trusted origins.
- Store provider credentials and database secrets in a managed secret store or protected environment configuration.
- Replace the process-local account rate limiter with shared storage when running multiple workers or instances; add production-appropriate monitoring, backups, and operational controls.

UdyamAI is a development project and does not provide accounting, tax, financial, or demand-forecasting guarantees.
