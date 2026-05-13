#!/usr/bin/env bash
# One-off: drop NewResSystem and reseed from live-db-24-apr.sql.
set -euo pipefail

cd "$(dirname "$0")/../ResSystem"

SA_PW='ResLocal!2026'
TOOLS_IMG=mcr.microsoft.com/mssql-tools
NETWORK=ressystem_default

run_sqlcmd() {
  docker run --rm --platform linux/amd64 --network "$NETWORK" \
    -v "$(pwd)/Database:/seed:ro" \
    -e SA_PASSWORD="$SA_PW" \
    "$TOOLS_IMG" bash -c "$1"
}

echo "[1/4] Dropping NewResSystem (if present)…"
run_sqlcmd '/opt/mssql-tools/bin/sqlcmd -S res-db,1433 -U sa -P "$SA_PASSWORD" -Q "IF DB_ID('"'"'NewResSystem'"'"') IS NOT NULL BEGIN ALTER DATABASE [NewResSystem] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [NewResSystem]; END"'

echo "[2/4] Creating fresh NewResSystem…"
run_sqlcmd '/opt/mssql-tools/bin/sqlcmd -S res-db,1433 -U sa -P "$SA_PASSWORD" -Q "CREATE DATABASE [NewResSystem]"'

echo "[3/4] Decoding UTF-16 dump → UTF-8 and running seed (1-5 min)…"
run_sqlcmd 'iconv -f UTF-16LE -t UTF-8 /seed/Scripts/live-db-24-apr.sql > /tmp/seed.utf8.sql && /opt/mssql-tools/bin/sqlcmd -S res-db,1433 -U sa -P "$SA_PASSWORD" -d NewResSystem -i /tmp/seed.utf8.sql'

echo "[4/4] Sanity check — VillaCountry row count:"
run_sqlcmd '/opt/mssql-tools/bin/sqlcmd -S res-db,1433 -U sa -P "$SA_PASSWORD" -d NewResSystem -h -1 -W -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM VillaCountry"'

echo "Done."
