import json
import re
import httpx

DOI_PATTERN = re.compile(r"10\.\d{4,}/\S+")
CROSSREF_URL = "https://api.crossref.org/works/{doi}"


def normalise_doi(raw: str) -> str:
    """Extract a bare DOI from any input — URL, doi: prefix, or plain DOI."""
    s = raw.strip()
    path_only = s.split('?')[0].split('#')[0].rstrip('/')

    # RSC (pubs.rsc.org) — DOI is always 10.1039/{last-segment}
    # e.g. https://pubs.rsc.org/en/content/articlehtml/2021/cs/d1cs00311a
    if 'pubs.rsc.org' in s:
        suffix = path_only.split('/')[-1]
        if re.match(r'^[a-z0-9]{6,20}$', suffix, re.IGNORECASE):
            return f"10.1039/{suffix.lower()}"

    # Nature family (nature.com/articles/{slug}) — DOI is 10.1038/{slug}
    # e.g. https://www.nature.com/articles/s41557-021-00679-1
    if 'nature.com/articles/' in s:
        slug = path_only.split('/articles/')[-1].split('/')[0]
        if re.match(r'^[a-zA-Z0-9._-]{4,}$', slug):
            return f"10.1038/{slug}"

    # Beilstein journals — DOI is 10.3762/{journal}.{vol}.{id}
    # e.g. https://www.beilstein-journals.org/bjoc/articles/19/1
    if 'beilstein-journals.org' in s:
        parts = path_only.split('/')
        # expect: .../{journal}/articles/{vol}/{id}
        try:
            art_idx = parts.index('articles')
            journal = parts[art_idx - 1]   # e.g. bjoc, bjnano
            vol = parts[art_idx + 1]
            art_id = parts[art_idx + 2]
            if vol.isdigit() and art_id.isdigit():
                return f"10.3762/{journal}.{vol}.{art_id}"
        except (ValueError, IndexError):
            pass

    # Generic: extract DOI pattern from anywhere in the string (handles publisher URLs,
    # doi.org links, doi:/DOI: prefixes, pasted article pages, etc.)
    # Covers: ACS, Wiley, Springer, Thieme, Taylor & Francis, Science, PNAS, Elsevier
    # direct doi links, chemrxiv, etc.
    match = re.search(r'10\.\d{4,}/\S+', s)
    if match:
        doi = match.group(0)
    else:
        doi = s
    return doi.rstrip(".,;)")


def is_valid_doi(doi: str) -> bool:
    return bool(DOI_PATTERN.fullmatch(doi))


def looks_like_doi(query: str) -> bool:
    """Return True if the query looks like a DOI rather than a title."""
    q = normalise_doi(query)
    return bool(DOI_PATTERN.match(q))


async def search_by_title(title: str, rows: int = 8) -> list[dict]:
    """Search CrossRef by title. Returns a list of candidate paper dicts."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.crossref.org/works",
            params={
                "query.title": title,
                "rows": rows,
                "select": "DOI,title,author,container-title,published-print,published-online",
            },
            headers={"User-Agent": "ChemRepro/1.0 (mailto:admin@chemrepro.io)"},
        )
    if resp.status_code != 200:
        return []

    results = []
    for item in resp.json().get("message", {}).get("items", []):
        doi = item.get("DOI", "")
        titles = item.get("title", [])
        if not doi or not titles:
            continue
        authors_raw = item.get("author", [])
        authors_list = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in authors_raw if a.get("family")
        ]
        container = item.get("container-title", [])
        published = item.get("published-print") or item.get("published-online") or {}
        date_parts = published.get("date-parts", [[]])
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        results.append({
            "doi": doi,
            "title": titles[0],
            "authors": authors_list,
            "journal": container[0] if container else None,
            "year": year,
        })
    return results


async def _fetch_europepmc_abstract(doi: str) -> str | None:
    """Fallback abstract source when CrossRef has none."""
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&format=json"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers={"User-Agent": "ChemRepro/1.0"})
        if resp.status_code != 200:
            return None
        for item in resp.json().get("resultList", {}).get("result", []):
            text = item.get("abstractText", "").strip()
            if text:
                return text
    except Exception:
        pass
    return None


async def fetch_paper_metadata(doi: str) -> dict | None:
    """
    Query CrossRef for paper metadata. Returns a dict ready for Paper model
    or None if not found.
    """
    url = CROSSREF_URL.format(doi=doi)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers={"User-Agent": "ChemRepro/1.0 (mailto:admin@chemrepro.io)"})
    if resp.status_code != 200:
        return None

    data = resp.json().get("message", {})

    title_parts = data.get("title", [])
    title_raw = title_parts[0] if title_parts else "Unknown title"
    # Strip JATS/HTML tags from title (CrossRef embeds <sub>, <sup> etc.)
    title = re.sub(r"<[^>]+>", "", title_raw).strip()
    # Remove "Electronic supplementary information" suffix (RSC papers concatenate ESI text)
    title = re.sub(
        r"\s*Electronic supplementary information.*$", "", title, flags=re.IGNORECASE
    ).strip() or title_raw

    authors_raw = data.get("author", [])
    authors_list = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in authors_raw
        if a.get("family")
    ]
    authors = json.dumps(authors_list)

    container = data.get("container-title", [])
    journal = container[0] if container else None

    published = data.get("published-print") or data.get("published-online") or {}
    date_parts = published.get("date-parts", [[]])
    year = date_parts[0][0] if date_parts and date_parts[0] else None

    abstract_raw = data.get("abstract", "")
    abstract = re.sub(r"<[^>]+>", "", abstract_raw).strip() or None
    # JATS XML embeds <jats:title>Abstract</jats:title> which concatenates onto
    # the first word after tag-stripping (e.g. "AbstractGarsubellin A")
    if abstract:
        abstract = re.sub(r"^Abstract\s*", "", abstract, flags=re.IGNORECASE).strip() or None

    if not abstract:
        abstract = await _fetch_europepmc_abstract(doi)

    return {
        "doi": doi,
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": year,
        "abstract": abstract,
    }


async def resolve_url_to_doi(url: str) -> str | None:
    """Resolve a publisher URL that doesn't embed a DOI to an actual DOI.
    Handles PubMed (via NCBI eSummary) and ScienceDirect (via CrossRef alternative-id).
    Returns the DOI string, or None if unrecognised / lookup fails."""
    if 'pubmed.ncbi.nlm.nih.gov' in url:
        return await _resolve_pubmed(url)
    if 'sciencedirect.com' in url or 'linkinghub.elsevier.com' in url:
        return await _resolve_sciencedirect(url)
    return None


async def _resolve_pubmed(url: str) -> str | None:
    pmid = url.rstrip('/').split('/')[-1].split('?')[0]
    if not pmid.isdigit():
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "pubmed", "id": pmid, "retmode": "json"},
                headers={"User-Agent": "ChemRepro/1.0"},
            )
        if resp.status_code != 200:
            return None
        result = resp.json().get("result", {}).get(pmid, {})
        for artid in result.get("articleids", []):
            if artid.get("idtype") == "doi":
                return artid.get("value")
    except Exception:  # noqa: BLE001
        pass
    return None


async def _resolve_sciencedirect(url: str) -> str | None:
    """Use CrossRef alternative-id filter to resolve a ScienceDirect PII to a DOI."""
    pii_match = re.search(r'pii/([A-Z0-9]+)', url, re.IGNORECASE)
    if not pii_match:
        return None
    pii = pii_match.group(1)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://api.crossref.org/works",
                params={"filter": f"alternative-id:{pii}", "select": "DOI", "rows": 1},
                headers={"User-Agent": "ChemRepro/1.0"},
            )
        if resp.status_code != 200:
            return None
        items = resp.json().get("message", {}).get("items", [])
        if items:
            return items[0].get("DOI")
    except Exception:  # noqa: BLE001
        pass
    return None
