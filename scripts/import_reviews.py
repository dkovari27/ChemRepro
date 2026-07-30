#!/usr/bin/env python3
"""
Bulk-import reviews from a JSON file into ChemRepro.

Usage:
  # Real user, dry run first:
  python scripts/import_reviews.py reviews.json --orcid 0009-0007-7610-9001 --dry-run

  # AI scraper profile (creates profile automatically if missing):
  python scripts/import_reviews.py reviews.json --ai-name OrgSyn --dry-run
  python scripts/import_reviews.py reviews.json --ai-name OrgSyn

  # Railway PostgreSQL:
  set DATABASE_URL=postgresql://postgres:PASSWORD@acela.proxy.rlwy.net:17700/railway
  python scripts/import_reviews.py reviews.json --ai-name OrgSyn

Required packages: httpx sqlalchemy psycopg (for PostgreSQL only)
"""
import argparse
import base64
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.image import UploadedImage
from app.models.paper import Paper
from app.models.rating import Rating
from app.models.user import User

AI_CAREER_STAGE = "Data curation agent"

# Confidence thresholds — records below either value are rejected at import
_MIN_AI_CONFIDENCE = 0.75
_MIN_EXTRACTION_CONFIDENCE = 0.75


def make_session(db_url: str):
    url = db_url
    if url.startswith("sqlite:///./") or url == "sqlite:///./chemrepro.db":
        url = f"sqlite:///{PROJECT_ROOT / 'chemrepro.db'}"
    elif "postgres" in url:
        url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}
    engine = create_engine(url, connect_args=connect_args)
    return sessionmaker(bind=engine)()


def ensure_ai_user(db, orcid_id: str, display_name: str, nickname: str | None, dry_run: bool) -> bool:
    """Create or update AI reviewer profile. Returns True if user exists after this call.
    nickname is only updated when explicitly provided from the JSONL (not None)."""
    user = db.get(User, orcid_id)
    if user:
        print(f"  Profile {orcid_id!r} already exists (name={user.name!r})")
        if nickname is not None and not dry_run and user.nickname != nickname:
            user.nickname = nickname
            db.commit()
            print(f"  Updated nickname to {nickname!r}")
        return True
    creation_nickname = nickname or display_name
    print(f"  Profile {orcid_id!r} not found, creating...")
    if dry_run:
        print(f"  DRY RUN: would create profile name={display_name!r}, nickname={creation_nickname!r}, career_stage={AI_CAREER_STAGE!r}")
        return True
    db.add(User(
        orcid_id=orcid_id,
        name=display_name,
        nickname=creation_nickname,
        career_stage=AI_CAREER_STAGE,
        career_stage_set=True,
        pledge_accepted=True,
        is_demo=False,
    ))
    db.commit()
    print(f"  Created: {display_name!r} (orcid_id={orcid_id!r}, nickname={creation_nickname!r}, career_stage={AI_CAREER_STAGE!r})")
    return True


def fetch_crossref(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{doi}"
    try:
        r = httpx.get(url, headers={"User-Agent": "ChemRepro/1.0 (mailto:chemrepro@gmail.com)"}, timeout=12)
    except httpx.RequestError as exc:
        print(f"         CrossRef request failed: {exc}")
        return None
    if r.status_code != 200:
        print(f"         CrossRef returned HTTP {r.status_code}")
        return None
    data = r.json().get("message", {})

    title_parts = data.get("title", [])
    title = re.sub(r"<[^>]+>", "", title_parts[0] if title_parts else "").strip() or "Unknown title"

    authors = json.dumps([
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in data.get("author", []) if a.get("family")
    ])

    container = data.get("container-title", [])
    journal = container[0] if container else None

    published = data.get("published-print") or data.get("published-online") or {}
    parts = published.get("date-parts", [[]])
    year = parts[0][0] if parts and parts[0] else None

    abstract_raw = data.get("abstract", "")
    abstract = re.sub(r"<[^>]+>", "", abstract_raw).strip() or None
    if abstract:
        abstract = re.sub(r"^Abstract\s*", "", abstract, flags=re.IGNORECASE).strip() or None

    return {"doi": doi, "title": title, "authors": authors, "journal": journal, "year": year, "abstract": abstract}


def import_images(db, image_list: list, uploader_orcid_id: str, dry_run: bool) -> str:
    """
    Insert base64-encoded images into uploaded_images table.
    Returns a string of markdown image tags to append to the observation text.
    Each entry in image_list must have a 'uri' key (data URI or bare base64).
    """
    if not image_list:
        return ""
    tags: list[str] = []
    for img in image_list:
        uri = img.get("uri", "")
        if not uri:
            continue
        if uri.startswith("data:"):
            header, _, b64 = uri.partition(",")
            mime = re.search(r"data:([^;]+)", header)
            mime_type = mime.group(1) if mime else "image/jpeg"
        else:
            b64 = uri
            mime_type = "image/jpeg"
        try:
            data = base64.b64decode(b64)
        except Exception as exc:
            print(f"         Image decode error: {exc} — skipped")
            continue
        if dry_run:
            print(f"         DRY RUN: would insert image ({len(data):,} bytes, {mime_type})")
            tags.append("![](/images/dry-run-uuid)")
            continue
        uploaded = UploadedImage(
            uploader_orcid_id=uploader_orcid_id,
            mime_type=mime_type,
            data=data,
        )
        db.add(uploaded)
        db.flush()
        tags.append(f"![](/images/{uploaded.uuid})")
        print(f"         Image inserted: /images/{uploaded.uuid} ({len(data):,} bytes)")
    return "\n".join(tags)


def _rejected_path(input_path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return input_path.parent / f"rejected_{ts}.jsonl"


def _write_rejected(path: Path, row: dict, reason: str) -> None:
    """Append one rejected row to the log, creating the file on first call."""
    out = dict(row)
    out["_rejection_reason"] = reason
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")


VALID_STARS = {1, 2, 3, 4, 5}
# nd_failure_context when nd_star=null (new schema: extension_failed | inconclusive)
NULL_STAR_CONTEXTS = {"extension_failed", "inconclusive"}
# nd_failure_context when nd_star=1 (old schema, kept for back-compat; new schema uses null)
LEGACY_FAIL_CONTEXTS = {"original_tested", "extension_only"}
STAR_LABEL = {
    1: "did not work",
    2: "partial",
    3: "reproduced",
    4: "minor extension",
    5: "major extension",
    None: "inconclusive / extension failed",
}


def main():
    parser = argparse.ArgumentParser(description="Bulk-import ChemRepro reviews from JSON")
    parser.add_argument("file", help="Path to JSON reviews file")

    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--orcid", help="Real reviewer ORCID (e.g. 0009-0007-7610-9001)")
    id_group.add_argument("--ai-name", metavar="SCRAPER",
                          help="AI scraper name, e.g. OrgSyn: sets orcid_id=AI-OrgSyn, creates profile if missing")

    parser.add_argument("--career-stage", help="Override career_stage_snapshot for all rows")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    if args.ai_name:
        orcid_id = f"AI-{args.ai_name}"
        display_name = f"AI-{args.ai_name}"
        default_career = AI_CAREER_STAGE
    else:
        orcid_id = args.orcid
        display_name = None
        default_career = None

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./chemrepro.db")
    db = make_session(db_url)

    input_path = Path(args.file)
    rejected_path = _rejected_path(input_path)

    print(f"\n{'='*55}")
    print(f"  Reviewer : {orcid_id}")
    print(f"  DB       : {db_url[:65]}{'...' if len(db_url) > 65 else ''}")
    print(f"  Mode     : {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*55}\n")

    if input_path.suffix == ".jsonl":
        data = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("ERROR: JSON file must be a list of review objects.")
        sys.exit(1)

    print(f"Importing {len(data)} review(s)...\n")
    ok = skip = fail = held = 0
    inserted_ids: list[int] = []

    for i, row in enumerate(data, 1):
        # Task 1: field name is target_doi (not doi); accept legacy "doi" as fallback
        doi = (row.get("target_doi") or row.get("doi") or "").strip()
        if not doi:
            print(f"  [{i:>3}] SKIP: missing target_doi field")
            skip += 1
            continue

        # Task 2: gate on _needs_clarification
        if row.get("_needs_clarification"):
            print(f"  [{i:>3}] {doi}: HELD: _needs_clarification=true — written to rejected log")
            _write_rejected(rejected_path, row, "_needs_clarification: awaiting human review")
            held += 1
            continue

        # Task 3: enforce confidence thresholds
        ai_conf = row.get("ai_confidence")
        ext_conf = row.get("extraction_confidence")
        if ai_conf is not None and ai_conf < _MIN_AI_CONFIDENCE:
            reason = f"ai_confidence={ai_conf:.3f} below {_MIN_AI_CONFIDENCE}"
            print(f"  [{i:>3}] {doi}: REJECTED: {reason}")
            _write_rejected(rejected_path, row, reason)
            fail += 1
            continue
        if ext_conf is not None and ext_conf < _MIN_EXTRACTION_CONFIDENCE:
            reason = f"extraction_confidence={ext_conf:.3f} below {_MIN_EXTRACTION_CONFIDENCE}"
            print(f"  [{i:>3}] {doi}: REJECTED: {reason}")
            _write_rejected(rejected_path, row, reason)
            fail += 1
            continue

        nd_star = row.get("nd_star")  # None = null in JSON
        if nd_star is not None and nd_star not in VALID_STARS:
            reason = f"nd_star must be 1-5 or null, got {nd_star!r}"
            print(f"  [{i:>3}] {doi}: FAIL: {reason}")
            _write_rejected(rejected_path, row, reason)
            fail += 1
            continue

        ctx = row.get("nd_failure_context") or None
        if nd_star is None:
            if ctx not in NULL_STAR_CONTEXTS:
                reason = f"nd_failure_context must be 'extension_failed' or 'inconclusive' when nd_star is null, got {ctx!r}"
                print(f"  [{i:>3}] {doi}: FAIL: {reason}")
                _write_rejected(rejected_path, row, reason)
                fail += 1
                continue
        elif nd_star == 1:
            if ctx is not None and ctx not in LEGACY_FAIL_CONTEXTS:
                reason = f"nd_failure_context for 1-star must be 'original_tested', 'extension_only', or null, got {ctx!r}"
                print(f"  [{i:>3}] {doi}: FAIL: {reason}")
                _write_rejected(rejected_path, row, reason)
                fail += 1
                continue
        else:
            ctx = None

        # Task 5: read reviewer_nickname from the JSONL record
        record_nickname = (row.get("reviewer_nickname") or "").strip() or None

        career = args.career_stage or row.get("career_stage_snapshot") or default_career
        observation = ((row.get("reproducibility_observation") or "").strip()) or None
        image_list = row.get("images") or []

        # Task 6: scraper enrichment fields
        citing_author = (row.get("citing_author") or "").strip() or None
        is_multi_target = bool(row.get("is_multi_target", False))

        # Task 7: provenance fields
        source_doi = (row.get("source_doi") or "").strip() or None
        source_url = (row.get("source_url") or "").strip() or None

        # Ensure AI user profile exists.
        # reviewer_nickname from JSONL updates the stored nickname only when explicitly present;
        # when absent (None) the existing nickname is left untouched.
        if args.ai_name:
            ensure_ai_user(db, orcid_id, display_name, record_nickname, args.dry_run)

        paper = db.get(Paper, doi)
        if paper is None:
            print(f"  [{i:>3}] {doi}: not in DB, fetching from CrossRef...")
            meta = fetch_crossref(doi)
            if meta is None:
                print(f"  [{i:>3}] {doi}: FAIL: CrossRef lookup failed")
                _write_rejected(rejected_path, row, "CrossRef lookup failed")
                fail += 1
                continue
            print(f"         title: {meta['title'][:75]}")
            if not args.dry_run:
                paper = Paper(**meta)
                db.add(paper)
                db.flush()
        else:
            print(f"  [{i:>3}] {doi}: {paper.title[:65]!r}")

        existing = db.query(Rating).filter(
            Rating.doi == doi,
            Rating.orcid_id == orcid_id,
            Rating.scoring_mode == "new_design",
        ).first()
        if existing:
            print(f"         SKIP: already reviewed (rating id={existing.id})")
            skip += 1
            continue

        star_disp = "null" if nd_star is None else str(nd_star)
        print(f"         star={star_disp} ({STAR_LABEL.get(nd_star, '?')}){f', ctx={ctx}' if ctx else ''}")
        if citing_author:
            print(f"         citing_author={citing_author!r}")
        if is_multi_target:
            print(f"         is_multi_target=True")
        if source_doi:
            print(f"         source_doi={source_doi}")
        if image_list:
            print(f"         images: {len(image_list)} attached")

        img_tags = import_images(db, image_list, orcid_id, args.dry_run)
        if img_tags:
            observation = (observation or "") + ("\n\n" if observation else "") + img_tags

        if not args.dry_run:
            rating = Rating(
                doi=doi,
                orcid_id=orcid_id,
                scoring_mode="new_design",
                nd_star=nd_star,
                nd_failure_context=ctx,
                reproducibility_observation=observation,
                career_stage_snapshot=career,
                citing_author=citing_author,
                is_multi_target=is_multi_target,
                source_doi=source_doi,
                source_url=source_url,
                is_demo=False,
            )
            db.add(rating)
            db.commit()
            inserted_ids.append(rating.id)
            print(f"         INSERTED id={rating.id}")
        else:
            print(f"         would insert")
        ok += 1

    if rejected_path.exists():
        print(f"\n  Rejected log: {rejected_path}")

    print(f"\n{'='*55}")
    print(f"  Inserted : {ok}")
    print(f"  Skipped  : {skip}")
    print(f"  Held     : {held}  (needs clarification — see rejected log)")
    print(f"  Rejected : {fail}  (confidence / validation failures — see rejected log)")
    if args.dry_run:
        print("  (dry run: no changes made)")
    print()

    if inserted_ids and not args.dry_run:
        print("Running citation resolver on newly imported reviews...")
        try:
            from scripts.resolve_citations import resolve_ratings
            resolve_ratings(db_url=db_url, rating_ids=inserted_ids)
        except Exception as exc:
            print(f"  Citation resolver failed (non-fatal): {exc}")


if __name__ == "__main__":
    main()
