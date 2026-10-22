# Olive Tree Conversion CRM

A responsive solo interior business CRM built with React, Vinext and Cloudflare D1.

## Features
- Today dashboard for due follow-ups and site visits
- Enquiries with stages, source, budget, notes, call and WhatsApp links
- Customer quotations with quantity/rate items and print-to-PDF
- Interior project checklist and task progress
- Payment receipts, quoted totals and outstanding balances
- Archive and restore records using the Archived stage filter
- JSON backup export; sample data mode that never writes to the database

Records are stored server-side and scoped to the signed-in user. The deployment is owner-private. No customer records or credentials are stored in this source repository.

## Live standalone CRM
https://olive-interior-crm.britsingh20.workers.dev

Hosted directly on Cloudflare Workers with a dedicated D1 database. A server-checked password unlocks the CRM. Sessions use secure HttpOnly cookies and expire after 90 days. Password hashes stay in the Worker secret CRM_PASSWORD_HASH; passwords are never included in source. Failed login attempts are limited per IP address. Customer records and secrets are never committed to GitHub.

## Develop and deploy
Install dependencies with `npm install`. Run `npm run build:standalone`, then `npm run deploy:standalone` after authenticating Wrangler with the Cloudflare account. The standalone frontend and API are in `standalone/`; `standalone/wrangler.jsonc` declares the existing Worker and database. The standalone Worker implements its own password login; no email-code Access application is required. Apply standalone/migrations/0001_auth.sql to the existing D1 database before deploying this version. Configure CRM_PASSWORD_HASH as a secret using a random salt and PBKDF2-SHA256 with 100,000 iterations, encoded as salt:hexhash. Never commit its value. The build embeds static frontend assets in the Worker module. `npm run dev` remains the original Sites development workflow.

The original Sites deployment remains available as a backup. Its `.openai/hosting.json` and trusted Sites authentication apply only to that deployment. The standalone database contains the migrated customer records; later changes are independent between the two deployments.

Automatic GitHub deployments require connecting this repository through Cloudflare's GitHub integration. The integration currently needs reconnection in the Cloudflare dashboard; source commits alone do not deploy this Worker.

## Limits
WhatsApp opens a prepared message for manual sending. Follow-ups are shown inside the CRM, with no background push notifications. Quotes have no automatic GST calculation. File uploads, automatic Meta lead ingestion, accounting integrations, and multiple employee roles are not included in this initial release. JSON export is a backup download; restore import is not yet implemented.

## Research basis
Houzz Pro sales CRM connects leads, estimates, schedules, invoicing and project work: https://pro.houzz.com/for-pros/feature-sales-crm
Mydoma Studio covers project management, client communication, approvals and design boards: https://mydomastudio.com/features/
This release prioritizes daily actions for one operator over team and design collaboration features.

## Conversion workflow
Stages: Site visit → Quotation → 3D drawing → Follow-up → Converted (or Not proceeding).
New customers receive a site-visit call today. Completing a site visit schedules a quotation in 2 days. Marking a quotation sent schedules 3D work in 3 days. Marking a drawing shared schedules the decision conversation in 2 days. The first recorded interest/price response schedules 3 days, then weekly; no answer retries tomorrow. Call later requires the customer's chosen date. Design changes return to drawing in 3 days. Dates are editable per customer.

Schedules persist in each customer record. The daily queue updates by India date and includes overdue work; it does not send messages or push notifications in the background. Only explicit user actions advance stages or mark conversion.

Existing records and quotations are retained. Legacy confirmed/in-progress/completed customers appear as Converted; old enquiry/contacted stages appear as Site visit. Archived records are accessible through the Customers filter.

## Contacts and voice intake
Phone-only contacts are supported with blank names. `/api/import` normalizes Indian mobile numbers and skips duplicates. Signed-in imports use the current user. Service imports require `CRM_IMPORT_KEY` and use `CRM_OWNER_EMAIL`; imported email-scoped records become owned by that signed-in email on their next load. Contact data is uploaded at runtime and is not embedded in source.

Voice notes use the browser SpeechRecognition/webkitSpeechRecognition service with English India and Tamil language choices. Recognition depends on browser support, microphone permission and the browser speech service. Text entry and operating-system keyboard dictation are supported fallbacks. Microphone audio is not stored in the CRM.

Voice inbox splits updates at “next client” or blank lines, matches an explicit phone number or a unique exact saved name, and requires a selected customer before saving. Simple labeled fields produce editable suggestions. Full transcripts are retained as customer notes. Potential is a user-provided Hot/Warm/Cold assessment, with Hot setting high follow-up priority. This is rule-based extraction, not a general AI semantic parser. Ambiguous matches require manual selection. The operator reviews suggestions before they are saved; stages and dates remain unchanged.

Clicking a customer name or number opens that customer's voice entry directly. Start speaking, stop, review the transcript and use Save note to persist it immediately to that customer's requirements notes. Optional field suggestions are separate from saving a raw note. Existing notes are appended to, and the customer remains open after saving. Update & schedule opens the conversion action screen directly.

### iPhone speech recovery
Embedded iPhone browsers default to keyboard dictation guidance, because exposing the browser speech API does not guarantee that its speech service can capture audio. Speech failures now show specific guidance and expose keyboard dictation. The keyboard control focuses the selected customer's text box; the user must tap the iPhone keyboard microphone. No code can launch that operating-system dictation action on the user's behalf. Browser speech remains available as an explicit retry. Voice-note screens no longer reserve the unrelated bottom scheduling footer; Save note remains accessible in the scrolling form.
