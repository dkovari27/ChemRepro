#!/usr/bin/env python3
"""
Scan ChemRepro ratings for unresolved paper citations and attempt to resolve them.

An "unresolved citation" is a mention like "Smith et al. (2019)" or "as reported
by Jones and Lee" that does NOT already have a [[DOI]] in double-bracket notation.

Pipeline per rating:
  1. Claude Haiku: detect unresolved mentions and extract author/year/topic info
  2. CrossRef search API: retrieve top-3 candidates per mention
  3. Claude Sonnet: pick the best match (confidence threshold >= 0.80)
  4. Rewrite observation text with [[DOI]] substituted in place; commit
  5. If unresolved: leave text unchanged; print a warning

Usage:
  set DATABASE_URL=postgresql://...
  set ANTHROPIC_API_KEY=sk-ant-...

  python scripts/resolve_citations.py --dry-run        # preview only
  python scripts/resolve_citations.py                  # live run on all ratings
  python scripts/resolve_citations.py --ai-name JACSAU # limit to one AI reviewer
  python scripts/resolve_citations.py --ids 52 53 54  # specific rating IDs
"""
import argparse
import hashlib
import hmac as _hmac_module
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.rating import Rating

try:
    import anthropic as _anthropic_module
    _anthropic_available = True
except ImportError:
    _anthropic_available = False


_CROSSREF_URL = "https://api.crossref.org/works"


def _extract_text(response) -> str:
    """Return the text of the first TextBlock in a response (skips ThinkingBlocks)."""
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""


def _parse_json_response(text: str) -> dict:
    """Extract and parse a JSON object from a model response robustly.

    Handles: plain JSON, ```json fences, fences with extra trailing text.
    """
    text = text.strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return json.loads(text)
_CROSSREF_HEADERS = {"User-Agent": "ChemRepro/1.0 (mailto:chemrepro@gmail.com)"}

_HAIKU_DETECT_PROMPT = """\
You review a chemistry reproducibility observation for unresolved paper citations.

An UNRESOLVED citation is a reference to a specific external paper by author name (e.g. "Smith et al.", \
"Jones and Lee (2019)", "following the method of Peng et al.") where no DOI in [[double-bracket]] notation \
is present in the same sentence.

An ALREADY RESOLVED citation has [[10.xxxx/...]] directly in the text — skip those.

Return ONLY valid JSON, no markdown:
{
  "unresolved": [
    {
      "mention": "<exact phrase identifying the cited group, e.g. 'Smith et al. (2019)'>",
      "sentence": "<the full sentence containing the mention>",
      "authors": "<surname(s) of cited authors, comma-separated>",
      "year": <integer year or null>,
      "topic": "<brief description of what the cited work is about, from context>"
    }
  ]
}

Return {"unresolved": []} if all citations already have [[DOI]] or if there are no citations.\
"""

_SONNET_PICK_PROMPT = """\
You are verifying whether a CrossRef search result matches a chemistry paper citation.

Unresolved mention: "{mention}"
Sentence context: "{sentence}"
Topic from context: "{topic}"

CrossRef candidates:
{candidates}

Pick the candidate that best matches the citation. Only confirm a match if you are highly confident \
(>= 0.80) the candidate is the same paper being cited.

Return ONLY valid JSON:
{{"doi": "<DOI string>", "confidence": <0.0-1.0>}}
or {{"doi": null, "confidence": 0.0}} if no candidate is a confident match.\
"""


def _make_db(db_url: str):
    url = db_url
    if "postgres" in url:
        url = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)
    engine = create_engine(url)
    return sessionmaker(bind=engine)()


def _crossref_search(mention: str, authors: str, year: int | None, topic: str) -> list[dict]:
    params: dict = {
        "rows": 5,
        "select": "DOI,title,author,published-print,published-online,container-title",
    }
    # Always pass the raw mention as the bibliographic query — CrossRef handles both
    # "Smith et al. 2019" and "Green Chem. 2022, 24, 4628" style citations well this way.
    bib = mention
    if topic and topic not in mention:
        bib = f"{mention} {topic[:60]}"
    params["query.bibliographic"] = bib[:200]
    # Add author search only for "et al." / "Author and Author" style mentions
    if authors and re.search(r'\bet al\b|and\s+\w+', mention, re.I):
        params["query.author"] = authors
    if year:
        params["filter"] = f"from-pub-date:{year - 1},until-pub-date:{year + 1}"
    try:
        r = httpx.get(_CROSSREF_URL, params=params, headers=_CROSSREF_HEADERS, timeout=10)
        items = r.json().get("message", {}).get("items", [])
    except Exception as exc:
        print(f"    CrossRef error: {exc}")
        return []
    results = []
    for item in items:
        title_parts = item.get("title", [])
        title = re.sub(r"<[^>]+>", "", title_parts[0] if title_parts else "").strip()
        raw_authors = item.get("author", [])
        author_str = ", ".join(
            f"{a.get('family', '')} {a.get('given', '')[:1]}".strip()
            for a in raw_authors[:3]
        )
        pub = item.get("published-print") or item.get("published-online") or {}
        parts = pub.get("date-parts", [[]])
        pub_year = parts[0][0] if parts and parts[0] else None
        journals = item.get("container-title", [])
        journal = journals[0] if journals else ""
        results.append({
            "doi": item.get("DOI", ""),
            "title": title,
            "authors": author_str,
            "year": pub_year,
            "journal": journal,
        })
    return results


def _format_candidates(candidates: list[dict]) -> str:
    lines = []
    for i, c in enumerate(candidates, 1):
        lines.append(
            f"{i}. DOI: {c['doi']} | Title: {c['title'][:90]} | "
            f"Authors: {c['authors']} | Year: {c['year']} | Journal: {c['journal']}"
        )
    return "\n".join(lines) if lines else "(no candidates found)"


def _make_citation_token(rating_id: int, mention: str, candidate_doi: str, secret: str) -> str:
    msg = f"{rating_id}:{mention}:{candidate_doi}".encode()
    return _hmac_module.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _flag_for_admin(rating, mention: str, candidate_doi: str, confidence: float) -> None:
    """Send an HTML admin email with Confirm / Review manually buttons."""
    try:
        from app.utils.email import send_generic_email
        from app.config import settings as _settings

        token = _make_citation_token(
            rating.id, mention, candidate_doi, _settings.ADMIN_SECRET_TOKEN
        )
        approve_url = (
            f"{_settings.SITE_URL}/admin/citation-approve"
            f"?r={rating.id}&m={quote(mention)}&d={quote(candidate_doi)}&t={token}"
        )
        review_url = (
            f"{_settings.SITE_URL}/admin/citation-review/{rating.id}"
            f"?m={quote(mention)}&d={quote(candidate_doi)}"
        )
        paper_url = f"{_settings.SITE_URL}/paper/{rating.doi}"

        body_html = f"""
<div style="font-family:sans-serif;max-width:620px;margin:0 auto;color:#1e293b">
  <h2 style="color:#1e40af;margin-bottom:4px">Citation review needed</h2>
  <p style="color:#64748b;margin-top:0">Confidence {confidence:.0%} — below auto-resolve threshold (80%)</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0;background:#f8fafc;
                border:1px solid #e2e8f0;border-radius:8px;font-size:14px">
    <tr><td style="padding:8px 14px;color:#64748b;font-weight:600;width:150px">Rating ID</td>
        <td style="padding:8px 14px">{rating.id}</td></tr>
    <tr style="background:#f1f5f9">
        <td style="padding:8px 14px;color:#64748b;font-weight:600">Paper</td>
        <td style="padding:8px 14px"><a href="{paper_url}" style="color:#1e40af">{rating.doi}</a></td></tr>
    <tr><td style="padding:8px 14px;color:#64748b;font-weight:600">Mention in text</td>
        <td style="padding:8px 14px;font-family:monospace">{mention}</td></tr>
    <tr style="background:#f1f5f9">
        <td style="padding:8px 14px;color:#64748b;font-weight:600">Best candidate</td>
        <td style="padding:8px 14px;font-family:monospace">{candidate_doi}</td></tr>
    <tr><td style="padding:8px 14px;color:#64748b;font-weight:600">Confidence</td>
        <td style="padding:8px 14px">{confidence:.0%}</td></tr>
  </table>
  <p style="font-size:14px">If the candidate DOI is correct, click <strong>Confirm</strong> to apply it
  instantly. If it is wrong, click <strong>Review</strong> to pick the right DOI and preview the result.</p>
  <a href="{approve_url}"
     style="display:inline-block;padding:10px 22px;background:#1e40af;color:#fff;
            text-decoration:none;border-radius:7px;font-weight:700;font-size:14px;margin-right:10px">
    Confirm
  </a>
  <a href="{review_url}"
     style="display:inline-block;padding:10px 22px;background:#64748b;color:#fff;
            text-decoration:none;border-radius:7px;font-weight:700;font-size:14px">
    Review manually
  </a>
</div>"""

        body_text = (
            f"Citation review needed (confidence {confidence:.0%})\n\n"
            f"Rating  : {rating.id}\n"
            f"Paper   : {rating.doi}\n"
            f"Mention : {mention}\n"
            f"Candidate: {candidate_doi}\n\n"
            f"Confirm : {approve_url}\n"
            f"Review  : {review_url}\n"
        )

        send_generic_email(
            to=_settings.GMAIL_ADDRESS,
            subject=f"[ChemRepro] Citation review needed: rating {rating.id}",
            body_html=body_html,
            body_text=body_text,
        )
        print(f"      Admin notified by email: suggested [[{candidate_doi}]] ({confidence:.0%} confidence)")
    except Exception as exc:
        print(f"      Admin notify failed (non-fatal): {exc}")


def resolve_ratings(
    db_url: str,
    rating_ids: list[int] | None = None,
    orcid_id: str | None = None,
    paper_dois: list[str] | None = None,
    dry_run: bool = False,
    api_key: str | None = None,
) -> dict:
    """
    Core resolution function. Call from import_reviews.py or standalone.

    Returns {"resolved": N, "unresolved": N, "skipped": N, "errors": N}
    """
    if not _anthropic_available:
        print("  resolve_citations: anthropic package not installed, skipping.")
        return {"resolved": 0, "unresolved": 0, "skipped": 0, "errors": 0}

    if not api_key:
        try:
            from app.config import settings as _settings
            api_key = _settings.ANTHROPIC_API_KEY
        except Exception:
            pass
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("  resolve_citations: ANTHROPIC_API_KEY not set in .env or environment, skipping.")
        return {"resolved": 0, "unresolved": 0, "skipped": 0, "errors": 0}

    client = _anthropic_module.Anthropic(api_key=key)
    db = _make_db(db_url)

    q = db.query(Rating).filter(
        Rating.reproducibility_observation.isnot(None),
        Rating.reproducibility_observation != "",
    )
    if rating_ids:
        q = q.filter(Rating.id.in_(rating_ids))
    elif paper_dois:
        q = q.filter(Rating.doi.in_(paper_dois))
    elif orcid_id:
        q = q.filter(Rating.orcid_id == orcid_id)

    ratings = q.all()
    print(f"  resolve_citations: checking {len(ratings)} rating(s)...")

    resolved = unresolved = skipped = errors = 0

    for rating in ratings:
        obs = rating.reproducibility_observation or ""

        # --- Haiku: detect unresolved mentions ---
        try:
            haiku_resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=_HAIKU_DETECT_PROMPT,
                messages=[{"role": "user", "content": f"Observation text:\n{obs}"}],
            )
            detected = _parse_json_response(_extract_text(haiku_resp))
            mentions = detected.get("unresolved", [])
        except Exception as exc:
            raw_preview = _extract_text(haiku_resp)[:120] if haiku_resp.content else "<empty>"
            print(f"    rating {rating.id}: Haiku error: {exc}")
            print(f"    raw response: {raw_preview!r}")
            errors += 1
            continue

        if not mentions:
            skipped += 1
            continue

        print(f"    rating {rating.id} (doi={rating.doi}): {len(mentions)} unresolved mention(s)")
        new_obs = obs

        for mention_info in mentions:
            mention = mention_info.get("mention", "")
            sentence = mention_info.get("sentence", "")
            authors = mention_info.get("authors", "")
            year = mention_info.get("year")
            topic = mention_info.get("topic", "")

            time.sleep(0.5)  # CrossRef polite-pool
            candidates = _crossref_search(mention, authors, year, topic)
            print(f"      CrossRef candidates for '{mention}':")
            for c in candidates:
                print(f"        [{c['doi']}] {c['title'][:70]} ({c['year']}) {c['authors'][:40]}")
            if not candidates:
                print(f"      '{mention}': no CrossRef candidates, leaving unresolved")
                unresolved += 1
                continue

            # --- Sonnet: pick best match ---
            try:
                sonnet_resp = client.messages.create(
                    model="claude-sonnet-5",
                    max_tokens=100,
                    messages=[{
                        "role": "user",
                        "content": _SONNET_PICK_PROMPT.format(
                            mention=mention,
                            sentence=sentence,
                            topic=topic,
                            candidates=_format_candidates(candidates),
                        ),
                    }],
                )
                pick = _parse_json_response(_extract_text(sonnet_resp))
            except Exception as exc:
                print(f"      '{mention}': Sonnet error: {exc}")
                errors += 1
                continue

            doi = pick.get("doi")
            confidence = pick.get("confidence", 0.0)

            if not doi or confidence < 0.80:
                print(f"      '{mention}': low confidence ({confidence:.2f}), leaving unresolved")
                unresolved += 1
                if doi and confidence > 0.0 and not dry_run:
                    _flag_for_admin(rating, mention, doi, confidence)
                continue

            print(f"      '{mention}' -> \"[[{doi}]]\" (confidence={confidence:.2f})")
            if not dry_run:
                new_obs = new_obs.replace(mention, f'"[[{doi}]]"', 1)

        if not dry_run and new_obs != obs:
            rating.reproducibility_observation = new_obs
            db.commit()
            resolved += 1

    db.close()
    print(f"  resolve_citations: resolved={resolved} unresolved={unresolved} skipped={skipped} errors={errors}")
    return {"resolved": resolved, "unresolved": unresolved, "skipped": skipped, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Resolve unlinked paper citations in ChemRepro reviews")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--railway", action="store_true",
                        help="Use PUBLIC_DATABASE_URL from .env (Railway direct connection)")
    parser.add_argument("--ai-name", metavar="NAME", help="Limit to AI-NAME reviewer (e.g. JACSAU)")
    parser.add_argument("--ids", nargs="+", type=int, metavar="ID", help="Specific rating IDs")
    parser.add_argument("--doi", nargs="+", metavar="DOI", help="Limit to reviews for these paper DOIs")
    args = parser.parse_args()

    if args.railway:
        try:
            from app.config import settings as _settings
            db_url = _settings.PUBLIC_DATABASE_URL
            if not db_url:
                print("ERROR: PUBLIC_DATABASE_URL is not set in .env")
                return
        except Exception as exc:
            print(f"ERROR loading PUBLIC_DATABASE_URL: {exc}")
            return
    else:
        db_url = os.environ.get("DATABASE_URL", "sqlite:///./chemrepro.db")

    orcid_id = f"AI-{args.ai_name}" if args.ai_name else None

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n{'='*55}\n  DB  : {db_url[:65]}\n  Mode: {mode}\n{'='*55}\n")

    resolve_ratings(
        db_url=db_url,
        rating_ids=args.ids,
        paper_dois=args.doi,
        orcid_id=orcid_id,
        dry_run=args.dry_run,
    )



if __name__ == "__main__":
    main()
