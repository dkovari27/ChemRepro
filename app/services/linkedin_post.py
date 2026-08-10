"""
LinkedIn post generator for ChemRepro.

Template system based on chemrepro_linkedin_templates.md (Opus output).
Uses condition-linked templates: 5A/5B (5-star), 4A/4B (4-star), 3A/3B (3-star).
12A/12B (1-2 star), EF (extension_failed) and INC (inconclusive) are dormant per the
legal-shield policy in the spec: no entity, no ToS, no takedown route yet.

Anti-repeat rotation state is persisted in linkedin_rotation_state.json (project root).
Only one template block is injected into Haiku's prompt at a time (per section 6 of spec).
"""
import json
import random
from pathlib import Path

import anthropic

from app.config import settings

_STATE_FILE = Path(__file__).parent.parent.parent / "linkedin_rotation_state.json"

_EXCLUDED_FAILURE_CONTEXTS = {"extension_failed", "inconclusive"}


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility
# ─────────────────────────────────────────────────────────────────────────────

def is_eligible_for_post(nd_star: int | None, nd_failure_context: str | None) -> bool:
    """Return True if this review may appear in the LinkedIn draft queue."""
    if nd_star is None or nd_star < 3:
        return False
    if nd_failure_context in _EXCLUDED_FAILURE_CONTEXTS:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Rotation state (JSON sidecar, persists between manual generations)
# ─────────────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "last_labels": [],    # last 6 template labels used
        "last_closings": [],  # last 4 closing move IDs used
        "last_rhythm": None,  # last rhythm profile ID used
    }


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Template library (one block per label, injected into prompt individually)
# ─────────────────────────────────────────────────────────────────────────────

_TEMPLATES: dict[str, tuple[str, str]] = {

    "5A": ("5A — The Claim Restated", """\
Condition: 5-star review, clean reproduction, no significant extension.

Opening hook mechanic: Open by restating the specific operational claim the paper makes, in the paper's own terms, as a proposition still open at the moment of writing. The first sentence is the paper's promise, not the outcome. The reader does not yet know where this is going.

Narrative arc:
1. The claim as published: what transformation, what conditions, what the paper asserts about scope or practicality.
2. An independent chemist took the procedure to the bench, and what came back matched the written record on the points that matter: yield range, purity, timing, workup behaviour.
3. Zoom out: reproducible procedures are the ones that get used, cited and built on; this record now carries an independent data point.

Tone: Measured, factual, quietly confident. No superlatives, no exclamation, no enthusiasm language. The restraint is the point.
Foreground: paper_title, journal, year, procedural specifics from observation_excerpt.
Downplay: career_stage, DOI.
Empty-excerpt fallback: Stay at the level of the claim and the fact of independent execution. Do not fabricate yields.

Example opening: "[PAPER TITLE], published in [JOURNAL] in [YEAR], sets out a procedure its authors describe as operationally simple and tolerant of moisture."\
"""),

    "5B": ("5B — The Boundary Test", """\
Condition: 5-star review where the reviewer extended, adapted or pushed the chemistry beyond the reported scope, and it held.

Opening hook mechanic: Open with the question a working chemist asks about any published method, phrased as a boundary probe: what happens outside the substrate table. The first sentence poses the question; the post answers it.

Narrative arc:
1. The boundary question: published scope tables are chosen, and the useful question is always what sits just outside them.
2. A verified reviewer took the chemistry somewhere the paper did not go: a different substrate class, a different scale, a different solvent regime, whatever observation_excerpt supports.
3. The chemistry held its shape there. Note what that suggests about robustness without overclaiming generality from one experiment.

Tone: Curious, forward-leaning, exploratory.
Foreground: The extension itself from observation_excerpt; career_stage if present.
Downplay: Journal prestige, year; do not dwell on the original paper's framing.
Empty-excerpt fallback: Do not use this template; fall back to 5A. An extension post with no extension detail is empty.

Example opening: "Every scope table ends somewhere, and the more interesting question is usually what sits one substrate past the last entry."\
"""),

    "4A": ("4A — The Transfer Inventory", """\
Condition: 4-star review, mostly successful, minor deviations.

Opening hook mechanic: Open with the general observation that procedures lose something in transit between labs, framed as a normal property of experimental work rather than a failing. The first sentence is about the gap between paper and bench in the abstract; the post then makes it concrete.

Narrative arc:
1. The transit problem: a written procedure is a compressed account, and some of what a lab knows never makes it onto the page.
2. Inventory of what carried across intact: the core transformation, reagent stoichiometry, the outcome. State these positively and specifically.
3. Inventory of what needed local adjustment: the small deviations from observation_excerpt, described as adjustments rather than problems.

Tone: Practical, workmanlike, generous. Avoid drama; this template is deliberately unexcited.
Foreground: observation_excerpt structured as what held and what shifted.
Downplay: year, DOI, career_stage.
Empty-excerpt fallback: Keep beats 1 and 3; replace beat 2 with the point that most procedures need minor local calibration; lean the closing harder on soliciting detail.

Example opening: "A published procedure is a compressed account of what happened, and compression always costs something."\
"""),

    "4B": ("4B — The Bench Scene", """\
Condition: 4-star review, mostly successful, minor deviations.

Opening hook mechanic: Open inside a concrete moment at the bench: a specific physical observation, a colour change, a TLC plate, a slow-forming precipitate, a reaction left overnight. One sensory detail, present-tense feel, no context yet. Widen only in sentence two.

Narrative arc:
1. The scene: one concrete bench moment drawn from observation_excerpt, unexplained.
2. Pull back and place it: this is a verified chemist working through the procedure in [PAPER TITLE], [JOURNAL] [YEAR].
3. Resolve: the chemistry got where the paper said it would, with a small detour on the way, and that detour is now on the record for the next person.

Tone: Vivid, human, grounded. Resist editorialising; the scene carries it.
Foreground: One specific physical detail from observation_excerpt. career_stage fits naturally here.
Downplay: DOI, journal prestige, any framing of significance.
Empty-excerpt fallback: Do not use; fall back to 4A. This template cannot run without a concrete bench detail.

Example opening: "The reaction had gone from pale yellow to something closer to brown by the two-hour mark, which is not what the procedure describes."\
"""),

    "3A": ("3A — The Written and the Executed", """\
Condition: 3-star review, worked but with notable caveats or required modifications.

Opening hook mechanic: Open by naming the distance between the procedure as written and as actually executed, stated as a general methodological fact and immediately localised to this paper. Diagnostic register, no scene, no question.

Narrative arc:
1. The written procedure for [PAPER TITLE] specifies a particular set of conditions.
2. Reaching the described outcome required departing from those conditions in specific ways: the modifications from observation_excerpt, listed plainly.
3. State what that gap means practically without judging it: the chemistry is accessible, and the route there is longer than the page suggests.

Tone: Dry, precise, unsentimental. No warmth, no invitation, no question. The most clinical template in the set.
Foreground: The specific modifications; journal and year for anchoring.
Downplay: career_stage.
Empty-excerpt fallback: State that reaching the described outcome required departures from the written conditions, keep it at that level of generality, end on the record point.

Example opening: "There is often a distance between a procedure as written and the same procedure as actually run, and for [PAPER TITLE] that distance is measurable."\
"""),

    "3B": ("3B — The Variable Nobody Reports", """\
Condition: 3-star review, worked but with notable caveats or required modifications.

Opening hook mechanic: Open with a question about a single experimental variable, posed as something the literature rarely quantifies: water content, stirring rate, addition order, reagent age, batch source. The reviewer's experience is the answer.

Narrative arc:
1. The question about the variable, posed generally.
2. This paper's chemistry supplied an answer: the variable turned out to be load-bearing, in the specific way observation_excerpt describes.
3. Generalise carefully: sensitivity to an unreported variable is not a defect of the paper, it is information that only surfaces when someone else runs it.

Tone: Inquisitive, teacherly, collegial.
Foreground: The single variable. One variable only; do not list three.
Downplay: paper_title can sit later rather than in sentence one; DOI, year light.
Empty-excerpt fallback: Do not use; fall back to 3A. The template is built around a specific variable.

Example opening: "How much does the age of the reagent bottle actually matter? For most published procedures, there is no way to know from the page."\
"""),
}


# ─────────────────────────────────────────────────────────────────────────────
# Closing moves (C1-C4, safe for all eligible templates per valence constraint)
# ─────────────────────────────────────────────────────────────────────────────

_CLOSING_MOVES: dict[str, tuple[str, str]] = {
    "C1": (
        "C1 — Name the beneficiary",
        "Close by stating concretely who this record is now useful to and for what decision. "
        "Be specific (e.g. 'Anyone planning this step on a synthesis route now has a second data point.').",
    ),
    "C2": (
        "C2 — Open question to the reader",
        "Close by posing a live question about the same chemistry in the reader's own hands. "
        "A genuine invitation to compare notes, not a rhetorical device.",
    ),
    "C3": (
        "C3 — Invite the tacit detail",
        "Close by asking readers who have run this chemistry to contribute the practical knowledge "
        "the paper could not fit: the batch source, the stirring rate, the workup quirk.",
    ),
    "C4": (
        "C4 — Name the adjacent unknown",
        "Close by identifying the next unanswered question and asking who has tried it. "
        "Name the specific extension or follow-up that would be most informative.",
    ),
}


def _select_closing(state: dict) -> str:
    """Return the closing move ID least recently used (excludes last 4)."""
    last = state.get("last_closings", [])
    available = [k for k in _CLOSING_MOVES if k not in last[-4:]]
    if not available:
        available = list(_CLOSING_MOVES.keys())
    return random.choice(available)


# ─────────────────────────────────────────────────────────────────────────────
# Rhythm profiles
# ─────────────────────────────────────────────────────────────────────────────

_RHYTHMS: dict[str, tuple[str, str]] = {
    "R1": (
        "R1 — Single block",
        "Write the entire post as one unbroken paragraph. Dense, reads as a considered note. "
        "Suits 3A, 5A and dry-register posts.",
    ),
    "R2": (
        "R2 — Three movements",
        "Three short paragraphs (one per narrative beat), separated by blank lines. "
        "The default; suits all templates.",
    ),
    "R3": (
        "R3 — Cold open",
        "One or two lines standing alone, then a blank line, then the body as one or two paragraphs. "
        "Highest scroll-stopping power; suits 4B, 3B.",
    ),
}


def _select_rhythm(state: dict) -> str:
    """Return rhythm profile ID. Weighted 25/50/25 (R1/R2/R3); excludes previous."""
    last = state.get("last_rhythm")
    weights = {"R1": 1, "R2": 2, "R3": 1}
    if last and last in weights:
        weights[last] = 0
    pool: list[str] = []
    for k, w in weights.items():
        pool.extend([k] * w)
    if not pool:
        pool = ["R2"]
    return random.choice(pool)


# ─────────────────────────────────────────────────────────────────────────────
# Template selection
# ─────────────────────────────────────────────────────────────────────────────

def _select_template(nd_star: int, has_observation: bool, state: dict) -> str:
    """
    Return a template label ('5A'/'5B', '4A'/'4B', '3A'/'3B').
    Within each tier, alternates between A and B. B variant requires an observation.
    """
    # Clamp to the defined tiers: 3, 4, 5
    if nd_star not in (3, 4, 5):
        return "5A"
    a = f"{nd_star}A"
    b = f"{nd_star}B"

    # B variants need an observation excerpt per the spec
    if not has_observation:
        return a

    # Alternate within the tier: if the most recent tier usage was B, use A, and vice versa
    last_labels: list[str] = state.get("last_labels", [])
    tier_set = {a, b}
    last_in_tier = next((lbl for lbl in reversed(last_labels) if lbl in tier_set), None)
    return a if last_in_tier == b else b


# ─────────────────────────────────────────────────────────────────────────────
# Prompt assembly
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_RULES_TMPL = """\
## Global rules (always apply)

Format:
- {word_target} words (stay within 15 of this number), excluding the URL line and hashtags.
- Third person, from ChemRepro's institutional voice. Never "I", never "we tried".
- No em dashes. Use commas, semicolons or colons instead.
- Blank line, then the paper URL alone on its own line.
- Blank line, then 3 to 5 hashtags. #ChemRepro always. Others matched to the actual chemistry.

Never:
- Never state, imply, approximate or gesture at the star rating. No "high marks", "top score", "did not fare well", "rated poorly", "glowing", "damning".
- Never name, number or characterise the reviewer beyond career_stage, and only where the template calls for it.
- Never allege misconduct, fraud, fabrication or negligence. Discrepancies are observed differences, never intent.
- Never write "the reviewer gave", "scored", "rated". Write what was observed, not what was judged.
- Never quote more than one fragment of observation_excerpt, and never longer than 15 words. Paraphrase the rest.

Attribution language: use "reported", "observed", "noted", "found", "did not reproduce under the conditions tried".
Avoid: "failed", "wrong", "false", "debunked", "does not work" as a general claim. A single reviewer report is one data point.

If observation_excerpt is empty: do not invent chemical detail. Shift weight to paper_title, journal, year and general template framing.
If career_stage is empty: omit silently. Never write "an anonymous reviewer"; use "a verified reviewer" or drop the clause.\
"""

_CHECKLIST = """\
## Pre-publish checklist (verify before returning)

1. Word count close to the target stated in the global rules (±15 words), excluding URL and hashtags?
2. Zero em dashes?
3. No number, adjective or phrase that maps to a star rating?
4. Reviewer unidentified beyond career_stage?
5. Third person throughout?
6. paper_url on its own line, nothing after it except hashtags?
7. Between 3 and 5 hashtags, #ChemRepro among them?
8. Attribution language only ("reported", "observed", "noted", "found")?
9. Quoted material from observation_excerpt under 15 words?
10. Opening matches the template's stated mechanic?
11. Closing move is the one specified below?\
"""


def _build_prompt(
    label: str,
    closing_id: str,
    rhythm_id: str,
    paper_title: str,
    journal: str | None,
    year: int | None,
    doi: str,
    observation: str | None,
    career_stage: str | None,
    site_url: str,
    word_target: int = 120,
) -> str:
    template_name, template_text = _TEMPLATES[label]
    closing_name, closing_desc = _CLOSING_MOVES[closing_id]
    rhythm_name, rhythm_desc = _RHYTHMS[rhythm_id]

    paper_url = f"{site_url.rstrip('/')}/paper/{doi}"
    journal_info = (
        f"{journal}, {year}" if journal and year
        else (str(year) if year else (journal or ""))
    )
    obs_snippet = (observation or "").strip()[:600]
    reviewer_info = f"Career stage: {career_stage}" if career_stage else "Career stage: (not provided)"
    global_rules = _GLOBAL_RULES_TMPL.format(word_target=word_target)

    return (
        f"{global_rules}\n\n"
        f"---\n\n"
        f"## Structural template: {template_name}\n\n"
        f"{template_text}\n\n"
        f"---\n\n"
        f"## Closing move to use (override the template's default)\n\n"
        f"{closing_name}: {closing_desc}\n\n"
        f"---\n\n"
        f"## Paragraph rhythm\n\n"
        f"{rhythm_name}: {rhythm_desc}\n\n"
        f"---\n\n"
        f"## Paper and review data\n\n"
        f'Paper: "{paper_title}"{f" ({journal_info})" if journal_info else ""}\n'
        f"Paper URL: {paper_url}\n"
        f"Observation excerpt (up to 600 chars): "
        f"{obs_snippet if obs_snippet else '(no written observation — use the empty-excerpt fallback)'}\n"
        f"{reviewer_info}\n\n"
        f"---\n\n"
        f"{_CHECKLIST}\n\n"
        f"Return only the post text, no preamble or commentary."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main generation function
# ─────────────────────────────────────────────────────────────────────────────

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
    Returns an empty string on failure or for ineligible reviews.
    """
    if not settings.ANTHROPIC_API_KEY:
        return ""

    if nd_star is None or not is_eligible_for_post(nd_star, nd_failure_context):
        return ""

    state = _load_state()

    obs_text = (observation or "").strip()
    has_obs = bool(obs_text)
    label = _select_template(nd_star, has_obs, state)
    closing_id = _select_closing(state)
    rhythm_id = _select_rhythm(state)

    # Scale post length to review length: max 60% longer, floor 80, ceiling 180.
    # No observation: default to 100 words so the post is still meaningful.
    obs_word_count = len(obs_text.split()) if obs_text else 0
    word_target = (
        max(80, min(180, int(obs_word_count * 1.6)))
        if obs_word_count > 0
        else 100
    )

    prompt = _build_prompt(
        label=label,
        closing_id=closing_id,
        rhythm_id=rhythm_id,
        paper_title=paper_title,
        journal=journal,
        year=year,
        doi=doi,
        observation=observation,
        career_stage=career_stage,
        site_url=site_url,
        word_target=word_target,
    )

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        draft = message.content[0].text.strip()
    except Exception:
        return ""

    if not draft:
        return ""

    # Persist rotation state so the next generation picks a different variant
    last_labels: list[str] = state.get("last_labels", [])
    last_labels.append(label)
    state["last_labels"] = last_labels[-6:]

    last_closings: list[str] = state.get("last_closings", [])
    last_closings.append(closing_id)
    state["last_closings"] = last_closings[-4:]

    state["last_rhythm"] = rhythm_id

    _save_state(state)
    return draft


# ─────────────────────────────────────────────────────────────────────────────
# DB entry point (used by the admin manual-generate endpoint)
# ─────────────────────────────────────────────────────────────────────────────

def generate_linkedin_post_for_rating(rating_id: int) -> None:
    """
    Fetch the rating and paper from DB, generate a draft, store it.
    Called from admin router only (no longer a background task on review submit).
    """
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models.paper import Paper
    from app.models.rating import Rating

    with Session(engine) as db:
        rating = db.get(Rating, rating_id)
        if not rating:
            return
        if not is_eligible_for_post(rating.nd_star, rating.nd_failure_context):
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
