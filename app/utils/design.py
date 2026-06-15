from fastapi import Request


def _is_v1(request: Request) -> bool:
    return request.session.get("design_ver") == "v1"


def design_base(request: Request) -> str:
    return "base_v1.html" if _is_v1(request) else "base.html"


def design_ver(request: Request) -> str:
    return request.session.get("design_ver") or "v2"


def index_tpl(request: Request) -> str:
    return "index_v1.html" if _is_v1(request) else "index.html"


def paper_tpl(request: Request) -> str:
    return "paper_v1.html" if _is_v1(request) else "paper.html"


def paper_classic_tpl(request: Request) -> str:
    return "paper_classic_v1.html" if _is_v1(request) else "paper_classic.html"


def register_globals(templates_instance) -> None:
    templates_instance.env.globals["design_base"] = design_base
    templates_instance.env.globals["design_ver"] = design_ver
