from datetime import datetime
from pydantic import BaseModel


class PaperBase(BaseModel):
    doi: str
    title: str
    authors: str
    journal: str | None = None
    year: int | None = None


class PaperCreate(PaperBase):
    pass


class PaperOut(PaperBase):
    fetched_at: datetime

    model_config = {"from_attributes": True}


class PaperWithScores(PaperOut):
    avg_reproducibility: float | None = None
    avg_generalisability: float | None = None
    rating_count: int = 0
