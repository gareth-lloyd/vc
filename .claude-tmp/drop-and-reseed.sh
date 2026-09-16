#!/usr/bin/env bash
# Drop a legacy database on the `res-db` container and reseed it from a dump.
#
#   .claude-tmp/drop-and-reseed.sh <dump-file> [db-name]
#
# <dump-file> is either:
#   *.bak  a SQL Server backup — RESTORE … WITH MOVE (the shape every
#          production dump has arrived in since 2026-08, e.g.
#          `ResSystem/NewResSystem_2026Aug13.bak`);
#   *.sql  a T-SQL script — the older `live-db-YYYY-MM-DD.sql` convention,
#          UTF-16 LE, transcoded to UTF-8 on the fly. Kept for old dumps only;
#          that schema is no longer a supported load source (CUTOVER.md §0).
#
# [db-name] is the database to (re)create — default `ResProd`, the name
# `LEGACY_DATABASE_URL` points at for the cutover. The database is DROPPED, so
# name it deliberately. Nothing destructive happens until the dump has been
# validated: an unreadable or non-backup file fails before the DROP, leaving
# the existing database untouched.
#
# The dump may live anywhere: a .bak is copied into the container and a .sql is
# mounted from its own directory, so this runs from the main checkout or any
# worktree (`ResSystem/` is gitignored and exists only in the main checkout).
set -euo pipefail

DUMP=${1:-}
DB=${2:-ResProd}

if [[ -z "$DUMP" || "$DUMP" == "-h" || "$DUMP" == "--help" ]]; then
  # Print the header block above, minus the shebang, stopping at `set -e`.
  sed -n '2,/^set -/p' "$0" | sed '$d; s/^# \{0,1\}//'
  exit 1
fi
[[ -f "$DUMP" ]] || { echo "No such dump file: $DUMP" >&2; exit 1; }

DUMP_DIR=$(cd "$(dirname "$DUMP")" && pwd)
DUMP_FILE=$(basename "$DUMP")
DUMP_EXT=${DUMP_FILE##*.}

# Reject an unsupported dump type HERE, while the target database is still
# intact — not after the DROP.
case "$DUMP_EXT" in
  bak | sql) ;;
  *)
    echo "Unsupported dump type '.$DUMP_EXT' — expected .bak or .sql" >&2
    exit 1
    ;;
esac

SA_PW=${SA_PASSWORD:-'ResLocal!2026'}
TOOLS_IMG=${TOOLS_IMG:-mcr.microsoft.com/mssql-tools}
NETWORK=${RES_NETWORK:-ressystem_default}
CONTAINER=${RES_CONTAINER:-res-db}
SERVER=${RES_SERVER:-res-db,1433}

# sqlcmd runs in the tools image (Azure SQL Edge ships none) and reaches the
# server over the compose network. Notes:
#   -b            exit non-zero on a T-SQL error. WITHOUT it sqlcmd returns 0
#                 even when RESTORE fails, `set -e` never trips, and the script
#                 cheerfully reports success over a database that is not there.
#   SQLCMDPASSWORD  keeps the password out of the host's process list and out
#                 of `docker inspect`; sqlcmd reads it natively, so no -P.
# Args are passed as argv, never re-parsed by a shell, so query text needs no
# quote gymnastics.
sqlcmd() {
  docker run --rm --platform linux/amd64 --network "$NETWORK" \
    -e SQLCMDPASSWORD="$SA_PW" \
    "$TOOLS_IMG" /opt/mssql-tools/bin/sqlcmd \
    -b -S "$SERVER" -U sa "$@"
}

# As above, but with the dump's directory mounted — only the .sql path needs
# it, because sqlcmd reads a script CLIENT-side.
sqlcmd_with_dump() {
  docker run --rm --platform linux/amd64 --network "$NETWORK" \
    -v "$DUMP_DIR:/seed:ro" -e SQLCMDPASSWORD="$SA_PW" \
    "$TOOLS_IMG" bash -c "$1"
}

echo "Reseeding [$DB] on $CONTAINER from $DUMP_DIR/$DUMP_FILE"

if [[ "$DUMP_EXT" == bak ]]; then
  # RESTORE reads SERVER-side, so the backup has to be inside the container.
  # Copying into the data volume works wherever the dump lives on the host; the
  # compose file's `./Database:/seed:ro` mount only covers that one directory.
  REMOTE=/var/opt/mssql/backup/$DUMP_FILE
  echo "==> Copying backup into $CONTAINER (this is the slow step)…"
  docker exec "$CONTAINER" mkdir -p /var/opt/mssql/backup
  docker cp "$DUMP_DIR/$DUMP_FILE" "$CONTAINER:$REMOTE"
  # `docker cp` preserves the host's mode and numeric owner; SQL Server runs as
  # an unprivileged user (uid 10001), so a 0600 dump would restore as
  # "Operating system error 5 (Access denied)". Needs -u 0: the copy belongs to
  # the host user, so `mssql` cannot chmod it. Best-effort — if it fails the
  # FILELISTONLY below reports the unreadable file, and does so BEFORE the DROP.
  docker exec -u 0 "$CONTAINER" chmod a+r "$REMOTE" 2>/dev/null ||
    echo "    (could not chmod the copy — relying on its own permissions)"

  echo "==> Reading the backup's file list…"
  # The backup carries the ORIGINAL server's file paths, so every logical file
  # is MOVEd onto this container's data dir under the TARGET database's name —
  # without that, restoring under a new name collides with the files of the
  # database the backup came from. `-w 1024` because FILELISTONLY returns ~20
  # columns and sqlcmd wraps at 80 by default, which would split each row into
  # fragments this loop would then misread.
  MOVES=""
  n=0
  while IFS='|' read -r logical _ ftype _; do
    [[ -n "${logical// /}" ]] || continue
    case "$ftype" in
      D) ext=mdf ;;
      L) ext=ldf ;;
      *) continue ;;
    esac
    n=$((n + 1))
    MOVES+=", MOVE '$logical' TO '/var/opt/mssql/data/${DB}_${n}.${ext}'"
  done < <(sqlcmd -h -1 -W -w 1024 -s '|' \
    -Q "SET NOCOUNT ON; RESTORE FILELISTONLY FROM DISK = '$REMOTE'")
  [[ -n "$MOVES" ]] || {
    echo "RESTORE FILELISTONLY returned no files — is $DUMP_FILE a backup?" >&2
    exit 1
  }
  echo "    $n file(s) to move."

  # Everything above is non-destructive. Only now is the target at risk.
  echo "==> Dropping [$DB] (if present)…"
  sqlcmd -Q "IF DB_ID('$DB') IS NOT NULL BEGIN ALTER DATABASE [$DB] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [$DB]; END"

  echo "==> Restoring [$DB] (2-5 min)…"
  sqlcmd -Q "RESTORE DATABASE [$DB] FROM DISK = '$REMOTE' WITH REPLACE$MOVES"
  # Only reached when the RESTORE really succeeded (-b above); on failure the
  # copy is deliberately left in place for debugging.
  docker exec "$CONTAINER" rm -f "$REMOTE"
else
  echo "==> Dropping [$DB] (if present)…"
  sqlcmd -Q "IF DB_ID('$DB') IS NOT NULL BEGIN ALTER DATABASE [$DB] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [$DB]; END"

  echo "==> Creating fresh [$DB]…"
  sqlcmd -Q "CREATE DATABASE [$DB]"

  echo "==> Decoding UTF-16 dump → UTF-8 and running seed (1-5 min)…"
  # Only transcode when the file actually carries a UTF-16 LE BOM; a UTF-8 dump
  # fed through `iconv -f UTF-16LE` comes out as mojibake.
  sqlcmd_with_dump "set -euo pipefail
    SRC=/seed/$DUMP_FILE
    if [ \"\$(head -c 2 \"\$SRC\" | od -An -tx1 | tr -d ' ')\" = fffe ]; then
      iconv -f UTF-16LE -t UTF-8 \"\$SRC\" > /tmp/seed.utf8.sql
      SRC=/tmp/seed.utf8.sql
    fi
    /opt/mssql-tools/bin/sqlcmd -b -S '$SERVER' -U sa -d '$DB' -i \"\$SRC\""
fi

echo "==> Sanity check — VillaMaster row count (the property table every"
echo "    loader hangs off; CUTOVER.md §3 says what to expect):"
sqlcmd -d "$DB" -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM VillaMaster"

echo "Done. Point LEGACY_DATABASE_URL at /$DB."
