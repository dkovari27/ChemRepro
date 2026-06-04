import json
import re
import httpx

DOI_PATTERN = re.compile(r"10\.\d{4,}/\S+")
CROSSREF_URL = "https://api.crossref.org/works/{doi}"


def normalise_doi(raw: str) -> str:
    """Strip URL prefix and trailing punctuation from a DOI string."""
    doi = raw.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "DOI:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    doi = doi.rstrip(".,;)")
    return doi


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
    title = title_parts[0] if title_parts else "Unknown title"

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

    return {
        "doi": doi,
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": year,
    }
