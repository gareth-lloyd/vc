"""Download the legacy property-image binaries from the legacy host to local disk.

GAP-012 flipped storage to S3, but nobody ever produced the legacy image
binaries: the rows exist with `properties/legacy/<guid>.jpg` keys and no backing
files, so every legacy villa photo 404s the moment production reads from S3. The
ticket assumed those binaries would arrive as an ops export of the legacy Docker
volume (`res-app-images:/app/wwwroot/PropertyImages`). They don't have to — the
legacy .NET app serves every one of them publicly from
`<base-url>/<VillaId>/<filename>` (the URL is hardcoded at
`PropertyService2.cs:766`; see
`django_res_design/legacy/workflows/03-catalog/property-imagery.md:20`).

This command fetches that tree into `<dest>/<legacy_id>/<filename>` — the exact
layout `import_legacy_images --source` already consumes, so the upload half needs
no changes. Nothing here writes to the database, and the DB connection is
released a second in: rows are read once, in the main thread, before the pool
starts, and workers do HTTP plus filesystem writes only.

Re-run semantics — the filesystem IS the ledger. No manifest, no checkpoint, no
`--resume`: each file is streamed to `<name>.part` and then `os.replace()`d into
place, so an interrupted run can never leave a partial file that a later run
mistakes for a complete one. Startup sweeps stale `.part` files and re-runs skip
any existing file at or above `MIN_IMAGE_BYTES`. Kill it at hour two and re-run;
it picks up where it stopped. There is no `--force`: to re-fetch a file, delete
it and re-run.

Accepted risks:

- "Skipped" assumes presence ⇒ correctness. A file already on disk is trusted
  (size aside), because verifying content would mean re-downloading it.
- 404 is the documented expected-loss bucket: reported, never retried. A 404
  *rate* above `MISSING_ABORT_RATIO` aborts, though — 18k 404s from a pruned
  source tree must not be reported as routine loss.
- mtimes are not preserved and nothing depends on them.
- Failures are reported, not repaired: a failed file simply has no final file,
  so the next run's skip diff IS the retry list. `.fetch-report.txt` is a
  diagnostic, not an input.

Why threads (`ThreadPoolExecutor` has no precedent here, so it needs a reason):
`httpx.Limits` *caps* a connection pool, it does not create concurrency — a
synchronous loop has exactly one request in flight whatever limits you set, and
measures 0.76 files/s ≈ 6.7 hours for this tree. Concurrency 8 measures 2.11
files/s ≈ 2.4 hours; 16 is three times *slower* (the server degrades), hence
`MAX_CONCURRENCY`. `asyncio` would mean async plumbing inside a sync
`handle()`; Celery would be far heavier than a one-shot operator-run download.
So: a fixed pool whose workers share nothing — they take plain tuples, touch
neither the ORM nor storage, and return a result tuple. All aggregation and all
output happens in the main thread (`self.stdout` is not thread-safe), and retry
sleeps happen inside workers so a bad patch never serialises the pool.

Running this against someone else's production server — read before you start:

- The target is a third party's live web server, still serving the legacy site
  to real users. Run it off-peak. Mitigations for going ahead without notifying
  them: concurrency capped, an identifying User-Agent, a circuit breaker, and an
  operator watching the first `--limit 200`.
- It moves ~10.3 GB of *their* egress, which no concurrency limit reduces and a
  hosting plan may cap. That is why the local archive is kept afterwards rather
  than deleted: we pay this cost exactly once.
- Sustained connections from one IP can trip a bot rule and block the operator.
  If that happens, stop and wait — do not switch IPs.
- There is no directory listing (that URL answers 200 with the Blazor SPA
  shell), so the DB row set is the only manifest. Anything on the server but not
  in the DB is out of scope.
- NOT a task. One-time, operator-run, never scheduled and never Celery-wrapped.

GAP-106 ships image URLs, never binaries, and this preserves every row's
existing key, so those URLs stay stable; the archive is also the durable
original-bytes source if `gap-106-res-to-website-push.md` §Unit 8 later re-keys
images to SEO filenames.

Examples:
    # Pre-flight only: validates the data and the destination in ~2 seconds.
    uv run python manage.py fetch_legacy_images --dry-run

    # Smoke run, watched, to get a real throughput number.
    uv run python manage.py fetch_legacy_images --limit 200

    # The real thing. `caffeinate -i` because system sleep kills a 2.4h run,
    # tmux because a closed terminal SIGHUPs it.
    caffeinate -i uv run python manage.py fetch_legacy_images

    # Gentler, if the host starts to struggle.
    uv run python manage.py fetch_legacy_images --concurrency 4 --delay 0.25

Cutover runbook: `django_res_design/todo/gap-012-s3-image-hosting.md`.
"""

from __future__ import annotations

import errno
import os
import random
import shutil
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote

import httpx
import structlog
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.console import render_table
from properties.services.legacy_images import (
    LegacyRow,
    case_collisions,
    duplicate_keys,
    filename_for,
    legacy_image_rows,
    unsafe_rows,
)

logger = structlog.get_logger(__name__)

# The legacy host is configured nowhere in settings (only LEGACY_DATABASE_URL
# exists, operator-supplied), and this command runs once — so no new setting.
# The URL is hardcoded at PropertyService2.cs:766.
DEFAULT_BASE_URL = "https://vc2.mojodev.co.uk/PropertyImages"
DEFAULT_DEST = "~/villacollective-legacy/PropertyImages"

# Measured on the real tree: 8 gives 2.11 files/s (11.9 Mbps); 16 collapses to
# 0.63 files/s as the server degrades. The cap encodes the measurement.
DEFAULT_CONCURRENCY = 8
MAX_CONCURRENCY = 16

# Tasks are submitted in a sliding window of this many per worker rather than
# all 18k up front. Submitting everything lets the pool race ahead of the main
# thread, so the circuit breaker and Ctrl-C only take effect after the queue has
# already drained — i.e. not at all. A small window keeps workers fed while
# bounding how many requests can still be issued after the run decides to stop.
IN_FLIGHT_PER_WORKER = 2

PROGRESS_EVERY = 250
DETAIL_CAP = 20
CHUNK_BYTES = 64 * 1024

DEFAULT_RETRIES = 3
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 30.0

# Stop rather than spend two more hours hammering a box that has started
# refusing us (a WAF wall, a maintenance page, the host falling over).
CONSECUTIVE_FAILURE_ABORT = 50
# A pruned source tree would otherwise land 18k rows in the never-fatal
# "missing at source" bucket and read as routine loss. 120/120 sampled OK.
MISSING_ABORT_RATIO = 0.10
MISSING_ABORT_FLOOR = 100

# Mean file size on the real tree; used for the free-space pre-flight only.
MEAN_IMAGE_BYTES = 594_000
DISK_SAFETY_FACTOR = 1.5
# Smaller than any real photo — catches truncation and empty bodies, and marks
# an existing file as untrustworthy so it is re-fetched.
MIN_IMAGE_BYTES = 1024

PART_SUFFIX = ".part"
LOCK_NAME = ".fetch.lock"
REPORT_NAME = ".fetch-report.txt"

# Sniffed on the first streamed chunk, so a wrong body costs no bandwidth.
# Keyed on bytes, never the extension: the data holds uppercase `.JPG`.
IMAGE_MAGIC = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"GIF87a",
    b"GIF89a",
    b"BM",  # BMP
)

# Deliberately not the house `_HTTP_TIMEOUT = 20.0` scalar: a multi-MB body from
# a degraded IIS box can exceed 20s in total, but `read` is per chunk-read, so
# this bounds a stall without punishing a large file. `pool=None` stops a worker
# waiting for a free connection from failing spuriously.
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=None)

# No UA convention exists in this repo (ical_ingest sets none); this is a
# deliberate add. Against a third party's production server it is the difference
# between "unknown bot" and a client whose owner can be identified.
USER_AGENT = "villacollective-legacy-image-fetch/1.0 (one-time GAP-012 migration)"

_DOWNLOADED = "downloaded"
_SKIPPED = "skipped (already present)"
_MISSING = "missing at source (404)"
_REDIRECT = "unexpected redirect"
_REJECTED = "rejected (not an image)"
_FAILED = "failed"
_NO_LEGACY_ID = "no property legacy_id"
_SWEPT = "stale .part swept"
# A worker that returned because the run was stopping; counted nowhere.
_STOPPED = "not attempted"

_PROBLEM_BUCKETS = (_MISSING, _REDIRECT, _REJECTED, _FAILED)


class _NotAnImage(Exception):
    """The body is not an image, decided from its leading bytes."""


class _Task(NamedTuple):
    """Everything a worker needs. Built in the main thread; workers share nothing."""

    pk: int
    url: str
    target: Path


class _Result(NamedTuple):
    pk: int
    bucket: str
    detail: str
    # Non-empty when the whole run must stop (e.g. the disk filled up).
    fatal: str = ""


def _is_git_work_tree(candidate: Path) -> bool:
    """True if `candidate` is the root of a git work tree.

    Tests for a real repository rather than the mere existence of `.git`: a
    normal clone's `.git` is a directory that always holds `HEAD`, and a
    worktree or submodule's is a file pointing at the real gitdir. The
    distinction is load-bearing — a stray empty `.git/` directory that git
    itself does not recognise (there is one in this operator's `$HOME`) would
    otherwise veto every path beneath it, including the default archive.
    """
    marker = candidate / ".git"
    return marker.is_file() or (marker / "HEAD").is_file()


def _looks_like_image(prefix: bytes) -> bool:
    if any(prefix.startswith(magic) for magic in IMAGE_MAGIC):
        return True
    # WebP: "RIFF" <4-byte length> "WEBP".
    return prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP"


def _discard(part: Path) -> None:
    try:
        part.unlink(missing_ok=True)
    except OSError:  # nothing useful to do; the startup sweep will get it
        pass


def _stream_to_part(response: httpx.Response, part: Path) -> int:
    """Stream the body to `part`, returning its size. Raises `_NotAnImage` early."""
    size = 0
    with part.open("wb") as fh:
        for index, chunk in enumerate(response.iter_bytes(CHUNK_BYTES)):
            if index == 0 and not _looks_like_image(chunk):
                raise _NotAnImage("body is not an image (magic bytes)")
            fh.write(chunk)
            size += len(chunk)
    return size


def _fetch_one(
    client: httpx.Client,
    task: _Task,
    *,
    delay: float,
    retries: int,
    stop: threading.Event,
) -> _Result:
    """Fetch one file. HTTP and filesystem only — no ORM, no storage, no output."""
    part = task.target.with_name(task.target.name + PART_SUFFIX)
    last_error = "no attempt made"
    for attempt in range(retries + 1):
        if stop.is_set():
            return _Result(task.pk, _STOPPED, "")
        if delay:
            time.sleep(delay)
        try:
            with client.stream("GET", task.url) as response:
                if response.status_code == 404:
                    return _Result(task.pk, _MISSING, task.url)
                if response.is_redirect:
                    location = response.headers.get("location", "?")
                    return _Result(task.pk, _REDIRECT, f"{task.url} -> {location}")
                if response.status_code in RETRY_STATUSES:
                    last_error = f"HTTP {response.status_code}"
                elif response.status_code != 200:
                    return _Result(task.pk, _FAILED, f"{task.url} (HTTP {response.status_code})")
                else:
                    return _download(response, task, part)
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            _discard(part)
        if attempt < retries:
            backoff = min(RETRY_MAX_DELAY, RETRY_BASE_DELAY * 2**attempt)
            # Jitter so a burst of workers does not retry in lockstep.
            time.sleep(backoff + random.uniform(0, RETRY_BASE_DELAY))
    return _Result(task.pk, _FAILED, f"{task.url} ({last_error})")


def _download(response: httpx.Response, task: _Task, part: Path) -> _Result:
    content_type = response.headers.get("content-type", "")
    # The measured trap: a directory URL answers 200 with the Blazor SPA shell,
    # which without this guard is saved as a .jpg and surfaces months later.
    if not content_type.startswith("image/"):
        return _Result(task.pk, _REJECTED, f"{task.url} (Content-Type: {content_type or 'none'})")
    task.target.parent.mkdir(parents=True, exist_ok=True)
    try:
        size = _stream_to_part(response, part)
    except _NotAnImage as exc:
        _discard(part)
        return _Result(task.pk, _REJECTED, f"{task.url} ({exc})")
    except OSError as exc:
        _discard(part)
        if exc.errno == errno.ENOSPC:
            # Every remaining file would fail too; a 15,000-line failure list
            # is useless, so this stops the run instead.
            return _Result(
                task.pk,
                _FAILED,
                f"{task.url} ({exc.strerror})",
                f"no space left on device while writing {part}",
            )
        return _Result(task.pk, _FAILED, f"{task.url} ({exc})")
    if size < MIN_IMAGE_BYTES:
        _discard(part)
        return _Result(task.pk, _REJECTED, f"{task.url} ({size} bytes, under {MIN_IMAGE_BYTES})")
    # Atomic: an interrupted run can never leave a partial file that a later
    # run mistakes for a complete one.
    os.replace(part, task.target)
    return _Result(task.pk, _DOWNLOADED, "")


class Command(BaseCommand):
    help = (
        "Download the legacy property-image binaries into "
        "<dest>/<property.legacy_id>/<filename>, the layout import_legacy_images consumes."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dest",
            default=DEFAULT_DEST,
            help=(
                "Directory to write the nested PropertyImages tree into. Must be "
                f"outside any git work tree. Default: {DEFAULT_DEST}"
            ),
        )
        parser.add_argument(
            "--base-url",
            default=DEFAULT_BASE_URL,
            help=f"Legacy PropertyImages base URL (https only). Default: {DEFAULT_BASE_URL}",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=DEFAULT_CONCURRENCY,
            help=f"Parallel downloads, 1..{MAX_CONCURRENCY}. Default: {DEFAULT_CONCURRENCY}",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.0,
            help="Seconds to wait before each request — the 'be gentler' knob.",
        )
        parser.add_argument(
            "--retries",
            type=int,
            default=DEFAULT_RETRIES,
            help=f"Retries per file for transport errors and {sorted(RETRY_STATUSES)}.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Download at most N files this run (0 = no limit). Use for a smoke run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run every pre-flight check and report the plan without fetching.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        concurrency: int = options["concurrency"]
        if not 1 <= concurrency <= MAX_CONCURRENCY:
            raise CommandError(
                f"--concurrency must be 1..{MAX_CONCURRENCY} — measured throughput peaks "
                f"at {DEFAULT_CONCURRENCY} and collapses above it as the source degrades"
            )
        delay: float = options["delay"]
        retries: int = options["retries"]
        limit: int = options["limit"]
        if delay < 0 or retries < 0 or limit < 0:
            raise CommandError("--delay, --retries and --limit must be >= 0")
        base_url: str = options["base_url"].rstrip("/")
        if not base_url.startswith("https://"):
            raise CommandError(f"--base-url must be https, got {base_url!r}")

        dest = Path(options["dest"]).expanduser()
        self._reject_unsafe_dest(dest)
        dest = dest.resolve()
        dest.mkdir(parents=True, exist_ok=True)
        # Always first, so an operator reading a scrollback knows what was written.
        self.stdout.write(f"archive destination: {dest}")

        lock = self._acquire_lock(dest)
        try:
            self._fetch(
                dest=dest,
                base_url=base_url,
                concurrency=concurrency,
                delay=delay,
                retries=retries,
                limit=limit,
                dry_run=options["dry_run"],
            )
        finally:
            _discard(lock)

    # -- pre-flight ---------------------------------------------------------

    def _reject_unsafe_dest(self, dest: Path) -> None:
        """The archive is ~10 GB and must never be committable.

        A `.gitignore` entry would only paper over it; refusing the path is what
        actually enforces it. Walk up rather than shelling out to git.
        """
        for candidate in (dest, *dest.parents):
            if _is_git_work_tree(candidate):
                raise CommandError(
                    f"--dest {dest} is inside the git work tree at {candidate} — the archive "
                    "is ~10 GB and must live outside the repo; pass an absolute path such as "
                    f"{DEFAULT_DEST}"
                )
        base_dir = Path(str(settings.BASE_DIR)).resolve()
        if dest.expanduser().resolve().is_relative_to(base_dir):
            raise CommandError(
                f"--dest {dest} is inside the project directory {base_dir} — pass a path "
                f"outside it, such as {DEFAULT_DEST}"
            )

    def _acquire_lock(self, dest: Path) -> Path:
        """Refuse a concurrent run: two of these against one host is the DoS we promised not to be.

        It also makes the `.part` sweep safe — a second run would delete the
        first run's in-flight temp files.
        """
        lock = dest / LOCK_NAME
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise CommandError(
                f"another fetch appears to be in progress ({lock}) — wait for it to finish, "
                f"or delete {LOCK_NAME} if no run is active"
            ) from None
        return lock

    def _abort_on_data_hazards(self, rows: list[LegacyRow]) -> None:
        """Every check here guards corruption that nothing downstream would notice."""
        duplicated = duplicate_keys(rows)
        if duplicated:
            details = sorted(
                f"{row.key} (image pk={row.pk}, property pk={row.property_pk})"
                for row in rows
                if row.key in duplicated
            )
            raise CommandError(
                f"{len(duplicated)} colliding image key(s) — flattening is unsafe, nothing was "
                "fetched; resolve the duplicate rows first:\n  " + "\n  ".join(details)
            )

        collisions = case_collisions(rows)
        if collisions:
            details = sorted(
                f"{row.legacy_id}/{filename_for(row.key)} (image pk={row.pk})"
                for _segments, group in collisions
                for row in group
            )
            raise CommandError(
                f"{len(collisions)} path(s) differ only by case — distinct in Postgres and S3 "
                "but ONE file on a case-insensitive filesystem, so the second download would "
                "silently clobber the first and both keys would get the same bytes; nothing was "
                "fetched:\n  " + "\n  ".join(details)
            )

        unsafe = unsafe_rows(rows)
        if unsafe:
            details = sorted(
                f"{row.legacy_id}/{filename_for(row.key)} (image pk={row.pk})" for row in unsafe
            )
            raise CommandError(
                f"{len(unsafe)} row(s) have unsafe path segments — the legacy app did no "
                "filename sanitisation, and these would escape --dest; nothing was fetched:\n  "
                + "\n  ".join(details)
            )

    def _scan(
        self, dest: Path, legacy_ids: set[str], *, sweep: bool
    ) -> tuple[set[tuple[str, str]], int]:
        """One `scandir` per villa folder, not one `is_file()` per row.

        Returns the trustworthy existing files and the stale `.part` count.
        """
        existing: set[tuple[str, str]] = set()
        stale = 0
        for legacy_id in sorted(legacy_ids):
            try:
                entries = list(os.scandir(dest / legacy_id))
            except FileNotFoundError:
                continue
            for entry in entries:
                # Dotfiles (.DS_Store, our own lock/report) are never images.
                if entry.name.startswith(".") or not entry.is_file():
                    continue
                if entry.name.endswith(PART_SUFFIX):
                    stale += 1
                    if sweep:
                        _discard(Path(entry.path))
                    continue
                # A zero-byte or truncated artefact is not evidence of success.
                if entry.stat().st_size >= MIN_IMAGE_BYTES:
                    existing.add((legacy_id, entry.name))
        return existing, stale

    def _check_free_space(self, dest: Path, pending: int) -> None:
        needed = int(pending * MEAN_IMAGE_BYTES * DISK_SAFETY_FACTOR)
        free = shutil.disk_usage(dest).free
        if free < needed:
            raise CommandError(
                f"not enough free space at {dest}: {pending} file(s) need about "
                f"{needed / 1e9:.1f} GB (mean {MEAN_IMAGE_BYTES / 1e3:.0f} KB plus margin) "
                f"but only {free / 1e9:.1f} GB is free"
            )

    # -- the run -----------------------------------------------------------

    def _fetch(
        self,
        *,
        dest: Path,
        base_url: str,
        concurrency: int,
        delay: float,
        retries: int,
        limit: int,
        dry_run: bool,
    ) -> None:
        rows = legacy_image_rows()
        # Nothing past this point touches the ORM, and a 2.4-hour idle
        # connection to Render's external host would be dropped. Skipped inside
        # a transaction (i.e. under test), where closing rolls back the caller.
        if not connection.in_atomic_block:
            connection.close()
        self._abort_on_data_hazards(rows)

        no_legacy_id: list[int] = []
        addressable: list[tuple[LegacyRow, str, str]] = []
        for row in rows:
            legacy_id = row.legacy_id
            if not legacy_id:
                no_legacy_id.append(row.pk)
                continue
            addressable.append((row, legacy_id, filename_for(row.key)))

        existing, stale = self._scan(
            dest, {legacy_id for _row, legacy_id, _f in addressable}, sweep=not dry_run
        )

        skipped = 0
        tasks: list[_Task] = []
        for row, legacy_id, filename in addressable:
            if (legacy_id, filename) in existing:
                skipped += 1
                continue
            target = dest / legacy_id / filename
            # Belt and braces: the segments were validated, now check the join.
            if not target.resolve().is_relative_to(dest):
                raise CommandError(f"refusing to write outside {dest}: {target}")
            url = f"{base_url}/{quote(legacy_id, safe='')}/{quote(filename, safe='')}"
            tasks.append(_Task(row.pk, url, target))
        if limit:
            tasks = tasks[:limit]

        self._check_free_space(dest, len(tasks))

        if dry_run:
            self.stdout.write("DRY RUN — nothing was downloaded")
            self._report(
                counts=Counter({_DOWNLOADED: len(tasks)}),
                skipped=skipped,
                stale=stale,
                no_legacy_id=no_legacy_id,
                total=len(rows),
                details={},
            )
            return

        counts: Counter[str] = Counter()
        details: dict[str, list[str]] = defaultdict(list)
        try:
            fatal, interrupted = self._run_pool(
                tasks=tasks,
                concurrency=concurrency,
                delay=delay,
                retries=retries,
                counts=counts,
                details=details,
            )
        finally:
            self._write_report(dest, details)

        self._report(
            counts=counts,
            skipped=skipped,
            stale=stale,
            no_legacy_id=no_legacy_id,
            total=len(rows),
            details=details,
        )
        report = dest / REPORT_NAME
        if fatal:
            raise CommandError(f"{fatal} — re-run to resume; see {report}")
        if interrupted:
            raise CommandError(f"interrupted — re-run to resume; see {report}")
        unfinished = sum(counts[bucket] for bucket in (_REDIRECT, _REJECTED, _FAILED))
        if unfinished:
            raise CommandError(
                f"{unfinished} file(s) failed, were rejected or redirected — re-run to retry "
                f"them (the skip diff is the retry list); see {report}"
            )

    def _run_pool(
        self,
        *,
        tasks: list[_Task],
        concurrency: int,
        delay: float,
        retries: int,
        counts: Counter[str],
        details: dict[str, list[str]],
    ) -> tuple[str, bool]:
        """Drive the pool. Returns `(fatal_message, interrupted)`.

        All aggregation and all output happen here, in the main thread.
        """
        stop = threading.Event()
        fatal = ""
        interrupted = False
        attempted = 0
        consecutive = 0
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=_HTTP_TIMEOUT,
            # A real file answers 200 directly, so a redirect means a WAF or
            # maintenance rule appeared and we want to see it, not follow it
            # into a 200-with-HTML. Diverges from ical_ingest deliberately.
            follow_redirects=False,
            limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
        )
        executor = ThreadPoolExecutor(max_workers=concurrency)
        queued = iter(tasks)

        def submit_next() -> Future[_Result] | None:
            task = next(queued, None)
            if task is None:
                return None
            return executor.submit(
                _fetch_one, client, task, delay=delay, retries=retries, stop=stop
            )

        try:
            pending: set[Future[_Result]] = set()
            for _slot in range(concurrency * IN_FLIGHT_PER_WORKER):
                future = submit_next()
                if future is None:
                    break
                pending.add(future)
            try:
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        try:
                            result = future.result()
                        except Exception as exc:  # one worker bug must not lose two hours of work
                            result = _Result(0, _FAILED, f"unexpected {type(exc).__name__}: {exc}")
                        if result.bucket == _STOPPED:
                            continue
                        counts[result.bucket] += 1
                        attempted += 1
                        if result.detail:
                            details[result.bucket].append(result.detail)
                        if result.bucket in (_DOWNLOADED, _MISSING):
                            consecutive = 0
                        else:
                            consecutive += 1
                            logger.warning(
                                "legacy_image.fetch_failed",
                                image_pk=result.pk,
                                bucket=result.bucket,
                                detail=result.detail,
                            )
                        if attempted % PROGRESS_EVERY == 0:
                            self.stdout.write(f"fetched {attempted}/{len(tasks)}")
                        fatal = (
                            fatal
                            or result.fatal
                            or self._fatal_check(
                                consecutive=consecutive,
                                attempted=attempted,
                                missing=counts[_MISSING],
                            )
                        )
                    if fatal:
                        stop.set()
                        break
                    for _slot in range(len(done)):
                        future = submit_next()
                        if future is None:
                            break
                        pending.add(future)
            except KeyboardInterrupt:
                interrupted = True
                stop.set()
        finally:
            # wait=False + cancel_futures: the queue is dropped and the few
            # in-flight workers unwind on their own. A `with` block would
            # instead wait for all ~18k queued tasks, which is what makes a
            # naive Ctrl-C ignore the interrupt entirely.
            executor.shutdown(wait=False, cancel_futures=True)
            client.close()
        return fatal, interrupted

    def _fatal_check(self, *, consecutive: int, attempted: int, missing: int) -> str:
        if consecutive >= CONSECUTIVE_FAILURE_ABORT:
            return (
                f"stopped after {consecutive} consecutive failures — the source may be down, "
                "in maintenance, or blocking us"
            )
        if attempted >= MISSING_ABORT_FLOOR and missing / attempted > MISSING_ABORT_RATIO:
            return (
                f"{missing} of {attempted} files are missing at source "
                f"({missing / attempted:.0%}, over the {MISSING_ABORT_RATIO:.0%} threshold) — "
                "the source tree may have been pruned; check the legacy host"
            )
        return ""

    # -- output ------------------------------------------------------------

    def _write_report(self, dest: Path, details: dict[str, list[str]]) -> None:
        """Every problem URL, uncapped. A diagnostic, not an input.

        Overwritten rather than appended: an appended list is a lie on re-run.
        Written even on interrupt, so a Ctrl-C still leaves a record — minus any
        worker still in flight, which the next run's skip diff covers anyway.
        """
        lines: list[str] = []
        for bucket in _PROBLEM_BUCKETS:
            for detail in details.get(bucket, []):
                lines.append(f"{bucket}\t{detail}")
        (dest / REPORT_NAME).write_text("\n".join(lines) + "\n" if lines else "")

    def _report(
        self,
        *,
        counts: Counter[str],
        skipped: int,
        stale: int,
        no_legacy_id: list[int],
        total: int,
        details: dict[str, list[str]],
    ) -> None:
        table_rows = [
            (_DOWNLOADED, counts[_DOWNLOADED]),
            (_SKIPPED, skipped),
            (_MISSING, counts[_MISSING]),
            (_REDIRECT, counts[_REDIRECT]),
            (_REJECTED, counts[_REJECTED]),
            (_FAILED, counts[_FAILED]),
            (_NO_LEGACY_ID, len(no_legacy_id)),
            (_SWEPT, stale),
            ("total", total),
        ]
        self.stdout.write(render_table(("bucket", "count"), table_rows))
        for bucket in _PROBLEM_BUCKETS:
            entries = details.get(bucket, [])
            if not entries:
                continue
            self.stdout.write(f"\n{bucket} (first {DETAIL_CAP}):")
            for entry in entries[:DETAIL_CAP]:
                self.stdout.write(f"  {entry}")
        if no_legacy_id:
            self.stdout.write(f"\n{_NO_LEGACY_ID} (image pks, first {DETAIL_CAP}):")
            self.stdout.write("  " + ", ".join(str(pk) for pk in no_legacy_id[:DETAIL_CAP]))
