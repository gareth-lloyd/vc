# BUG-024 — `Person.anonymize()` cannot erase anyone holding two phone numbers

- **Severity:** 🔴 Bug (a GDPR erasure raises `IntegrityError` and rolls back;
  the affected person cannot be erased at all through the supported path).
- **Source:** 2026-09-02, found while building GAP-101's `anonymised_person`
  scenario — the scenario gave its synthetic person a second phone, and the
  command failed on `unique_contact_phone`.
- **Files touched:**
  - `django_res/accounts/models/person.py:238-240` — the phone scrub loop.
  - `django_res/accounts/models/person.py:514-519` — the
    `unique_contact_phone` constraint on `(contact, number)`.

## Problem

`anonymize()` scrubs the two channel tables in visibly different ways:

```python
for email in self.emails.all():
    email.email = f"redacted-{email.pk}@anonymized.local"   # unique per row
    email.save(update_fields=["email", "updated_at"])
for phone in self.phones.all():
    phone.number = ""                                       # identical per row
    phone.save(update_fields=["number", "updated_at"])
```

`PersonEmail` and `PersonPhone` both carry a `UniqueConstraint` on
`(contact, <value>)`. The email loop respects it — the `pk`-derived sentinel is
distinct per row. The phone loop does not: every phone on the person collapses
to `""`, so the second row violates `unique_contact_phone`.

The method is `@transaction.atomic`, so the failure is clean — nothing is
half-erased. It is also total: a person with a mobile *and* a landline (an
entirely ordinary shape; `CustomerPersonFactory` plus one extra phone is enough
to reproduce) can never be anonymised. The erasure request simply errors.

Reproduce:

```python
person = CustomerPersonFactory()                       # makes a MOBILE phone
PersonPhoneFactory(contact=person, number="+44 20 7000 0002", is_primary=False)
person.anonymize()   # IntegrityError: duplicate key ... (contact_id, number)=(N, )
```

## Proposed fix

Mirror the email loop — give each phone a per-row sentinel rather than a shared
blank. `f"redacted-{phone.pk}"` keeps the rows distinct, keeps the column
non-PII, and keeps the constraint meaningful.

`""` was presumably chosen because a redacted phone number has no useful
sentinel form, but blank is also what "never captured" looks like, so the
current value is ambiguous in exactly the way **GAP-095** describes for the
Zoho payload — a per-row sentinel resolves both.

Whatever sentinel is chosen must be excluded from any outbound payload that
reaches Zoho: `push_sync_record` already refuses ANONYMIZED persons
(`integrations/tasks.py:77-82`), so nothing leaks today, but the sentinel
should not become a value the CRM could ever display.

## Acceptance

- A person with two or more phones anonymises without error. (test)
- Each scrubbed phone row holds a distinct value; none holds a real number.
  (test)
- The existing single-phone behaviour is unchanged apart from the sentinel.
  (test)
- GAP-101's `anonymised_person` scenario gains a second phone once this lands,
  so the regression is exercised by the sample too.

## Dependencies

- **GAP-095** — same "blank means two different things" problem, one layer out.
- **GAP-101** — the scenario that found it; it deliberately keeps one phone so
  the sample stays on the working path until this is fixed.
