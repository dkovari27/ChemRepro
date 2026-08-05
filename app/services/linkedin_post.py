"""
Generate a LinkedIn post draft for ChemRepro's company page
whenever a new review is submitted.

Called as a background task; result is stored in Rating.linkedin_post_draft.
"""
import anthropic

from app.config import settings

# Star labels used when building the prompt
_STAR_LABELS = {
    1: "1 star (major issues or failed reproduction)",
    2: "2 stars (significant problems encountered)",
    3: "3 stars (mixed — worked with notable caveats)",
    4: "4 stars (mostly successful with minor issues)",
    5: "5 stars (clean, full reproduction / extension)",
}

_FAILURE_LABELS = {
    "extension_failed": "attempted an extension that failed",
    "inconclusive":     "had inconclusive results",
}


def generate_linkedin_post(
    paper_title: str,
    journal: str | None,
    year: int | None,
    doi: str,
    nd_star: int | None,
    nd_failure_context: str | None,
    observation: str | None,
    career_stage: str | None,
    site_url: str = "https://chemrepro.org",
) -> str:
    """
    Call Claude Haiku and return a LinkedIn post draft as plain text.
    Returns an empty string on failure (no key configured, network error, etc.).
    """
    if not settings.ANTHROPIC_API_KEY:
        return ""

    # Build a human-readable outcome description
    if nd_star is not None:
        outcome_desc = _STAR_LABELS.get(nd_star, f"{nd_star}/5 stars")
    elif nd_failure_context:
        outcome_desc = _FAILURE_LABELS.get(nd_failure_context, "an inconclusive result")
    else:
        outcome_desc = "a result (star rating pending)"

    # Truncate observation to avoid token waste
    obs_snippet = (observation or "").strip()[:600]

    journal_info = f" ({journal}, {year})" if journal and year else (f", {year}" if year else "")

    reviewer_context = f"The reviewer is a {career_stage}." if career_stage else ""

    paper_url = f"{site_url.rstrip('/')}/paper/{doi}"

    prompt = f"""Write a short LinkedIn post (150-200 words) for ChemRepro's company LinkedIn page
announcing that a new reproducibility review has just been submitted.

ChemRepro (https://chemrepro.org) is a community platform where synthetic chemists share
verified, first-hand reproducibility experiences about published chemistry reactions.
Reviewers log in with their ORCID iDs so entries are verified, but their identities are
never disclosed publicly.

Details of this review:
- Paper: "{paper_title}"{journal_info}
- DOI: {doi}
- Outcome: {outcome_desc}
- Reviewer observation (excerpt): {obs_snippet if obs_snippet else "(no written observation)"}
- {reviewer_context}

Guidelines:
- Write in the third person from ChemRepro's perspective (e.g. "A new review just landed on ChemRepro...")
- Do NOT identify or hint at the reviewer's identity
- Keep the tone professional but engaging, suitable for a chemistry-audience LinkedIn post
- Reference the paper title and journal naturally (no need to spell out the DOI)
- End with a link to the paper: {paper_url}
- Add 3-5 relevant hashtags at the end (e.g. #ReproducibilityInChemistry #OrganicChemistry #ChemRepro)
- Do NOT use em dashes. Use commas, semicolons, or colons instead.
- Return only the post text, no preamble or commentary."""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        return ""


def generate_linkedin_post_for_rating(rating_id: int) -> None:
    """
    Background-task entry point.
    Fetches the rating + paper from DB, generates draft, stores it.
    """
    from sqlalchemy.orm import Session
    from app.database import engine
    from app.models.rating import Rating
    from app.models.paper import Paper

    with Session(engine) as db:
        rating = db.get(Rating, rating_id)
        if not rating:
            return
        paper = db.get(Paper, rating.doi)
        if not paper:
            return

        draft = generate_linkedin_post(
            paper_title=paper.title or "",
            journal=paper.journal,
            year=paper.year,
            doi=rating.doi,
            nd_star=rating.nd_star,
            nd_failure_context=rating.nd_failure_context,
            observation=rating.reproducibility_observation,
            career_stage=rating.career_stage_snapshot,
        )
        if draft:
            rating.linkedin_post_draft = draft
            db.commit()
