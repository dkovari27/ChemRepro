from fastapi import Request


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
