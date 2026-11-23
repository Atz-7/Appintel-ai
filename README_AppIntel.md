# AppIntel AI — API & MCP Integration Readiness

A research case study mapping 100 apps across 10 categories.

## Files
- `AppIntel_AI_Case_Study.html` — self-contained interactive case-study page (open in a browser).
- `appintel_master_normalized.json` / `.csv` — normalized 100-app dataset.
- `appintel_reconciliation_audit.json` — coverage, normalization and structural audit.
- `appintel_verification_audit.json` — targeted official-document audit for 8 apps.

## Open locally
Open `AppIntel_AI_Case_Study.html` in Chrome/Edge. The page reads its dataset inline, so it does not need a server or API key.

## Method and limitations
The supplied 100-app list was reconciled to 100 canonical records from 101 collected source names. One alias was applied (`QuickBooks Online` → `QuickBooks`); out-of-scope TikTok was excluded. 379 evidence URLs were collected, but not all were independently opened. The automated Tavily + Gemini run produced 8 completed reports; the remaining records were assembled in separate research batches. Eight records received targeted manual checks against official documentation. No authenticated API/MCP calls were performed. 92 records remain flagged for human review. Buildability labels are research judgments, not measured integration success rates.

Composio connectivity was tested and exposed meta-tools only; no app-specific toolkit execution is claimed. Do not publish credentials or `.env` files.

## Suggested next verification steps
1. Open every official evidence URL for the highest-impact integrations.
2. Verify auth flow and access tier in a test account.
3. Run at least one read-only authenticated API/MCP smoke test per integration.
4. Record timestamp, account tier, scopes, endpoint, result and failure mode.
5. Recalculate buildability only after those checks.
