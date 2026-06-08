from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, papers, api
from app.routers import feedback as feedback_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ChemRepro",
    description="Community reproducibility ratings for synthetic chemistry papers.",
    version="0.1.0",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="chemrepro_session",
    max_age=60 * 60 * 24 * 7,
    https_only=(settings.ORCID_ENV == "production"),
    same_site="lax",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(papers.router)
app.include_router(api.router)
app.include_router(feedback_router.router)

_templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return _templates.TemplateResponse("error.html", {
        "request": request,
        "status_code": exc.status_code,
        "user_name": request.session.get("user_name"),
        "orcid_id": request.session.get("orcid_id"),
    }, status_code=exc.status_code)
