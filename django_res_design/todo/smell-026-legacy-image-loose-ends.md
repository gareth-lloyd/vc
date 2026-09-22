# SMELL-026 — Legacy-image loose ends: four WebP-as-`.jpeg`, unvalidated read path

**Severity:** smell (two small, known items parked during GAP-012/GAP-120 so
the cutover was not blocked on them).

**Status:** ⬜ filed 2026-09-22.

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
