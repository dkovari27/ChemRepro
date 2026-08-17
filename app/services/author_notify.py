"""
Look up a paper's corresponding author email and send a one-time review notification.
Sources tried in order: CrossRef → Europe PMC → PubMed.
Opt-out is handled via HMAC-signed token using itsdangerous.
"""
import hashlib
import html
import re

import httpx
from itsdangerous import URLSafeSerializer
from sqlalchemy.orm import Session

from app.config import settings
from app.models.author_notification import AuthorNotification
from app.utils.email import send_generic_email

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

_signer = URLSafeSerializer(settings.SECRET_KEY, salt="author-opt-out")


def _make_token(email: str) -> str:
    return _signer.dumps(email)


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


async def _find_email_crossref(doi: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://api.crossref.org/works/{doi}")
            if r.status_code != 200:
                return None
            data = r.json().get("message", {})
            for author in data.get("author", []):
                email = author.get("email", "")
                if email and _EMAIL_RE.match(email):
                    return email.lower()
    except Exception:
        pass
    return None


async def _find_email_europepmc(doi: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            url = (
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                f"?query=doi:{doi}&format=json&resultType=core&pageSize=1"
            )
            r = await client.get(url)
            if r.status_code != 200:
                return None
            results = r.json().get("resultList", {}).get("result", [])
            if not results:
                return None
            for author in results[0].get("authorList", {}).get("author", []):
                for aff in author.get("authorAffiliationDetailList", {}).get("authorAffiliation", []):
                    email = aff.get("email", "")
                    if email and _EMAIL_RE.match(email):
                        return email.lower()
    except Exception:
        pass
    return None


_ELECTRONIC_ADDRESS_RE = re.compile(
    r"Electronic address:\s*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    re.IGNORECASE,
)


async def _find_email_pubmed(doi: str) -> str | None:
    """Search PubMed for the DOI, fetch full XML, and extract corresponding author email.

    PubMed XML affiliation fields often contain 'Electronic address: email@domain.com'
    which is the standardised field for corresponding author contact.
    Covers JACS, Org Lett, J Org Chem, Angew Chem, Nat Chem, Chem Sci, and most other
    indexed chemistry journals.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Step 1: resolve DOI → PMID
            search_r = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={"db": "pubmed", "term": f"{doi}[DOI]", "retmode": "json"},
            )
            if search_r.status_code != 200:
                return None
            ids = search_r.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return None

            # Step 2: fetch full record XML
            fetch_r = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                params={"db": "pubmed", "id": ids[0], "rettype": "xml", "retmode": "xml"},
            )
            if fetch_r.status_code != 200:
                return None

            # Step 3: find 'Electronic address: email@...' anywhere in the XML
            match = _ELECTRONIC_ADDRESS_RE.search(fetch_r.text)
            if match:
                return match.group(1).lower()
    except Exception:
        pass
    return None


async def notify_author_if_possible(
    doi: str,
    paper_title: str,
    rating_id: int,
    db: Session,
    base_url: str = "https://chemrepro.com",
) -> None:
    """Background-task entry point. Finds author email and sends notification if not opted out."""
    if not settings.AUTHOR_NOTIFY_ENABLED:
        return

    email = (
        await _find_email_crossref(doi)
        or await _find_email_europepmc(doi)
        or await _find_email_pubmed(doi)
    )
    if not email:
        return

    email_hash = _hash_email(email)

    # Check global opt-out (user unsubscribed from all ChemRepro emails)
    global_block = db.query(AuthorNotification).filter(
        AuthorNotification.email_hash == email_hash,
        AuthorNotification.global_opted_out == True,  # noqa: E712
    ).first()
    if global_block:
        return

    # Check per-paper deduplication / opt-out
    existing = db.query(AuthorNotification).filter(
        AuthorNotification.doi == doi,
        AuthorNotification.email_hash == email_hash,
    ).first()
    if existing:
        return  # already notified or opted out for this paper

    token = _make_token(email)
    record = AuthorNotification(doi=doi, email_hash=email_hash, opt_out_token=token)
    db.add(record)
    db.commit()

    review_url = f"{base_url}/paper/{doi}#review-{rating_id}"
    opt_out_paper_url = f"{base_url}/notify/opt-out/{token}/paper"
    opt_out_all_url = f"{base_url}/notify/opt-out/{token}/all"
    short_title = paper_title[:100] + ("…" if len(paper_title) > 100 else "")

    body_text = (
        f"Your paper has been reviewed on ChemRepro, a community platform for "
        f"reproducibility ratings in synthetic chemistry.\n\n"
        f'Paper: "{short_title}"\n'
        f"Review: {review_url}\n\n"
        f"ChemRepro collects first-hand reproducibility experiences from practising chemists. "
        f"You are welcome to read or respond to the review on the platform.\n\n"
        f"Stop notifications for this paper only: {opt_out_paper_url}\n\n"
        f"Stop all emails from ChemRepro: {opt_out_all_url}\n\n"
        f"The ChemRepro team\n{base_url}"
    )

    title_esc = html.escape(short_title)
    review_url_esc = html.escape(review_url)

    body_html = f"""
    <p>Your paper has been reviewed on <a href="{base_url}">ChemRepro</a>, a community platform
    for reproducibility ratings in synthetic chemistry.</p>
    <p><strong>Paper:</strong> {title_esc}<br/>
    <strong>Review:</strong> <a href="{review_url_esc}">{review_url_esc}</a></p>
    <p>ChemRepro collects first-hand reproducibility experiences from practising chemists.
    You are welcome to read or respond to the review on the platform.</p>
    <p style="margin-top:16px">
      <a href="{opt_out_paper_url}">Stop notifications for this paper</a>
      &nbsp;&nbsp;&nbsp;&nbsp;
      <a href="{opt_out_all_url}">Unsubscribe from all ChemRepro emails</a>
    </p>
    """

    send_generic_email(
        to=email,
        subject=f"Your paper was reviewed on ChemRepro",
        body_html=body_html,
        body_text=body_text,
    )
