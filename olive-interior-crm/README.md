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

## Develop
Install dependencies using the Sites helper, then `npm run dev`. Authentication is provided by the Sites platform; local testing requires an isolated mock identity or trusted request headers. Never deploy a development authentication bypass.

## Deploy
`.openai/hosting.json` declares the Sites project and D1 binding. Publish using the Sites source workflow and build helper. Database schema is in `db/schema.ts`; tracked Drizzle migrations are applied by Sites during deployment.

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
