from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, papers, api

# Create tables (use Alembic for production migrations)
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
    max_age=60 * 60 * 24 * 7,  # 7 days
    https_only=(settings.ORCID_ENV == "production"),
    same_site="lax",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(papers.router)
app.include_router(api.router)
