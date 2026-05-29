# Villa image pool (dev/staging seed data)

A small pool of realistic villa imagery so the dev/staging UI (catalogue,
detail, search results) renders real photos instead of grey 1x1 placeholders.

**This is dev-only seed data.** It is never served to real users and has no
place in the production media pipeline.

## Layout

```
villa_images/
  manifest.yaml            # source of truth: villas + per-kind prompts
  villa_01_amalfi/
    hero.jpg
    interior.jpg
    exterior.jpg
    gallery.jpg
  villa_02_provence/
    ...
```

One subdirectory per villa keeps a stylistically coherent set together.
Filenames map 1:1 to the seeded `ImageKind` values
(`hero` / `interior` / `exterior` / `gallery`). Floor plans are deliberately
not generated — the model produces poor ones, so `FLOOR_PLAN` falls back to the
1x1 placeholder.

`manifest.yaml` is the source of truth for both the imagery *and* the seeded
property identity. Per entry:

| field          | drives                                              |
| -------------- | --------------------------------------------------- |
| `slug`         | image subdirectory name + `PropertyImage` files     |
| `display_name` | `Property.display_name`                              |
| `location_tag` | `Region` name / locality (text before the last `,`) |
| `country_iso2` | `Country` (reuses the seeded ISO-3166 row)          |
| `style_anchor` | `PropertyDescription` body (and the image prompts)  |
| `prompts`      | the generation prompt per image kind                |

## How it's consumed

`properties.factories.villa_manifest()` returns the entries that have a
generated `hero.jpg` on disk. The `properties` seed stage cycles that list —
exhausting every villa before any repeat — and builds each property from the
entry (name, region/country, description), assigning its imagery. `PropertyFactory`
writes the HERO (via `children__villa`); the `gallery` seed stage writes the
non-HERO images from the same villa (tracked on `SeedContext.property_villa`).
If the pool is absent (fresh checkout) the manifest is empty, so the seeder
falls back to random property data and a 1x1 PNG — tests and seeds still work.

## Regenerating

Generation uses OpenAI `gpt-image-1` and requires an API key:

1. Put your key in `django_res/.env` as `OPEN_AI_API_KEY=sk-...`
   (loaded via `settings.OPEN_AI_API_KEY`).
2. Dry-run a single villa to preview prompts:
   `uv run python manage.py generate_seed_images --only villa_01_amalfi --dry-run`
3. Generate it for real, then inspect the four files:
   `uv run python manage.py generate_seed_images --only villa_01_amalfi`
4. Full pass (skips files that already exist — re-runs cost nothing):
   `uv run python manage.py generate_seed_images`

Flags: `--only <slug>`, `--kind <hero|interior|exterior|gallery>`,
`--quality <low|medium|high|auto>`, `--dry-run`, `--force` (overwrite).

To add or re-roll villas, edit `manifest.yaml` and re-run. The shared style
preamble lives in the management command, not the manifest, so every image
stays coherent.
