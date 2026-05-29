# INV-004 — `integrations.SyncRun` / `SyncIssue` failure handling

- **Severity:** Investigation
- **Source:** `findings/2026-05-26-data-model-deep-audit.md` "What I'd
  want to investigate further" item 4

## Question

`SyncRun` / `SyncIssue` weren't audited in detail.

- How are failed sync attempts cleaned up?
- Is there a retry strategy?
- Does the Zoho integration depend on at-least-once delivery semantics
  that the current schema can't guarantee?

## Suggested probe

```
rg -n "SyncRun\|SyncIssue" django_res/integrations/
```

Read the service layer and any Celery tasks; check retry/backoff policy.

## Outcome

Open per-finding tickets if there are real holes. Mostly relevant once
Zoho integration is actually exercised (see
[Q-003](q-003-channel-sync-scope.md) and
[GAP-002](gap-002-integrations-empty-url-surface.md)).
