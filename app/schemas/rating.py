from datetime import datetime
from pydantic import BaseModel, Field


class RatingCreate(BaseModel):
    outcome: str | None = None
    reproducibility_score: int | None = Field(None, ge=1, le=5)
    reproducibility_observation: str | None = Field(None, max_length=1000)
    scope_level: str | None = None
    scope_observation: str | None = Field(None, max_length=1000)
    modification_details: str | None = Field(None, max_length=1000)


class RatingOut(BaseModel):
    id: int
    doi: str
    outcome: str | None
    reproducibility_score: int | None
    reproducibility_observation: str | None
    scope_level: str | None
    scope_observation: str | None
    modification_details: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AggregatedScores(BaseModel):
    doi: str
    rating_count: int
    avg_reproducibility: float | None
    avg_generalisability: float | None
