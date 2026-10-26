# UdyamAI Feature Matrix

This matrix describes the checked-in implementation, not a deployment guarantee.
Capabilities vary depending on whether the app is used locally or connected to
the optional backend.

| Area | Status | What works | Boundaries |
| --- | --- | --- | --- |
| Merchant workspace | Implemented | Browser-local workspace and optional merchant-scoped backend records | Local browser data and backend records are separate stores; there is no automatic sync between them. |
| Sales and expenses | Implemented | Record and review transactions; backend APIs validate and persist merchant records | Demo merchants are read-only. Values depend on what the merchant records. |
| Product and inventory | Implemented | Product records, stock updates, inventory risk estimates when sufficient history is available | Risk estimates require stock counts and enough recent sales history; they are not purchase orders. |
| Analytics | Implemented for connected backend records | Inclusive date-filtered revenue, recorded expenses, gross/net profit where costs are complete, average sale value, daily trend, expense categories, product revenue, comparison coverage, and transparent data coverage | Date ranges are limited to 366 days. Comparisons require the prior period to fall within stored history but cannot verify bookkeeping completeness. Browser-local records remain separate and do not use the backend analytics endpoint. Refunds and cancelled transactions are not modeled. |
| CSV import and export | Implemented for connected backend records | Preview, column mapping, row validation, confirmation, row-level results, exact-repeat detection, downloadable templates, and merchant-scoped sales/expense/product exports | UTF-8 CSV, 2 MB, and 5,000-row import limits. Sales require date and amount; historical costs are not inferred from current product costs; imported sales do not change stock. Products with existing names are skipped, not updated. Exports are limited to 10,000 rows. Demo merchants are read-only. |
| Dashboard and insights | Implemented | Recorded totals and deterministic, evidence-based insights; connected merchants can review date-filtered backend analytics and coverage | Incomplete records can result in unavailable or incomplete metrics. Revenue is not profit. |
| Business Twin | Implemented | Compare a deterministic scenario; selecting a product shows its recorded 30-day revenue, units, and gross profit only when historical costs are complete, and fills an editable demand assumption from the rounded recorded daily average | Historical records are a reference, not a forecast. Scenario outputs remain hypothetical and exclude other expenses; records may be incomplete. |
| Assistant | Implemented with limits | English/Hindi questions; local rules-based answers or optional backend LLM; bounded conversational follow-ups | Conversation context is temporary and limited to the current browser session. Recognized recorded-data questions use deterministic evidence; open-ended LLM advice can still be imperfect. |
| Voice assistant | Browser-dependent | Speech-to-text and spoken replies where Web Speech APIs and language packs are available; typed input remains available | Requires user microphone permission and suitable browser support. Voice can answer questions but does not perform business actions. |
| Campaign Studio | Draft workflow | Generate or edit campaign copy and save drafts | Drafts are not delivered; no messaging or social-platform integration is included. |
| Action plan / Autopilot | Checklist workflow | Create and manage suggested tasks and review action history | Tasks are suggestions/checklists; no orders, payments, or external actions are executed. |
| Demo data | Implemented | Seeded coconut-cart and kirana examples; deterministic reset of seeded demo records | Seed reset only targets merchants explicitly marked as demos and preserves the personal merchant. |
| Backend protection | Development baseline | Merchant bearer-token checks and merchant-scoped API queries; demo accounts are read-only | Development tokens are not production identity. Rate limiting is process-local. Use production identity, secrets management, monitoring, and deployment controls before serving real businesses. |
| Frontend validation | Manual | Browser-based workflows and JavaScript syntax checks | No frontend build, lint, or automated browser-test suite is configured. |

## Calculation and date conventions

- Backend scenario and recorded-metric calculations use application code; language
  models do not calculate financial results.
- Gross profit is only available when sales have cost-of-goods data and excludes
  operating expenses.
- Analytics use recorded sale amounts and expenses. Net profit is gross profit
  less recorded expenses and is unavailable if costs are incomplete. Average
  recorded sale is not an order-level average.
- CSV imports accept ISO dates (`YYYY-MM-DD`) and decimal amounts with at most
  two decimal places. Exact repeated imported transactions are skipped; identical
  legitimate rows may be treated as duplicates.
- Business-day boundaries use `Asia/Kolkata`. Browser-local demo dates follow the
  same timezone to keep demo charts and backend reports aligned.
- The application is a prototype and does not provide accounting, tax, lending,
  or demand-forecasting guarantees.
