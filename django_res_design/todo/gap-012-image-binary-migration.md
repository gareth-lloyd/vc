# GAP-012 — Image binary migration (legacy `wwwroot/PropertyImages` → new storage)

**Severity:** gap (designed-but-unbuilt; the DB rows are migrated, the files
are not).

**Status:** ⬜ open — tracker. The `PropertyImage` rows land via the loader;
the actual image binaries are **not** copied by any code today. This ticket is
the canonical home for that workstream, which `CUTOVER.md §8` defers to ("Image
migration workstream") without tracking anywhere.

**Source:** `django_res/data_migration/CUTOVER.md §8` ("Image files (out of
scope here)"); confirmed against the legacy app + a live load on 2026-06-09.

## Problem

`PropertyImageLoader` (`data_migration/loaders/property_children.py:71-119`)
imports one `properties_propertyimage` row per legacy `VillaPropertyImages`
row, storing the image field as:

```python
"image": f"properties/legacy/{filename}"   # filename = VillaPropertyImages.Name
```

So the DB knows the **filename** but the binary itself is never copied into the
new storage backend. A current load has **12,283** such rows
(`reconcile_legacy`, 2026-06-09). Until the files exist at the keys the rows
point at, every gallery / hero image resolves to a 404, and any UI that
surfaces them (catalogue, quote flow — see GAP-005's imagery slice) shows broken
images.

### Where the legacy files live (verified)

The legacy .NET app stores property images **nested under the integer villa id**,
not flat:

- `NewResSystem/Bases/Component.cs:213,219,239`
  ```csharp
  public string PropertyImagesFolder = "PropertyImages";
  Path.Combine(GetWwwRootPath, PropertyImagesFolder, villaid.ToString(), imageName)
  // → wwwroot/PropertyImages/<VillaId>/<imageName>
  ```
- Rendered URL (`Pages/Bookings/Booking.razor:89`):
  `https://vc2.mojodev.co.uk/PropertyImages/<VillaId>/<filename>`

The files are **not** in the repo or the running container —
`res-app:/app/wwwroot/PropertyImages` is empty (0 files) and the path is
gitignored (`.gitignore:399`, `.dockerignore:13`). They live wherever ops
archived the legacy `wwwroot/PropertyImages/` tree (S3 / backup tarball); ops
must export it before this can run.

### The reconstruction gotcha (load-bearing)

The loader **kept the filename but dropped the `<VillaId>` subfolder**. So the
Django row alone cannot locate its source file. The mapping is:

| Need | Source |
|---|---|
| target storage key | `PropertyImage.image` = `properties/legacy/<filename>` (flat) |
| `<filename>` | tail of `image`; = legacy `VillaPropertyImages.Name` |
| `<VillaId>` (source subfolder) | `PropertyImage.property.legacy_id` (= legacy `VillaMaster.Id`) — **not** in the `image` string |

So the copy is **nested source → flat target**:

```
PropertyImages/<property.legacy_id>/<filename>   →   <MEDIA>/properties/legacy/<filename>
```

Worked example (real row, 2026-06-09): `properties/legacy/9436180e-6cb5-4f59-8995-58fe3e02bc64.jpg`
on a property with `legacy_id=1` came from
`wwwroot/PropertyImages/1/9436180e-6cb5-4f59-8995-58fe3e02bc64.jpg`.

### Flatten-collision check (passed for this dump, but verify per dump)

Flattening into one `properties/legacy/` directory is only safe if filenames
are globally unique across villas. Verified 2026-06-09: **12,293 rows, 12,293
distinct image keys, 0 collisions** — legacy `Name` values are GUIDs
(`<guid>.jpg`), so flattening is safe here. This is a property of the data, not
a guarantee: re-verify on the cutover dump (a single colliding `Name` across two
villas would make two rows resolve to one file, silently overwriting).

## Proposed fix

A one-shot migration step (management command, run during cutover after
`loadlegacy`), driven by the `PropertyImage` rows so it copies exactly the files
the DB references:

1. Take ops' export of the legacy `wwwroot/PropertyImages/` tree (nested by
   villa id) as the source root.
2. For each `PropertyImage` with a `properties/legacy/` key, reconstruct the
   source path `<root>/<property.legacy_id>/<filename>` and copy the bytes to
   the new storage at the row's `image` key (`default_storage`, so it works for
   local `MEDIA_ROOT` and S3 alike).
3. Report: copied, missing-at-source (row points at a file ops didn't export),
   and any flatten-collision. Missing-at-source is the expected-loss bucket —
   log it, don't crash the run.

Idempotent: skip keys already present in the target so re-runs are cheap (mirrors
the loader discipline).

## Acceptance

- A command (e.g. `manage.py migrate_image_files --source <path>`) copies every
  `PropertyImage.image` binary from the nested legacy tree into the new storage
  backend at its flat `properties/legacy/<filename>` key.
- Run is idempotent (re-run copies nothing new) and reports
  copied / missing-at-source / collision counts.
- A verification pass confirms every `PropertyImage` with a `properties/legacy/`
  key has a resolvable object in `default_storage` (and lists any that don't).
- Hero/gallery images resolve (200, not 404) through the API/serializer
  (`properties/serializers/image.py`) for a sampled property.
- Re-runs the flatten-collision check against the cutover dump before copying.

## Dependencies

- **Blocked by** ops exporting the legacy `wwwroot/PropertyImages/` tree (the
  binaries are not in this repo).
- **Blocked by** the prod storage-backend decision (local `MEDIA_ROOT` vs S3) —
  the copy targets `default_storage`, so it's backend-agnostic, but the backend
  must be chosen/wired for the prod deploy.
- **Related:** `CUTOVER.md §8` (the deferral this ticket tracks); `GAP-005`
  (quote-flow imagery — its "data already exists" slice assumes the binaries
  actually resolve); `INV-005` (`legacy_id` indexing — the reconstruction relies
  on `Property.legacy_id`).
