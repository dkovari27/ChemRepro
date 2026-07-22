#!/usr/bin/env python3
"""
Scan ChemRepro ratings for unresolved formatted bibliographic citations and
flag them for admin review.

An "unresolved citation" is a formatted bibliographic reference such as
  "J. Org. Chem. 2022, 87, 1234-1238"
  "Org. Lett. 2019, 21, 5678"
  "Angew. Chem. Int. Ed. 2021, 60, 12345"
that does NOT already carry a [[DOI]] in double-bracket notation.

Author-name phrases like "Smith et al." or "Njardarson and co-workers" are
NOT processed by this script (Category B detection is disabled).

Pipeline per rating:
  1. Claude Haiku (via CLI): detect formatted bibliographic citations
  2. CrossRef search API: retrieve top-5 candidates per citation
  3. Claude Sonnet (via CLI): pick the best match and report confidence
  4. Send admin email with Approve / Resolve manually / Dismiss buttons
  5. Text is NEVER changed automatically regardless of confidence

Runs locally via the Claude Code CLI (claude -p), using your Pro subscription.
No Anthropic API key required. See TASKS.md for future API migration note.

Usage:
  python scripts/resolve_citations.py --dry-run        # preview only
  python scripts/resolve_citations.py                  # live run (sends emails)
  python scripts/resolve_citations.py --railway        # use Railway DB
  python scripts/resolve_citations.py --ai-name JACSAU # limit to one AI reviewer
  python scripts/resolve_citations.py --ids 52 53 54  # specific rating IDs
"""
import argparse
import glob as _glob
import hashlib
import hmac as _hmac_module
import html as _html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.rating import Rating


_CROSSREF_URL = "https://api.crossref.org/works"


def _call_claude_cli(system: str, user: str, model: str) -> str:
    """Call the Claude Code CLI (claude -p). Uses Pro subscription; no API key needed."""
    prompt = f"<system_instructions>\n{system}\n</system_instructions>\n\n{user}" if system else user
    cmd = _build_claude_cmd(prompt, model)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, encoding="utf-8")
    except FileNotFoundError:
        raise RuntimeError(
            "Claude CLI not found. Run 'where claude' in PowerShell to locate it, "
            "then add it to PATH or set the CLAUDE_PATH environment variable."
        )
    if result.returncode != 0:
        err = result.stderr.strip() or "claude CLI returned a non-zero exit code"
        raise RuntimeError(f"Claude CLI error: {err}")
    return result.stdout.strip()


def _build_claude_cmd(prompt: str, model: str) -> list[str]:
    """Build subprocess command for claude -p, handling Windows .cmd wrapper."""
    override = os.environ.get("CLAUDE_PATH")
    if override:
        return _wrap_cmd(override, prompt, model)
    if platform.system() != "Windows":
        exe = shutil.which("claude") or "claude"
        return [exe, "-p", prompt, "--model", model]
    for name in ("claude.cmd", "claude.exe", "claude"):
        path = shutil.which(name)
        if path:
            return _wrap_cmd(path, prompt, model)
    local = os.environ.get("LOCALAPPDATA", "")
    home = os.path.expanduser("~")
    for p in [
        os.path.join(home, "AppData", "Roaming", "npm", "claude.cmd"),
        os.path.join(home, "AppData", "Local", "Programs", "claude", "claude.exe"),
    ]:
        if os.path.exists(p):
            return _wrap_cmd(p, prompt, model)
    store_pattern = os.path.join(
        local, "Packages", "Claude_*", "LocalCache", "Roaming",
        "Claude", "claude-code", "*", "claude.exe"
    )
    matches = sorted(_glob.glob(store_pattern))
    if matches:
        return [matches[-1], "-p", prompt, "--model", model]
    raise FileNotFoundError(
        "claude CLI not found. Run 'where claude' in PowerShell, "
        "then add it to PATH or set CLAUDE_PATH."
    )


def _wrap_cmd(path: str, prompt: str, model: str) -> list[str]:
    if path.lower().endswith(".cmd"):
        return ["cmd", "/c", path, "-p", prompt, "--model", model]
    return [path, "-p", prompt, "--model", model]


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return json.loads(text)


_CROSSREF_HEADERS = {"User-Agent": "ChemRepro/1.0 (mailto:chemrepro@gmail.com)"}

# Category B (author-name phrase detection) was intentionally DISABLED.
# The original Category B prompt detected mentions like "Smith et al.", "Jones and Lee",
# "Njardarson and co-workers" and tried to resolve them to DOIs. This caused false
# positives (e.g. resolving an author's own name to the reviewed paper's DOI).
# Kept here as a comment in case it proves useful in the future.
#
# Category A only: formatted bibliographic citations.

_HAIKU_DETECT_PROMPT = """\
You review a chemistry reproducibility observation for formatted bibliographic citations \
that have not yet been resolved to a DOI.

A FORMATTED CITATION contains a journal name or abbreviation together with a year and \
optionally a volume and/or page range. Examples:
  "J. Org. Chem. 2022, 87, 1234-1238"
  "Org. Lett. 2019, 21, 5678"
  "ACS Catal. 2020, 10, 9012-9020"
  "Angew. Chem. Int. Ed. 2021, 60, 12345"
  "Chem. Commun. 2017, 53, 7890-7893"
  "Green Chem. 2018, 20, 3456-3465"
  "Nat. Chem. 2020, 12, 123-130"

DO NOT flag:
  - Author-name phrases like "Smith et al.", "Jones and Lee", "as reported by X and co-workers"
  - General text that does not include a journal abbreviation + year
  - Any citation already in [[10.xxxx/...]] double-bracket notation — skip those entirely

Return ONLY valid JSON, no markdown:
{
  "citations": [
    {
      "mention": "<exact citation text as it appears in the observation>",
      "sentence": "<the full sentence containing the citation>",
      "journal": "<journal name or abbreviation>",
      "year": <integer year or null>,
      "volume": "<volume number as string or null>",
      "pages": "<page range or null>"
    }
  ]
}

Return {"citations": []} if no formatted bibliographic citations are found.\
"""

_SONNET_PICK_PROMPT = """\
You are verifying whether a CrossRef search result matches a chemistry paper citation.

Unresolved mention: "{mention}"
Sentence context: "{sentence}"
Journal / volume / pages from citation: "{topic}"

CrossRef candidates:
{candidates}

Pick the candidate that best matches the citation. Only confirm a match if you are highly \
confident (>= 0.80) the candidate is the same paper being cited. For formatted bibliographic \
citations, match on journal, year, volume, and page range.

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


def _crossref_search(
    mention: str,
    year: int | None,
    journal: str = "",
    volume: str = "",
    pages: str = "",
) -> list[dict]:
    params: dict = {
        "rows": 5,
        "select": "DOI,title,author,published-print,published-online,container-title,page,volume",
    }
    params["query.bibliographic"] = mention[:200]
    if journal:
        params["query.container-title"] = journal[:80]
    if year:
        params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"
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
        journal_name = journals[0] if journals else ""
        results.append({
            "doi": item.get("DOI", ""),
            "title": title,
            "authors": author_str,
            "year": pub_year,
            "journal": journal_name,
            "page": item.get("page", ""),
            "volume": item.get("volume", ""),
        })
    return results


def _format_candidates(candidates: list[dict]) -> str:
    lines = []
    for i, c in enumerate(candidates, 1):
        vol_part = f" | Vol: {c['volume']}" if c.get("volume") else ""
        page_part = f" | Pages: {c['page']}" if c.get("page") else ""
        lines.append(
            f"{i}. DOI: {c['doi']} | Title: {c['title'][:90]} | "
            f"Authors: {c['authors']} | Year: {c['year']} | Journal: {c['journal']}{vol_part}{page_part}"
        )
    return "\n".join(lines) if lines else "(no candidates found)"


def _make_citation_token(rating_id: int, mention: str, candidate_doi: str, secret: str) -> str:
    msg = f"{rating_id}:{mention}:{candidate_doi}".encode()
    return _hmac_module.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _make_dismiss_token(rating_id: int, mention: str, candidate_doi: str, secret: str) -> str:
    msg = f"dismiss:{rating_id}:{mention}:{candidate_doi}".encode()
    return _hmac_module.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _flag_for_admin(
    rating,
    mention: str,
    candidate_doi: str,
    confidence: float,
    candidate_info: dict | None = None,
) -> None:
    """Send an HTML admin email with Approve / Resolve manually / Dismiss buttons."""
    try:
        from app.utils.email import send_generic_email
        from app.config import settings as _settings

        approve_token = _make_citation_token(
            rating.id, mention, candidate_doi, _settings.ADMIN_SECRET_TOKEN
        )
        dismiss_token = _make_dismiss_token(
            rating.id, mention, candidate_doi, _settings.ADMIN_SECRET_TOKEN
        )

        approve_url = (
            f"{_settings.SITE_URL}/admin/citation-approve"
            f"?r={rating.id}&m={quote(mention, safe='')}&d={quote(candidate_doi, safe='')}"
            f"&t={approve_token}"
        )
        review_path = (
            f"/admin/citation-review/{rating.id}"
            f"?m={quote(mention, safe='')}&d={quote(candidate_doi, safe='')}"
        )
        review_url = (
            f"{_settings.SITE_URL}/admin/login/{_settings.ADMIN_SECRET_TOKEN}"
            f"?next={quote(review_path, safe='')}"
        )
        dismiss_url = (
            f"{_settings.SITE_URL}/admin/citation-dismiss"
            f"?r={rating.id}&m={quote(mention, safe='')}&d={quote(candidate_doi, safe='')}"
            f"&t={dismiss_token}"
        )
        paper_url = f"{_settings.SITE_URL}/paper/{rating.doi}"

        # Highlight detected mention in observation text
        obs = rating.reproducibility_observation or ""
        obs_esc = _html.escape(obs)
        mention_esc = _html.escape(mention)
        obs_highlighted = obs_esc.replace(
            mention_esc,
            f'<mark style="background:#fef08a;padding:0 2px;border-radius:2px">{mention_esc}</mark>',
            1,
        )

        cand = candidate_info or {}
        cand_title = _html.escape(cand.get("title", ""))
        cand_authors = _html.escape(cand.get("authors", ""))
        cand_journal = _html.escape(cand.get("journal", ""))
        cand_year = cand.get("year", "")
        cand_vol = _html.escape(str(cand.get("volume", "") or ""))
        cand_page = _html.escape(str(cand.get("page", "") or ""))

        candidate_rows = ""
        if cand_title:
            candidate_rows += f"""
    <tr><td style="padding:8px 14px;color:#64748b;font-weight:600">Title</td>
        <td style="padding:8px 14px">{cand_title}</td></tr>"""
        if cand_authors:
            candidate_rows += f"""
    <tr style="background:#f1f5f9">
        <td style="padding:8px 14px;color:#64748b;font-weight:600">Authors</td>
        <td style="padding:8px 14px">{cand_authors}</td></tr>"""
        if cand_journal:
            candidate_rows += f"""
    <tr><td style="padding:8px 14px;color:#64748b;font-weight:600">Journal</td>
        <td style="padding:8px 14px">{cand_journal}{', ' + str(cand_year) if cand_year else ''}{', vol. ' + cand_vol if cand_vol else ''}{', p. ' + cand_page if cand_page else ''}</td></tr>"""

        body_html = f"""
<div style="font-family:sans-serif;max-width:660px;margin:0 auto;color:#1e293b">
  <h2 style="color:#1e40af;margin-bottom:4px">Citation detected in rating {rating.id}</h2>
  <p style="color:#64748b;margin-top:0">
    A formatted bibliographic citation was found.
    Proposed DOI confidence: <strong>{confidence:.0%}</strong>
  </p>

  <h3 style="font-size:13px;font-weight:600;color:#475569;margin-bottom:6px">Observation text</h3>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px 16px;
              font-size:13px;line-height:1.6;max-height:200px;overflow-y:auto;
              white-space:pre-wrap;word-wrap:break-word;margin-bottom:16px">
    {obs_highlighted}
  </div>

  <table style="width:100%;border-collapse:collapse;margin:0 0 16px;background:#f8fafc;
                border:1px solid #e2e8f0;border-radius:8px;font-size:14px">
    <tr><td style="padding:8px 14px;color:#64748b;font-weight:600;width:150px">Rating ID</td>
        <td style="padding:8px 14px">{rating.id}</td></tr>
    <tr style="background:#f1f5f9">
        <td style="padding:8px 14px;color:#64748b;font-weight:600">Paper</td>
        <td style="padding:8px 14px">
          <a href="{paper_url}" style="color:#1e40af">{rating.doi}</a>
        </td></tr>
    <tr><td style="padding:8px 14px;color:#64748b;font-weight:600">Detected citation</td>
        <td style="padding:8px 14px;font-family:monospace;color:#b45309">{_html.escape(mention)}</td></tr>
    <tr style="background:#f1f5f9">
        <td style="padding:8px 14px;color:#64748b;font-weight:600">Proposed DOI</td>
        <td style="padding:8px 14px;font-family:monospace">
          <a href="https://doi.org/{_html.escape(candidate_doi)}" style="color:#1e40af">
            {_html.escape(candidate_doi)}
          </a>
        </td></tr>
    {candidate_rows}
    <tr style="background:#f1f5f9">
        <td style="padding:8px 14px;color:#64748b;font-weight:600">Confidence</td>
        <td style="padding:8px 14px">{confidence:.0%}</td></tr>
  </table>

  <p style="font-size:13px;color:#475569;margin-bottom:14px">
    Clicking <strong>Approve</strong> replaces the citation text with the DOI link in the review.
    Clicking <strong>Resolve manually</strong> opens a form to enter a different DOI.
    Clicking <strong>Dismiss</strong> acknowledges this notice with no changes.
    You are logged in automatically on all three links.
  </p>

  <a href="{approve_url}"
     style="display:inline-block;padding:10px 22px;background:#15803d;color:#fff;
            text-decoration:none;border-radius:7px;font-weight:700;font-size:14px;margin-right:8px">
    Approve
  </a>
  <a href="{review_url}"
     style="display:inline-block;padding:10px 22px;background:#1e40af;color:#fff;
            text-decoration:none;border-radius:7px;font-weight:700;font-size:14px;margin-right:8px">
    Resolve manually
  </a>
  <a href="{dismiss_url}"
     style="display:inline-block;padding:10px 22px;background:#64748b;color:#fff;
            text-decoration:none;border-radius:7px;font-weight:700;font-size:14px">
    Dismiss
  </a>
</div>"""

        body_text = (
            f"Citation detected in rating {rating.id} (confidence {confidence:.0%})\n\n"
            f"Rating   : {rating.id}\n"
            f"Paper    : {rating.doi}\n"
            f"Mention  : {mention}\n"
            f"Proposed : {candidate_doi}\n\n"
            f"Approve  : {approve_url}\n"
            f"Review   : {review_url}\n"
            f"Dismiss  : {dismiss_url}\n"
        )

        send_generic_email(
            to=_settings.GMAIL_ADDRESS,
            subject=f"[ChemRepro] Citation detected: rating {rating.id}",
            body_html=body_html,
            body_text=body_text,
        )
        print(f"      Admin notified: suggested [[{candidate_doi}]] ({confidence:.0%} confidence)")
    except Exception as exc:
        print(f"      Admin notify failed (non-fatal): {exc}")


def resolve_ratings(
    db_url: str,
    rating_ids: list[int] | None = None,
    orcid_id: str | None = None,
    paper_dois: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Core resolution function. Call from import_reviews.py or standalone.
    Uses the Claude Code CLI (Pro subscription). Run locally only.

    Returns {"flagged": N, "no_candidate": N, "skipped": N, "errors": N}
    """
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

    flagged = no_candidate = skipped = errors = 0

    for rating in ratings:
        obs = rating.reproducibility_observation or ""

        # Haiku via CLI: detect formatted bibliographic citations
        try:
            raw = _call_claude_cli(
                system=_HAIKU_DETECT_PROMPT,
                user=f"Observation text:\n{obs}",
                model="claude-haiku-4-5-20251001",
            )
            detected = _parse_json_response(raw)
            citations = detected.get("citations", [])
        except Exception as exc:
            print(f"    rating {rating.id}: detection error: {exc}")
            errors += 1
            continue

        if not citations:
            skipped += 1
            continue

        print(f"    rating {rating.id} (doi={rating.doi}): {len(citations)} formatted citation(s)")

        for cite_info in citations:
            mention = cite_info.get("mention", "")
            sentence = cite_info.get("sentence", "")
            journal = cite_info.get("journal", "")
            year = cite_info.get("year")
            volume = str(cite_info.get("volume") or "")
            pages = str(cite_info.get("pages") or "")
            topic = " ".join(filter(None, [journal, volume, pages]))

            time.sleep(0.5)
            candidates = _crossref_search(mention, year, journal=journal, volume=volume, pages=pages)
            print(f"      CrossRef candidates for '{mention}':")
            for c in candidates:
                print(
                    f"        [{c['doi']}] {c['title'][:70]} "
                    f"({c['year']}) {c['journal']} vol.{c.get('volume', '?')} p.{c.get('page', '?')}"
                )

            if not candidates:
                print(f"      '{mention}': no CrossRef candidates, skipping")
                no_candidate += 1
                continue

            # Sonnet via CLI: pick best match
            try:
                raw = _call_claude_cli(
                    system="",
                    user=_SONNET_PICK_PROMPT.format(
                        mention=mention,
                        sentence=sentence,
                        topic=topic,
                        candidates=_format_candidates(candidates),
                    ),
                    model="claude-sonnet-5",
                )
                pick = _parse_json_response(raw)
            except Exception as exc:
                print(f"      '{mention}': pick error: {exc}")
                errors += 1
                continue

            doi = pick.get("doi")
            confidence = pick.get("confidence", 0.0)

            if not doi:
                print(f"      '{mention}': Sonnet found no match, using top CrossRef candidate")
                doi = candidates[0]["doi"]
                confidence = 0.0

            print(f"      '{mention}' -> proposed [[{doi}]] (confidence={confidence:.2f})")

            if not dry_run:
                best = next((c for c in candidates if c["doi"] == doi), candidates[0])
                _flag_for_admin(rating, mention, doi, confidence, candidate_info=best)
                flagged += 1

    db.close()
    print(
        f"  resolve_citations: flagged={flagged} no_candidate={no_candidate} "
        f"skipped={skipped} errors={errors}"
    )
    return {"flagged": flagged, "no_candidate": no_candidate, "skipped": skipped, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Detect and flag bibliographic citations in ChemRepro reviews")
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
