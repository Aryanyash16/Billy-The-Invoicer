# Implementation status

## Included in the repository
- API, models, review endpoints, audit records, deterministic validation.
- PDF/image/email-text ingestion path, Groq extraction adapter.
- Evaluation scripts for per-field metrics and threshold analysis.
- QuickBooks sandbox-only integration adapter, environment config and sync ledger.
- Test suite and docs for public datasets, case study, demo and real-user pilot.

## Not yet verified / requires setup
- `uv sync` and test execution in your local environment.
- OCR depends on OS Tesseract installation.
- Groq extraction needs a valid API key and current model access.
- SROIE/CORD data download, schema mapping, annotation quality review and actual scoring.
- QuickBooks OAuth app, vendor ID, expense account ID, token refresh persistence, and a successful sandbox round-trip.
- Next.js review UI starter is included; it requires npm install and local API configuration.
- Real-user pilot and demo recording.

## Important implementation caveats
- Current heuristic score is field completeness, not model-calibrated confidence.
- Automatic approval is disabled by default. The score is field completeness, not calibrated confidence; do not enable auto-approval until threshold evaluation on labelled representative data establishes a safe operating point.
- The example QuickBooks Bill payload is minimal and may require adjustments for your sandbox company/account configuration.
- API reviewer identity header is development-only. Add real auth and tenant isolation before deployment.


## Phase 1 changes in this revision
- Invoice schema preserves explicit `quickbooks_vendor_id` and `quickbooks_expense_account_id` mappings.
- Added QuickBooks OAuth connect/callback routes with state validation and persisted sandbox tokens; refresh-token rotation is saved after refresh.
- QuickBooks Bill creates use a stable `requestid` query parameter (not `intuit_tid`) and retry the same logical request after transport failures.
- Correction and approval re-run duplicate checks while excluding the current invoice.
- Added `psycopg[binary]` and PostgreSQL healthcheck/readiness in Compose.
- Fixed literal `\n` configuration/documentation artifacts.
- Added regression tests for mapping preservation, stable QuickBooks request IDs, missing vendor mappings, and duplicate approval prevention.

## Phase 1 verification limitations
- Regression tests passed in the available test environment using lightweight stubs for dependencies (`tenacity` and `groq`) that were not installed in this isolated build container. Run the full suite after `uv sync` on the target machine.
- QuickBooks OAuth and Bill creation have not been tested against an actual Intuit sandbox; configure the Intuit app and verify the redirect URI, scopes, vendor/account IDs, and create/read round-trip.
- OAuth state is process-local (suitable only for the current single-worker local setup). Use a shared expiring store for multi-worker deployments.
- OAuth tokens are stored in the local database for this scaffold; encrypt them at rest and use a managed secret store before production.
- `uv.lock` could not be regenerated in the isolated environment because package registry access is unavailable. Run `uv lock` or `uv sync` on your Mac to refresh it for the added psycopg dependency.
