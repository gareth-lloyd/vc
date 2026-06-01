# INV-004 — `integrations.SyncRun` / `SyncIssue` failure handling

- **Severity:** Investigation
- **Source:** the 2026-05-26 data-model deep audit "What I'd
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

## Findings (2026-06-02)

**The sync *execution* layer does not exist yet.** Every orchestration entry
point is a stub that raises `NotImplementedError` "wired in v1.1":

- `integrations/tasks.py` — `push_pending`, `reconcile_provider`,
  `refresh_oauth_tokens` are bare skeletons (no `@shared_task`, Celery not yet
  configured).
- `integrations/services/zoho.py` `ZohoSyncClient.{push,pull,reconcile,fingerprint}`
  all raise `NotImplementedError`. `SyncClient` (`sync_client.py`) is just the ABC.

So the three questions are presently moot — nothing reads or writes `SyncRun` /
`SyncIssue` / `SyncRecord` status at runtime except the `post_save` row-creation
and `post_delete` cleanup handlers in `integrations/signals.py` (the latter added
by [FG-007](fg-007-syncrecord-genericfk-dangling.md)). Answering against the
schema as it stands:

1. **Failed-attempt cleanup.** None automated. `SyncRecord` carries
   `status` (incl. `ERROR`) + `error_message`; `SyncIssue` is append-only with
   explicit `resolved_at` / `resolved_by` / `resolution` (ops-resolved, not
   auto-purged — consistent with the no-soft-delete audit-table convention);
   `SyncRun` is append-only audit with `records_{processed,succeeded,failed}` and
   a `RUNNING/SUCCEEDED/FAILED/PARTIAL` status. The substrate is there; no sweeper
   or auto-resolution task is.
2. **Retry strategy.** None implemented, and **`SyncRecord.retry_count` is inert**
   — declared but never read or written anywhere in the codebase. The implied
   model (per `push_pending`'s docstring) is "leave the row `PENDING`; the next
   beat re-pushes" — i.e. unbounded retry with no backoff and no dead-letter.
3. **At-least-once.** The persist-first `PENDING` `SyncRecord` plus the
   `unique (content_type, object_id, provider)` constraint give an at-least-once-
   shaped substrate (a row stays `PENDING` until a push succeeds; the unique key
   prevents duplicate records). Exactly-once is neither provided nor expected.
   No remote-side idempotency key beyond `external_id` is captured. No schema
   hole for at-least-once — the only gap is that nothing executes the retries.

**One concrete schema gap to carry into the v1.1 execution slice:** there is no
retry cap / backoff. When `push_pending` / `reconcile_provider` are wired, decide
on a max-retry bound and a terminal dead-letter state (the `ERROR` status +
`retry_count` are the natural substrate — wire `retry_count` to increment and
gate re-push, and stop retrying past a cap) so a permanently-failing record
doesn't re-push every beat forever. Flagged here rather than as its own ticket
because it's only actionable once execution exists.

## Outcome

✅ Investigation closed. **No live holes today** — the failure-handling surface
is unbuilt by design (v1.1), and the schema is adequate for at-least-once. No
per-finding tickets opened now; the retry-cap / dead-letter consideration above
should be folded into the v1.1 sync-execution work alongside
[GAP-002](gap-002-integrations-empty-url-surface.md).
