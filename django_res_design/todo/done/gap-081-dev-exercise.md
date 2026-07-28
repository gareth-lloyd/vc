# GAP-081 — dev exercise runbook (Zoho Flow outbound push)

How to exercise everything GAP-081 shipped (contact/enquiry/quote push +
amendment 2: relationships, org/enquiry notes, agency keys, dispatch dedupe)
on a local dev environment, without touching real Zoho.

## 1. One-time setup

**Capture endpoint.** The webhook URLs are the credential (zapikey-in-URL), so
never put the real Limitless URLs in local `.env`. Use per-kind
[webhook.site](https://webhook.site) URLs, or run a local capture server:

```bash
python3 - <<'EOF'
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        print(f"\n=== POST {self.path} ===")
        print(json.dumps(json.loads(body), indent=2))
        self.send_response(200); self.end_headers()
HTTPServer(("127.0.0.1", 9999), H).serve_forever()
EOF
```

**Env vars** — in the repo-root `.env` (read by `settings/base.py` via
`environ.Env.read_env`; real env vars take precedence). Unset kind = that
push is silently disabled, so a partial set is fine:

```
ZOHO_FLOW_WEBHOOK_CONTACT=http://127.0.0.1:9999/contact
ZOHO_FLOW_WEBHOOK_ENQUIRY=http://127.0.0.1:9999/enquiry
ZOHO_FLOW_WEBHOOK_QUOTE=http://127.0.0.1:9999/quote
# ZOHO_FLOW_WEBHOOK_BOOKING — dormant until the booking build (~Sept)
```

**Stack.** `/demo-worktree` (Django + Vite + DB), plus — required for
auto-pushes, which dispatch `push_sync_record.delay` on commit:

```bash
docker compose up -d redis
cd django_res && uv run celery -A villacollective worker -l info
```

(Backfill, §2K, pushes synchronously and needs no worker.) Seed data if
needed: `uv run python manage.py seed_dev`.

**Observe** in three places: the capture server output, Django admin →
Integrations → *Sync records* / *Sync runs* (provider ZOHO_CRM; PENDING →
OK/ERROR), and the celery worker log.

## 2. Exercises

**A. Contact auto-push.** Edit any Person (Customer 360 / Clients). Expect one
POST to `/contact`. Verify the payload: `RES_ID` = res PK, `notes` INCLUDED,
**all** tags present (SENSITIVE_TAGS denylist ships empty), and (amendment 2)
`relationships` and agency `notes`.

**B. Child bumps.** Add/edit/delete a PersonEmail or PersonPhone → parent
contact re-pushes with the updated lists.

**C. Relationships.** Link two persons (GAP-041 linked contacts). Expect
**both** parties re-pushed; each payload's `relationships` carries raw kind +
direction + display-label `relation` (in-leg via RELATIONSHIP_INVERSE_LABEL).
Rows whose other party is anonymized are skipped.

**D. Organisation.** Rename an Organisation → every member agent re-pushes;
person/agent summaries in enquiry & quote payloads carry keyed
`agency` `{RES_ID, id, name}`.

**E. Merge + dedupe.** Merge two persons (one with several relationships).
Survivor is pushed via the `person_merged` signal — expect a **single**
contact POST, not one per relationship (`enqueue_zoho_push` skips dispatch
when the record is already PENDING). `Organisation.merge()` bulk-update
staleness is an accepted residual.

**F. Anonymization.** Anonymize a person → **no** contact push, ever. An
enquiry linked to them pushes with its denormalised capture columns blanked
and its notes blanked. An anonymized AGENT does *not* blank enquiry notes
(accepted residual).

**G. Enquiry auto-push.** Create an enquiry, then change stage / assignee /
anything — every save pushes (all transitions go through `.save()`). Payload
has the person/agent summaries with `agency` keys.

**H. Enquiry notes.** Add an EnquiryNote → enquiry re-pushes; the note appears
in the RES_ID-keyed `notes` list.

**I. Quote — explicit send only.** Editing a DRAFT quote pushes **nothing**
(`auto_push=False`). Send it by email, or POST `:mark-manually-sent` → one
quote push via `record_quote_sent`. Re-sending an already-SENT quote
re-enqueues (renegotiation).

**J. Failure handling.** Point one kind's URL at a 500-returning endpoint
(e.g. `https://httpstat.us/500`): record goes ERROR with retries; the beat
`push_pending` sweep repairs stranded PENDING rows (run it by hand:
`push_pending()` from `integrations.tasks` in `manage.py shell`). A 4xx parks
the record ERROR without retry.

**K. Backfill.** `uv run python manage.py zoho_backfill --kinds contact --per-minute 30`
(default: all of contact → enquiry → quote, 60/min). Creates a MANUAL
SyncRun with counters; pushes synchronously through the production task
body. Quote eligibility = actually sent (SENT/ACCEPTED, or EXPIRED/CANCELLED
with a QUOTE_SENT event) — legacy DRAFT quotes never backfill (by design;
historic quotes reach Zoho via Nick's spreadsheets). Kinds with unset URLs
are skipped with a notice.

**L. Loader suppression.** Run `loadlegacy` — zero pushes, zero new
ZOHO_CRM SyncRecords (`BaseLoader` wraps rows in `suppress_zoho_push()`).

**M. Log hygiene.** Watch the worker console during any push at default log
level: no webhook URL (i.e. no zapikey) appears — the `httpx` logger is
pinned to WARNING in LOGGING.

## 3. Shell inspection

```python
from integrations.models import SyncRecord, SyncRun
SyncRecord.objects.filter(provider="ZOHO_CRM").order_by("-updated_at") \
    .values_list("content_type__model", "object_id", "status", "error_message")[:20]
SyncRun.objects.order_by("-started_at").values()[:3]
```
