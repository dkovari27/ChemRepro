#!/usr/bin/env python3
"""
Upload base64 images from a JSON import file and attach them to existing ratings
by appending ![image](/images/{uuid}) to reproducibility_observation.

Only processes entries that have an "images" field. Skips ratings whose observation
already contains /images/ (idempotent).

Usage:
  set DATABASE_URL=postgresql://...
  python scripts/patch_import_images.py path/to/import.json --ai-name JACSAU --dry-run
  python scripts/patch_import_images.py path/to/import.json --ai-name JACSAU
"""
import argparse
import base64
import json
import os
import re
import sys
import uuid as uuid_lib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.image import UploadedImage
from app.models.rating import Rating


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Path to JSON reviews file")
    parser.add_argument("--ai-name", required=True, metavar="NAME",
                        help="AI reviewer name, e.g. JACSAU → orcid_id=AI-JACSAU")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./chemrepro.db")
    db_url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", db_url)
    engine = create_engine(db_url)
    db = sessionmaker(bind=engine)()

    orcid_id = f"AI-{args.ai_name}"
    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n{'='*55}\n  Reviewer : {orcid_id}\n  DB       : {db_url[:65]}\n  Mode     : {mode}\n{'='*55}\n")

    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    ok = skip = fail = 0

    for row in data:
        doi = (row.get("doi") or "").strip()
        images = row.get("images") or []
        if not images:
            print(f"  {doi}: no images field, skipping")
            skip += 1
            continue

        rating = db.query(Rating).filter(
            Rating.doi == doi,
            Rating.orcid_id == orcid_id,
            Rating.scoring_mode == "new_design",
        ).first()

        if not rating:
            print(f"  {doi}: rating not found in DB, skipping")
            skip += 1
            continue

        obs = rating.reproducibility_observation or ""
        if "/images/" in obs:
            print(f"  {doi}: already has image link, skipping")
            skip += 1
            continue

        img_tags = []
        for img in images:
            uri = img.get("uri", "")
            # Strip data URI prefix: data:image/jpeg;base64,...
            match = re.match(r"data:([^;]+);base64,(.+)", uri, re.DOTALL)
            if not match:
                print(f"    WARNING: unrecognised URI format for {doi}, skipping image")
                continue
            mime = match.group(1)
            raw = base64.b64decode(match.group(2))
            img_uuid = str(uuid_lib.uuid4())
            print(f"  {doi}: uploading image {img_uuid} ({mime}, {len(raw)} bytes)")
            if not args.dry_run:
                img_row = UploadedImage(
                    uuid=img_uuid,
                    uploader_orcid_id=orcid_id,
                    mime_type=mime,
                    data=raw,
                )
                db.add(img_row)
                db.flush()
            img_tags.append(f"![image](/images/{img_uuid})")

        if not img_tags:
            fail += 1
            continue

        new_obs = obs.rstrip() + "\n\n" + "\n".join(img_tags)
        print(f"  {doi}: appending {len(img_tags)} image tag(s) to observation")
        if not args.dry_run:
            rating.reproducibility_observation = new_obs
            db.commit()
        ok += 1

    print(f"\n{'='*55}\n  Updated : {ok}\n  Skipped : {skip}\n  Failed  : {fail}")
    if args.dry_run:
        print("  (dry run — no changes made)")
    print()
    db.close()


if __name__ == "__main__":
    main()
