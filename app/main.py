from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.utils.design import register_globals
from sqlalchemy import text

from app.database import Base, engine
from app.models import notification as _notif_model          # noqa: F401
from app.models import paper_subscription as _sub_model      # noqa: F401
from app.models import author_notification as _author_model  # noqa: F401
from app.models import message as _message_model             # noqa: F401
from app.models import user_follow as _user_follow_model     # noqa: F401
from app.models import name_suggestion as _name_model        # noqa: F401
from app.models.comment import CommentLike                   # noqa: F401
from app.routers import auth, papers, api
from app.routers import feedback as feedback_router
from app.routers import profile as profile_router
from app.routers import messages as messages_router
from app.routers import follows as follows_router

Base.metadata.create_all(bind=engine)

# Column migrations — safe to run on every startup (no-op after first run)
def _migrate():
    with engine.connect() as conn:
        is_sqlite = str(engine.url).startswith("sqlite")
        if is_sqlite:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(users)"))]
            if "career_stage" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN career_stage VARCHAR(60)"))
            if "career_stage_set" not in cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN career_stage_set BOOLEAN NOT NULL DEFAULT 0"))
            rating_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(ratings)"))]
            if "updated_at" not in rating_cols:
                conn.execute(text("ALTER TABLE ratings ADD COLUMN updated_at DATETIME"))
            comment_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(comments)"))]
            if "parent_id" not in comment_cols:
                conn.execute(text("ALTER TABLE comments ADD COLUMN parent_id INTEGER REFERENCES comments(id)"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS career_stage VARCHAR(60)"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS career_stage_set BOOLEAN NOT NULL DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE ratings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE"))
            conn.execute(text("ALTER TABLE comments ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES comments(id)"))
        conn.commit()

_migrate()

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
app.include_router(profile_router.router)
app.include_router(messages_router.router)
app.include_router(follows_router.router)

_templates = Jinja2Templates(directory="app/templates")
register_globals(_templates)


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
