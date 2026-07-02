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
            return value.startswith("/images/")
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


def register_globals(templates_instance) -> None:
    templates_instance.env.globals["design_base"] = design_base
    templates_instance.env.globals["design_ver"] = design_ver
    templates_instance.env.filters["render_md"] = render_md
