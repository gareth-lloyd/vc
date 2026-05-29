"""`./manage.py generate_seed_images` — build the committed villa image pool.

A one-off (re-runnable) operation that turns the prompt manifest at
`core/seed_data/villa_images/manifest.yaml` into a small pool of realistic
villa JPEGs, committed to the repo and drawn from by `PropertyFactory` and the
`gallery` seed stage. The goal is to make the dev/staging UI look like a real
product instead of grey 1x1 placeholders — not production media management.

Images are generated with OpenAI's `gpt-image-1` model (1536x1024, exactly
3:2), then re-encoded locally with Pillow to ~1200px-wide JPEGs so we control
the size/quality tradeoff. Four images per villa map 1:1 to the seeded
`ImageKind` values: hero / interior / exterior / gallery. Floor plans are
deliberately not generated (the model produces poor ones).

The command writes to the working tree, not the database, so it is *not*
guarded by `SEED_DEV_ALLOWED`. It refuses to run without `OPEN_AI_API_KEY`
(set it in `.env`; loaded via `settings.OPEN_AI_API_KEY`).

Idempotent by default: an existing destination file is skipped, so re-runs
only fill gaps and cost nothing. `--force` regenerates.

Examples:

  ./manage.py generate_seed_images --only villa_01_amalfi --dry-run
  ./manage.py generate_seed_images --only villa_01_amalfi
  ./manage.py generate_seed_images            # full manifest pass
  ./manage.py generate_seed_images            # re-run -> all skipped, no API calls
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

# Prepended to every prompt so the whole pool stays stylistically coherent
# without copy-pasting boilerplate into each manifest line. gpt-image-1 has no
# negative-prompt field, so the exclusions live in the positive prompt.
STYLE_PREAMBLE = (
    "Photorealistic high-end real-estate photography, natural golden-hour "
    "lighting, magazine-quality composition, sharp focus, professional colour "
    "grading. No people, no text, no logos, no watermarks, no signage."
)

# gpt-image-1 always returns base64 (no URL fetch). 1536x1024 is exactly 3:2,
# matching a typical real-estate hero crop.
MODEL = "gpt-image-1"
SIZE = "1536x1024"
DEFAULT_QUALITY = "medium"

# Local re-encode: downscale to ~1200px wide JPEGs to keep the repo footprint
# small (~150-250 kB each, ~12-20 MB for the whole 80-image pool).
MAX_WIDTH = 1200
JPEG_QUALITY = 80

# Be gentle on rate limits between real API calls.
SLEEP_BETWEEN_CALLS = 1.0

KINDS = ("hero", "interior", "exterior", "gallery")

IMAGE_ROOT = Path(settings.BASE_DIR) / "core" / "seed_data" / "villa_images"
MANIFEST_PATH = IMAGE_ROOT / "manifest.yaml"


def _build_prompt(style_anchor: str, kind_prompt: str) -> str:
    return f"{STYLE_PREAMBLE} {style_anchor.strip()} {kind_prompt.strip()}"


def _to_jpeg(png_bytes: bytes) -> bytes:
    """Re-encode raw model bytes to a downscaled, quality-capped JPEG."""
    with Image.open(io.BytesIO(png_bytes)) as img:
        rgb = img.convert("RGB")
        if rgb.width > MAX_WIDTH:
            height = round(rgb.height * MAX_WIDTH / rgb.width)
            rgb = rgb.resize((MAX_WIDTH, height), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        rgb.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue()


class Command(BaseCommand):
    help = "Generate the committed villa image pool from the prompt manifest."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--only",
            metavar="SLUG",
            help="Generate a single villa by manifest slug (e.g. villa_01_amalfi).",
        )
        parser.add_argument(
            "--kind",
            choices=KINDS,
            help="Generate a single image kind across the selected villas.",
        )
        parser.add_argument(
            "--quality",
            choices=("low", "medium", "high", "auto"),
            default=DEFAULT_QUALITY,
            help=f"gpt-image-1 quality tier (default: {DEFAULT_QUALITY}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print intended API calls and write nothing.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate even if the destination file already exists.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        villas = self._load_manifest()

        only: str | None = options["only"]
        if only is not None:
            villas = [v for v in villas if v["slug"] == only]
            if not villas:
                raise CommandError(f"No villa with slug {only!r} in {MANIFEST_PATH}.")

        kinds = (options["kind"],) if options["kind"] else KINDS
        dry_run: bool = options["dry_run"]
        force: bool = options["force"]

        client = None if dry_run else self._build_client()

        generated = skipped = failed = 0
        for villa in villas:
            slug = villa["slug"]
            for kind in kinds:
                dest = IMAGE_ROOT / slug / f"{kind}.jpg"
                if dest.exists() and not force:
                    skipped += 1
                    self.stdout.write(f"  skip  {slug}/{kind}.jpg (exists)")
                    continue

                prompt = _build_prompt(villa["style_anchor"], villa["prompts"][kind])

                if dry_run:
                    self.stdout.write(f"  call  {slug}/{kind}.jpg")
                    self.stdout.write(self.style.HTTP_INFO(f"        {prompt}"))
                    continue

                try:
                    self._generate_one(client, prompt, dest, options["quality"])
                except Exception as exc:  # report per-image and continue
                    failed += 1
                    self.stderr.write(self.style.ERROR(f"  FAIL  {slug}/{kind}.jpg: {exc}"))
                    continue

                generated += 1
                self.stdout.write(self.style.SUCCESS(f"  ok    {slug}/{kind}.jpg"))
                time.sleep(SLEEP_BETWEEN_CALLS)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. generated: {generated}, skipped: {skipped}, failed: {failed}"
            )
        )
        if failed:
            raise CommandError(f"{failed} image(s) failed to generate.")

    def _load_manifest(self) -> list[dict[str, Any]]:
        if not MANIFEST_PATH.is_file():
            raise CommandError(f"Manifest not found: {MANIFEST_PATH}")
        data = yaml.safe_load(MANIFEST_PATH.read_text())
        if not isinstance(data, list) or not data:
            raise CommandError(f"Manifest {MANIFEST_PATH} must be a non-empty list of villas.")
        return data

    def _build_client(self) -> Any:
        api_key = settings.OPEN_AI_API_KEY
        if not api_key:
            raise CommandError(
                "OPEN_AI_API_KEY is not set. Add it to .env (loaded via "
                "settings.OPEN_AI_API_KEY) before generating images."
            )
        # Imported lazily so the command module imports without the SDK present
        # (e.g. during a --help on a checkout that hasn't run `uv sync`).
        from openai import OpenAI

        return OpenAI(api_key=api_key)

    def _generate_one(self, client: Any, prompt: str, dest: Path, quality: str) -> None:
        resp = client.images.generate(
            model=MODEL,
            prompt=prompt,
            size=SIZE,
            quality=quality,
            n=1,
        )
        b64 = resp.data[0].b64_json if resp.data else None
        if not b64:
            raise RuntimeError("image response contained no b64_json payload")
        png_bytes = base64.b64decode(b64)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_to_jpeg(png_bytes))
