# CHECK-001 — Zoho contact flow: fixes raised with Limitless

- **Severity:** 🔎 Check (external party — nothing to build here; this ticket
  is closed by *verifying* someone else's change).
- **Owner of the work:** Limitless (Zoho Flow `limitless_parse_res_contact`).
  Not in this repo.
- **Raised:** 2026-09-01, by email, off the contact-sync demo transcript +
  the Deluge parse function.
- **Verify with:** `manage.py zoho_send_sample` (synthetic enum-coverage
  graph → sample webhooks → rollback) against the Limitless sandbox, then
  read the resulting Contact records. See
  `django_res/seeding/management/commands/zoho_send_sample.py`.

## Why this is a check, not a gap

Everything below is a mapping defect on the Zoho side of the integration. Our
payload (`django_res/integrations/services/zoho_payloads.py`) already carries
the data each item needs; nothing changes here. The ticket exists so the
fixes don't quietly not-happen — a Flow that silently mis-maps looks
identical from res, because we mark a push `IN_SYNC` on any HTTP 2xx (see
GAP-097).

## Items to verify

1. **Email-fallback dedupe must not merge two people.** When the RES_ID
   search misses and the Email search hits, the Flow overwrites RES_ID on
   whatever record it found. `PersonEmail` is `unique(contact, email)`, NOT
   globally unique (`accounts/models/person.py:494`), so two people sharing
   an address is legal and common. Asked for: accept the email match only
   when the found record's RES_ID is empty or equal; otherwise create.
   - *Verify:* push two Persons sharing one email; expect two Contacts.

2. **Agency-only contacts must create.** `first_name`/`last_name` are both
   `blank=True` (GAP-029 — a contact may carry an agency and no personal
   name). The guards test `!= null` but not `!= ""`, so `Last_Name` goes up
   empty and Zoho rejects it as mandatory. Asked for: fall back to the agency
   name.
   - *Verify:* push a name-less, agency-linked Person; expect a Contact.

3. **Phone labels — five, not two.** `PhoneLabel` is `mobile`, `work`,
   `home`, `fax`, `other` (`accounts/enums.py`). Today `work`/`fax`/`other`
   all collapse into `Other_Phone` last-one-wins, and Zoho's main `Phone`
   field is never populated at all. Asked for: `work` → `Phone`, `fax` →
   `Fax`, `is_primary` to win over array order, and the `x`-suffix strip
   fixed (`"020 1234 ext 5"` currently yields `"020 1234 e"`; uppercase `X`
   is missed).
   - *Verify:* push a Person with one number of each label.

4. **Address line 2 is not a state.** `address_line_2` currently lands in
   `Address_1_State_Province`. Asked for: append to
   `Address_1_Street_Address` after a newline.

5. **`town` must map to `Address_1_City`.** Dropped on a misreading of our
   "leave City empty *unless* town is non-blank" note. The field is captured
   going forward (`accounts/serializers/contact.py:103`).

6. **The agency link must be un-stickable.** `if (agency != null)` sets
   `Contact_Type: Agency` with no `else`, and the agency-address fallback is
   never withdrawn — so unlinking an agency in res leaves both in the CRM
   forever. `Person.agency` is an editable FK (GAP-046), so this will happen.
   - *Verify:* push a Person with an agency, unlink it, push again.

7. **Tags must be removable.** `add_tags` is called, `remove_tags` never is.
   Matters most for the GAP-040 special-category markers (`disability`,
   `approach_with_care`, `past_issues`, `time_waster`), which push in full
   (`SENSITIVE_TAGS` is deliberately empty). Asked for: diff against the
   record's current tags and remove the difference.
   - *Verify:* push a Person with a tag, remove it, push again.
   - Related, not asked: their display map mirrors `PersonTag` by hand — a
     new tag our end will silently create a snake_case tag in Zoho.

8. **`RES_Status` / `RES_Json` are `put` after the create/update.** Both
   appear below the write block, so unless the calling Flow does a second
   write with the returned map they never reach the CRM — contradicting the
   demo. Asked: confirm which, and move the puts if it's the former.

9. **`searchRecords` indexing lag.** A just-created record isn't immediately
   searchable, so bursts (e.g. `Person.merge` folding relationship rows) can
   double-create. Suggested: Zoho's upsert API with RES_ID as the
   duplicate-check field, which also removes item 1.

## Acceptance

- Each item above confirmed fixed against the sandbox, by push-and-read
  rather than by assurance.
- The test batch we asked for has been run: no personal name; work/fax/other
  numbers; two emails with no primary; agency unlinked since last push; a tag
  removed since last push; apostrophe/accented names.
- Anything Limitless declines to change is recorded here as an accepted
  divergence with its reason, not left silent.

## Dependencies

- **GAP-095** — erasure propagation. Item 7 (add-only tags) is the same
  mechanism seen from the compliance side; do not close that ticket by
  closing this one.
- **GAP-097** — until push delivery is confirmed beyond HTTP 2xx, "verified"
  here means *a human read the CRM record*, not *res reported success*.
- **GAP-098** — the legacy `ZohoId` question sits behind item 1/9: contacts
  already in the CRM from the legacy sync carry no RES_ID.
