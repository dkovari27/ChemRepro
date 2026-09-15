#!/usr/bin/env python3
"""
Backup Railway PostgreSQL to Google Drive.

Local:   python scripts/backup_to_gdrive.py
Railway: scheduled cron — same command, env vars injected by Railway.

Required env vars on Railway:
  DATABASE_URL      — set automatically by Railway PostgreSQL
  GDRIVE_SA_JSON    — paste the entire service account JSON as a single-line string
"""
import gzip
import io
import json
import os
import subprocess
from datetime import datetime, timezone

import psycopg2
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

FOLDER_ID = "1gpDAm0jTR8LnnNyCKoaYNRqNSrcvffHI"
KEEP_N = 14

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_drive_service():
    token_env = os.environ.get("GDRIVE_TOKEN_JSON")
    if token_env:
        info = json.loads(token_env)
    else:
        token_path = os.path.join(os.path.dirname(__file__), "..", "Backup", "token.json")
        with open(token_path) as f:
            info = json.load(f)

    creds = Credentials(
        token=info.get("token"),
        refresh_token=info.get("refresh_token"),
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info.get("client_id"),
        client_secret=info.get("client_secret"),
        scopes=info.get("scopes"),
    )
    if not creds.valid:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)

# ── Dump ──────────────────────────────────────────────────────────────────────

def _python_dump(db_url: str) -> bytes:
    """psycopg2-based fallback when pg_dump binary is not available."""
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    out = io.StringIO()
    out.write(f"-- ChemRepro Python dump {datetime.now(timezone.utc).isoformat()}\n\n")

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]

    for table in tables:
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        if not rows:
            continue
        cols = [d[0] for d in cur.description]
        out.write(f"\n-- {table} ({len(rows)} rows)\n")
        for row in rows:
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, bool):
                    vals.append("TRUE" if v else "FALSE")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    vals.append("'" + str(v).replace("'", "''") + "'")
            out.write(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(vals)});\n")

    cur.close()
    conn.close()
    return out.getvalue().encode("utf-8")

def _find_pg_dump() -> str:
    """Return the highest-version pg_dump installed, or plain 'pg_dump' as fallback."""
    import glob
    candidates = sorted(
        glob.glob("/usr/lib/postgresql/*/bin/pg_dump"),
        key=lambda p: int(p.split("/")[4]),
        reverse=True,
    )
    return candidates[0] if candidates else "pg_dump"


def dump_database(db_url: str) -> bytes:
    pg_dump_bin = _find_pg_dump()
    try:
        result = subprocess.run(
            [pg_dump_bin, "--no-owner", "--no-acl", db_url],
            capture_output=True, check=True, timeout=120
        )
        print(f"  Used pg_dump: {pg_dump_bin}")
        return result.stdout
    except FileNotFoundError:
        print(f"  pg_dump not found ({pg_dump_bin}), using Python fallback.")
        return _python_dump(db_url)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace").strip()
        first_line = err.splitlines()[0] if err else "unknown error"
        print(f"  pg_dump failed ({first_line}), using Python fallback.")
        return _python_dump(db_url)

# ── Drive ─────────────────────────────────────────────────────────────────────

def upload(service, filename: str, data: bytes) -> dict:
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/gzip", resumable=False)
    return service.files().create(
        body={"name": filename, "parents": [FOLDER_ID]},
        media_body=media,
        fields="id,name,size"
    ).execute()

def prune(service) -> int:
    res = service.files().list(
        q=f"'{FOLDER_ID}' in parents and name contains 'chemrepro_backup_' and trashed=false",
        fields="files(id,name,createdTime)",
        orderBy="createdTime"
    ).execute()
    old = res.get("files", [])[:-KEEP_N]
    for f in old:
        service.files().delete(fileId=f["id"]).execute()
        print(f"  Pruned: {f['name']}")
    return len(old)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    print("[1/4] Authenticating with Google Drive...")
    service = get_drive_service()
    print("  OK")

    print("[2/4] Dumping database...")
    sql_bytes = dump_database(db_url)
    print(f"  {len(sql_bytes):,} bytes uncompressed")

    print("[3/4] Compressing...")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(sql_bytes)
    compressed = buf.getvalue()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    filename = f"chemrepro_backup_{stamp}.sql.gz"
    print(f"  {len(compressed):,} bytes -> {filename}")

    print("[4/4] Uploading to Google Drive...")
    uploaded = upload(service, filename, compressed)
    print(f"  Uploaded: {uploaded['name']} (size={uploaded.get('size', '?')} bytes)")

    pruned = prune(service)
    print(f"  Pruned {pruned} old backup(s), keeping last {KEEP_N}.")

    print("\nBackup complete.")

if __name__ == "__main__":
    main()
