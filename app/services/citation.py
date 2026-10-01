"""Citation data (from CrossRef) and formatters: ACS-style text, RIS, EndNote, BibTeX."""
import json
import re
from urllib.parse import quote

import httpx

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
_cache: dict[str, dict] = {}
_CACHE_MAX = 500
_EN_DASH = "–"


def _strip_tags(s: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", s or "").split())


def _date_parts(message: dict) -> list[int]:
    for key in ("published-print", "issued", "published-online"):
        parts = (message.get(key) or {}).get("date-parts", [[]])
        if parts and parts[0] and parts[0][0]:
            return list(parts[0])
    return []


def _split_name(full: str) -> tuple[str, str]:
    full = full.strip()
    if " " not in full:
        return "", full
    given, family = full.rsplit(" ", 1)
    return given, family


async def get_citation_data(doi: str, fallback: dict | None = None) -> dict | None:
    """Fetch citation fields for a DOI. `fallback` holds title/authors(list)/journal/year
    from our own DB, used when CrossRef is unreachable or lacks a field."""
    if doi in _cache:
        return _cache[doi]

    message: dict = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.crossref.org/works/" + quote(doi, safe="/"),
                headers={"User-Agent": "ChemRepro/1.0 (mailto:admin@chemrepro.io)"},
            )
        if resp.status_code == 200:
            message = resp.json().get("message", {})
    except Exception:  # noqa: BLE001
        message = {}

    fallback = fallback or {}
    authors = [
        {"given": a.get("given", ""), "family": a.get("family", "")}
        for a in message.get("author", []) if a.get("family")
    ]
    if not authors:
        for name in fallback.get("authors", []):
            given, family = _split_name(name)
            authors.append({"given": given, "family": family})

    titles = message.get("title") or []
    title = _strip_tags(titles[0]) if titles else fallback.get("title", "")
    containers = message.get("container-title") or []
    journal = _strip_tags(containers[0]) if containers else (fallback.get("journal") or "")
    parts = _date_parts(message)
    if not parts and fallback.get("year"):
        parts = [fallback["year"]]

    if not title:
        return None

    page = message.get("page") or message.get("article-number") or ""
    data = {
        "doi": doi,
        "authors": authors,
        "title": title,
        "journal": journal,
        "volume": message.get("volume", ""),
        "issue": message.get("issue", ""),
        "page": page,
        "date_parts": parts,
        "publisher": message.get("publisher", ""),
    }
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[doi] = data
    return data


def _date_text(parts: list[int]) -> str:
    if not parts:
        return ""
    if len(parts) >= 3:
        return f"{parts[2]} {_MONTHS[parts[1] - 1]} {parts[0]}"
    if len(parts) == 2:
        return f"{_MONTHS[parts[1] - 1]} {parts[0]}"
    return str(parts[0])


def _page_text(page: str) -> str:
    return page.replace("-", _EN_DASH) if page else ""


def format_text(d: dict) -> str:
    """Full citation in the style shown on ACS article pages."""
    names = ", ".join(f"{a['given']} {a['family']}".strip() for a in d["authors"])
    title = d["title"].rstrip(".")
    out = f"{names}; {title}." if names else f"{title}."
    tail = d["journal"]
    date = _date_text(d["date_parts"])
    if date:
        tail += f" {date}"
    vol_part = ""
    if d["volume"]:
        vol_part = d["volume"]
        if d["issue"]:
            vol_part += f" ({d['issue']})"
    pages = _page_text(d["page"])
    if vol_part and pages:
        tail += f"; {vol_part}: {pages}."
    elif vol_part:
        tail += f"; {vol_part}."
    elif pages:
        tail += f"; {pages}."
    else:
        tail += "."
    out += f" {tail.strip()}"
    out += f" https://doi.org/{d['doi']}"
    return out


def _split_pages(page: str) -> tuple[str, str]:
    if not page:
        return "", ""
    m = re.match(r"^\s*([^-–—]+?)\s*[-–—]\s*(.+?)\s*$", page)
    if m:
        return m.group(1), m.group(2)
    return page.strip(), ""


def to_ris(d: dict) -> str:
    lines = ["TY  - JOUR"]
    for a in d["authors"]:
        lines.append(f"AU  - {a['family']}, {a['given']}".rstrip(", "))
    lines.append(f"TI  - {d['title']}")
    if d["journal"]:
        lines.append(f"T2  - {d['journal']}")
    p = d["date_parts"]
    if p:
        lines.append(f"PY  - {p[0]}")
        if len(p) >= 3:
            lines.append(f"DA  - {p[0]}/{p[1]:02d}/{p[2]:02d}")
    if d["volume"]:
        lines.append(f"VL  - {d['volume']}")
    if d["issue"]:
        lines.append(f"IS  - {d['issue']}")
    sp, ep = _split_pages(d["page"])
    if sp:
        lines.append(f"SP  - {sp}")
    if ep:
        lines.append(f"EP  - {ep}")
    if d["publisher"]:
        lines.append(f"PB  - {d['publisher']}")
    lines.append(f"DO  - {d['doi']}")
    lines.append(f"UR  - https://doi.org/{d['doi']}")
    lines.append("ER  - ")
    return "\r\n".join(lines) + "\r\n"


def to_endnote(d: dict) -> str:
    lines = ["%0 Journal Article"]
    for a in d["authors"]:
        lines.append(f"%A {a['family']}, {a['given']}".rstrip(", "))
    lines.append(f"%T {d['title']}")
    if d["journal"]:
        lines.append(f"%J {d['journal']}")
    if d["date_parts"]:
        lines.append(f"%D {d['date_parts'][0]}")
    if d["volume"]:
        lines.append(f"%V {d['volume']}")
    if d["issue"]:
        lines.append(f"%N {d['issue']}")
    if d["page"]:
        lines.append(f"%P {d['page']}")
    lines.append(f"%R {d['doi']}")
    lines.append(f"%U https://doi.org/{d['doi']}")
    return "\n".join(lines) + "\n"


def _bib_escape(s: str) -> str:
    return s.replace("\\", " ").replace("{", "(").replace("}", ")")


def to_bibtex(d: dict) -> str:
    first = d["authors"][0]["family"] if d["authors"] else "Unknown"
    key_name = re.sub(r"[^A-Za-z]", "", first) or "Unknown"
    year = str(d["date_parts"][0]) if d["date_parts"] else "nd"
    key = f"{key_name}{year}"
    authors = " and ".join(
        f"{_bib_escape(a['family'])}, {_bib_escape(a['given'])}".rstrip(", ") for a in d["authors"]
    )
    fields = []
    if authors:
        fields.append(("author", authors))
    fields.append(("title", "{" + _bib_escape(d["title"]) + "}"))
    if d["journal"]:
        fields.append(("journal", _bib_escape(d["journal"])))
    if d["date_parts"]:
        fields.append(("year", year))
    if d["volume"]:
        fields.append(("volume", d["volume"]))
    if d["issue"]:
        fields.append(("number", d["issue"]))
    if d["page"]:
        fields.append(("pages", d["page"].replace("-", "--")))
    fields.append(("doi", d["doi"]))
    fields.append(("url", f"https://doi.org/{d['doi']}"))
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
    return f"@article{{{key},\n{body}\n}}\n"


def authors_from_json(raw: str) -> list[str]:
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return [raw] if raw else []
