from fastapi import Request


def design_base(request: Request) -> str:
    return "base_v1.html" if request.session.get("design_ver") == "v1" else "base.html"


def design_ver(request: Request) -> str:
    return request.session.get("design_ver") or "v2"


def register_globals(templates_instance) -> None:
    templates_instance.env.globals["design_base"] = design_base
    templates_instance.env.globals["design_ver"] = design_ver
