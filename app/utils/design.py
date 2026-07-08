import json
import re
import bleach
import markdown as _md_lib
from fastapi import Request

_MD_ALLOWED_TAGS = [
    "p", "br", "strong", "em", "b", "i", "code", "pre",
    "ul", "ol", "li", "blockquote", "h3", "h4", "a", "img",
]


def _md_attrs(tag: str, name: str, value: str) -> bool:
    if tag == "a":
        return name in ("href", "title")
    if tag == "img":
        if name == "src":
            return value.startswith("/images/") or value.startswith("https://")
        return name in ("alt", "title")
    return False


def render_md(text: str | None) -> str:
    if not text:
        return ""
    raw_html = _md_lib.markdown(text, extensions=["nl2br"])
    return bleach.clean(raw_html, tags=_MD_ALLOWED_TAGS, attributes=_md_attrs, strip=True)


def _is_v1(request: Request) -> bool:
    return False  # v1 archived; v2 is the only active design


def design_base(request: Request) -> str:
    return "base.html"


def design_ver(request: Request) -> str:
    return "v2"


def index_tpl(request: Request) -> str:
    return "index.html"


def paper_tpl(request: Request) -> str:
    return "paper.html"


def paper_classic_tpl(request: Request) -> str:
    return "paper_classic.html"


def _from_json(value: str) -> list:
    try:
        return json.loads(value)
    except Exception:
        return [value]


# ── Paper reference cards ─────────────────────────────────────────────────────

_DOI_BRACKET_RE = re.compile(r"\[\[([^\]]+)\]\]")
_CHEMREPRO_URL_RE = re.compile(
    r"https?://(?:[\w-]+\.)*chemrepro[\w.-]*/paper/(10\.[^\s\)\]\"'<>#]+)"
)
_DOI_ORG_URL_RE = re.compile(
    r"https?://doi\.org/(10\.[^\s\)\]\"'<>#]+)"
)


def _parse_doi_from_raw(raw: str) -> str | None:
    raw = raw.strip().rstrip("/")
    m = re.match(r"https?://doi\.org/(.+)", raw, re.I)
    if m:
        return m.group(1).rstrip("/")
    m = re.match(r"https?://(?:[\w-]+\.)*chemrepro[\w.-]*/paper/(10\.[^\s\)\]\"'<>#]+)", raw, re.I)
    if m:
        return m.group(1).rstrip("/")
    if raw.startswith("10."):
        return raw
    return None


def collect_doi_refs(texts: list[str]) -> set[str]:
    """Scan a list of text strings and return all DOIs referenced via [[...]], doi.org, or ChemRepro URLs."""
    dois: set[str] = set()
    for text in texts:
        if not text:
            continue
        for m in _DOI_BRACKET_RE.finditer(text):
            doi = _parse_doi_from_raw(m.group(1))
            if doi:
                dois.add(doi)
        for m in _CHEMREPRO_URL_RE.finditer(text):
            dois.add(m.group(1).rstrip("/"))
        for m in _DOI_ORG_URL_RE.finditer(text):
            dois.add(m.group(1).rstrip("/"))
    return dois


def _paper_mini_card(paper) -> str:
    try:
        authors = json.loads(paper.authors)
    except Exception:
        authors = [str(paper.authors)] if paper.authors else []

    if len(authors) > 3:
        author_str = ", ".join(authors[:3]) + " et al."
    elif authors:
        author_str = ", ".join(authors)
    else:
        author_str = ""

    meta_parts = [p for p in [author_str, paper.journal, str(paper.year) if paper.year else ""] if p]
    meta = " &middot; ".join(meta_parts)

    title_esc = (paper.title or paper.doi).replace("<", "&lt;").replace(">", "&gt;")
    doi_esc = paper.doi.replace("<", "&lt;").replace(">", "&gt;")

    return (
        f'<a href="/paper/{paper.doi}" class="paper-ref-card block no-underline group '
        f'bg-white border border-slate-200 rounded-xl px-4 py-2.5 mt-2 '
        f'hover:border-brand hover:shadow-sm transition-all">'
        f'<div class="flex items-start gap-2.5">'
        f'<svg class="w-3.5 h-3.5 text-brand shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
        f'<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'
        f'</svg>'
        f'<div class="flex-1 min-w-0">'
        f'<p class="text-xs font-semibold text-[#111c17] leading-snug mb-0.5 '
        f'group-hover:text-brand transition-colors">{title_esc}</p>'
        f'<p class="text-[11px] text-slate-500 truncate">{meta}</p>'
        f'<p class="text-[10px] font-mono text-slate-400 mt-0.5">{doi_esc}</p>'
        f'</div>'
        f'</div>'
        f'</a>'
    )


def render_md_refs(text: str, papers_by_doi: dict) -> str:
    """Like render_md but converts [[DOI]] and ChemRepro URLs into inline links + appended mini-cards."""
    if not text:
        return ""

    cards: list[str] = []
    seen: set[str] = set()

    def _maybe_add_card(doi: str) -> None:
        if doi not in seen:
            seen.add(doi)
            paper = papers_by_doi.get(doi)
            if paper:
                cards.append(_paper_mini_card(paper))

    def _replace_bracket(m: re.Match) -> str:
        doi = _parse_doi_from_raw(m.group(1))
        if not doi:
            return m.group(0)
        paper = papers_by_doi.get(doi)
        _maybe_add_card(doi)
        label = (paper.title if paper else None) or doi
        return f"[{label}](/paper/{doi})"

    def _replace_chemrepro(m: re.Match) -> str:
        doi = m.group(1).rstrip("/")
        paper = papers_by_doi.get(doi)
        _maybe_add_card(doi)
        label = (paper.title if paper else None) or m.group(0)
        return f"[{label}](/paper/{doi})"

    def _replace_doi_org(m: re.Match) -> str:
        doi = m.group(1).rstrip("/")
        paper = papers_by_doi.get(doi)
        _maybe_add_card(doi)
        label = (paper.title if paper else None) or m.group(0)
        return f"[{label}](/paper/{doi})"

    processed = _DOI_BRACKET_RE.sub(_replace_bracket, text)
    processed = _CHEMREPRO_URL_RE.sub(_replace_chemrepro, processed)
    processed = _DOI_ORG_URL_RE.sub(_replace_doi_org, processed)

    html = render_md(processed)

    if cards:
        html += (
            '<div class="paper-ref-cards mt-3 space-y-1.5 not-prose">'
            + "".join(cards)
            + "</div>"
        )

    return html


def register_globals(templates_instance) -> None:
    from app.config import settings
    templates_instance.env.globals["design_base"] = design_base
    templates_instance.env.globals["design_ver"] = design_ver
    templates_instance.env.globals["is_local"] = settings.ORCID_ENV == "sandbox"
    templates_instance.env.filters["render_md"] = render_md
    templates_instance.env.filters["render_md_refs"] = render_md_refs
    templates_instance.env.filters["from_json"] = _from_json
