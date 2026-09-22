> **✅ RESOLVED (2026-09-22)** — Problem: four WebP files stored as `.jpeg` were known only by count, and `import_legacy_images` built its read path from DB free text with no validation. Fix: the four storage keys are recorded in §1 (option 1, no S3 touched; the `image/webp` re-upload recipe is there for when a consumer appears); `import_legacy_images` now runs the same `unsafe_rows` pre-flight as `fetch_legacy_images` and aborts listing the rows, dry-run included, with tests (commit 200b28cd).
>
> _Original ticket preserved below for context._

# SMELL-026 — Legacy-image loose ends: four WebP-as-`.jpeg`, unvalidated read path

**Severity:** smell (two small, known items parked during GAP-012/GAP-120 so
the cutover was not blocked on them).

**Status:** ✅ resolved 2026-09-22 (filed the same day).

**Source:** GAP-012 §fetch notes ("4 WebP … named `.jpeg`") and the module
docstring of `properties/management/commands/import_legacy_images.py`
("Accepted risk … hardening this read path is a follow-up").

## 1. Four WebP files named `.jpeg` (villa 412)

The legacy archive holds 18,216 JPEG, 12 PNG and 4 WebP; the four WebP are
stored under `.jpeg` names, so S3 labels them `image/jpeg`. Browsers sniff and
render them, but anything that trusts the extension — a future resize layer,
`PIL.Image.open` in a thumbnailer, a strict CDN — will choke on exactly these
four. Options, cheapest first:

- Leave them, and record the four keys here so the next person knows.
- Re-upload the four objects with `ContentType: image/webp` (same key, so no
  row changes) — one `aws s3 cp --metadata-directive REPLACE` each, in both
  buckets once production is filled.
- Convert to real JPEG and re-upload under the same key.

Any of the three closes the item; pick the first unless a consumer appears.

**Recorded 2026-09-22 (option 1).** Found by scanning every file under
`~/villacollective-legacy/PropertyImages/412/` for the RIFF/WebP magic —
exactly four, all under `.jpeg` names, none elsewhere in the archive. Storage
keys (`LEGACY_PREFIX` + filename):

- `properties/legacy/18fd9bd3-af59-4078-9262-e4410bb11c0b.jpeg`
- `properties/legacy/3985bf48-ce2a-47f4-887e-f4034677144e.jpeg`
- `properties/legacy/73ae334f-375b-4070-8616-ae7f949d5cec.jpeg`
- `properties/legacy/d3e72cbc-86b8-49f9-a35a-2126a5867eb1.jpeg`

Full S3 object keys carry the storage `location` prefix: `staging/<key>` in
bucket `villacollective-images` and `production/<key>` in
`villacollective-images-prod` (`settings/staging.py`, `settings/production.py`).
Three are plain VP8 768×512; `3985bf48…` reports no VP8 detail line (`file`
prints only "RIFF … Web/P"), so it is likely VP8L/extended — relevant only if
conversion is ever chosen.

If a consumer appears, option 2 is four commands per bucket, same key, no row
changes:

```sh
aws s3 cp s3://<bucket>/<location>/<key> s3://<bucket>/<location>/<key> \
  --metadata-directive REPLACE --content-type image/webp
```

## 2. `import_legacy_images` builds a read path from free text

`<source>/<property.legacy_id>/<filename>` uses DB-sourced values without
re-validation, so a crafted `filename` like `../../etc/passwd` would read
outside `--source` and upload it to S3 under the row's key. `fetch_legacy_images`
already refuses such rows via `properties.services.legacy_images.unsafe_rows`;
the current load is clean, so this is a hygiene fix, not an incident.

Fix: call the same `unsafe_rows` check at the top of `import_legacy_images`
and abort with the offending rows listed, mirroring the colliding-keys abort
that is already there. Add the test the fetch command has. Remove the
"Accepted risk" paragraph from the docstring.

## Acceptance

- The four WebP keys are listed here, or their content type corrected.
- `import_legacy_images` aborts on a row with an unsafe segment, with a test.
