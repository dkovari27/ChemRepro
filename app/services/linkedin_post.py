"""
LinkedIn post generator for ChemRepro.

Template system based on chemrepro_linkedin_templates.md.
Twelve outcome templates: 5A/5B (major extension), 4A/4B (minor extension),
3A/3B (reproduced as published), 2A/2B (reproduced with deviation),
1A/1B (did not work), EF (extension failed), INC (inconclusive).

Anti-repeat rotation state is persisted in linkedin_rotation_state.json (project root).
State updates ONLY on publish (when Daniel clicks Posted), not on generation.
"""
import json
import random
import re
from pathlib import Path

import anthropic

from app.config import settings

_STATE_FILE = Path(__file__).parent.parent.parent / "linkedin_rotation_state.json"


# ─────────────────────────────────────────────────────────────────────────────
# Rotation state (JSON sidecar, updates only on publish)
# ─────────────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "last_labels": [],    # last 6 template labels published (not generated)
        "last_closings": [],  # last 4 closing move IDs published
        "last_rhythm": None,  # last rhythm profile ID published
    }


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def update_rotation_on_publish(label: str, closing_id: str, rhythm_id: str) -> None:
    """
    Call when a draft is published to LinkedIn (status set to 'posted').
    Updates rotation state so the next generation picks a different variant.
    """
    if not (label and closing_id and rhythm_id):
        return
    state = _load_state()

    last_labels: list[str] = state.get("last_labels", [])
    last_labels.append(label)
    state["last_labels"] = last_labels[-6:]

    last_closings: list[str] = state.get("last_closings", [])
    last_closings.append(closing_id)
    state["last_closings"] = last_closings[-4:]

    state["last_rhythm"] = rhythm_id
    _save_state(state)


# ─────────────────────────────────────────────────────────────────────────────
# Template library (12 outcome templates; 4 event templates are manual-only)
# ─────────────────────────────────────────────────────────────────────────────

_TEMPLATES: dict[str, tuple[str, str]] = {

    "5A": ("5A: The Boundary Test", """\
Condition: 5 stars: major extension. The reviewer extended the chemistry to a genuinely new \
functional group class and it held.

Opening hook mechanic: Open with the question a working chemist asks about any published method, \
phrased as a boundary probe: what happens outside the substrate table. The first sentence poses \
the question; the post answers it. Do NOT reuse the example opening below; generate a fresh \
entry point each time.

Narrative arc:
1. The boundary question: published scope tables are chosen, and the useful question is always \
what sits just outside them.
2. A verified reviewer took the chemistry somewhere the paper did not go, a new functional group \
class, whatever observation_excerpt supports.
3. The chemistry held its shape there. Note what that suggests about the method's robustness \
without overclaiming generality from one experiment.

Tone: Curious, forward-leaning, exploratory.
Foreground: The extension itself from observation_excerpt; career_stage if present.
Downplay: journal prestige, year. Do not dwell on the original paper's framing.
Empty-excerpt fallback: Do not generate. Flag for Dan. No way to write this without the specific \
functional group detail.

Example opening (register only): \
"Every scope table ends somewhere, and the more interesting question is usually what sits one \
substrate past the last entry."\
"""),

    "5B": ("5B: The New Territory", """\
Condition: 5 stars: major extension, second rotation slot. Same tier as 5A.

Opening hook mechanic: Open with a capability statement, not a question: name the concrete thing \
that becomes possible in a synthesis once a given functional group is known to survive this chemistry. \
Declarative, the inverse of 5A's opening move. Do NOT reuse the example opening below.

Narrative arc:
1. The capability: what a chemist could now route through this transformation that they could not \
confidently route before.
2. The paper's own scope table did not include this functional group class; an independent reviewer \
supplied it, from observation_excerpt.
3. Name what tolerance for this functional group typically costs elsewhere in synthesis (a protecting \
group, an alternate route, a yield penalty) and what it means that this method apparently does not \
charge that cost.

Tone: Confident, applied, practical rather than exploratory.
Foreground: The specific new functional group class and what it costs elsewhere. career_stage if it \
adds practical credibility.
Downplay: journal, year, the original paper's own framing. This is about the capability, not the \
publication.
Empty-excerpt fallback: Do not generate. Flag for Dan. No way to name the specific capability \
without the detail.

Example opening (register only): \
"A method that tolerates a free carboxylic acid without protection is one fewer step in a lot of \
routes that currently need one."\
"""),

    "4A": ("4A: The Adjacent Substrate", """\
Condition: 4 stars: minor extension. The reviewer extended the chemistry to a substrate outside \
the paper's table, within the same functional-group family already demonstrated. No new functional \
group class involved.

Opening hook mechanic: Open by naming the ordinary, unglamorous next question after reading any \
scope table: not "does this work on something totally different" but "does this work on the substrate \
one row down from the ones actually tested." Deliberately smaller in scale than 5A/5B. Do NOT reuse \
the example opening below.

Narrative arc:
1. Scope tables demonstrate a family but rarely every member; the substrate one row over is usually \
left untested, not because it is expected to fail, just because papers have to stop somewhere.
2. A reviewer supplied that missing row, from observation_excerpt: same family the paper already \
demonstrated, a different enough substrate to have been worth checking.
3. Frame the value plainly: not a novel capability claim. This is the unglamorous confirmatory data \
that turns a method people cite into a method people actually reach for.

Tone: Modest, practical, a little dry.
Foreground: The specific adjacent substrate and its relationship to the paper's demonstrated family.
Downplay: Any language that inflates this into a breakthrough; that register belongs to 5A/5B. \
journal, year light.
Empty-excerpt fallback: Do not generate. Flag for Dan. Naming what makes the substrate "adjacent" \
requires the specific detail.

Example opening (register only): \
"The scope table in most methods papers has a family resemblance running through it, and the \
interesting test is usually the cousin that did not make the cut."\
"""),

    "4B": ("4B: The Incremental Win", """\
Condition: 4 stars: minor extension, second rotation slot. Same tier as 4A.

Opening hook mechanic: Open inside a concrete bench moment: one sensory or procedural detail, no \
context yet, widen in sentence two. Do NOT reuse the example opening below.

Narrative arc:
1. The scene: one concrete bench moment from observation_excerpt, unexplained.
2. Pull back and place it: a verified reviewer running the method in [PAPER TITLE], [JOURNAL] [YEAR], \
on a substrate one step outside the paper's own table.
3. Resolve the scene: no new functional group, no headline claim, just the method doing the same \
job on a slightly different input, now on the record.

Tone: Vivid, grounded, understated.
Foreground: One specific physical or procedural detail from observation_excerpt. career_stage fits \
naturally.
Downplay: doi, journal prestige, any framing of significance beyond "it worked here too."
Empty-excerpt fallback: Do not use. Fall back to 4A. This template cannot run without a concrete \
bench detail. If 4A also lacks sufficient detail, do not generate.

Example opening (register only): \
"The flask had been stirring for six hours before the TLC finally showed the spot moving, later \
than the paper's reported time but moving all the same."\
"""),

    "3A": ("3A: The Claim Restated", """\
Condition: 3 stars: reproduced as published. No deviation, no extension.

Opening hook mechanic: Open by restating the specific operational claim the paper makes, in the \
paper's own terms, as a proposition still open at the moment of writing. The first sentence is \
the paper's promise, not the outcome. The reader does not yet know where this is going. Do NOT \
reuse the example opening below.

Narrative arc:
1. The claim as published: what transformation, what conditions, what the paper asserts about \
scope or practicality.
2. An independent chemist took the procedure to the bench, and what came back matched the written \
record on the points that matter: yield range, purity, timing, workup behaviour.
3. Zoom out: reproducible procedures are the ones that get used, cited and built on; this record \
now carries an independent data point.

Tone: Measured, factual, quietly confident. No superlatives, no exclamation, no enthusiasm language. \
The restraint is the point.
Foreground: paper_title, journal, year, the procedural specifics inside observation_excerpt.
Downplay: career_stage, doi.
Empty-excerpt fallback: Stay at the level of the claim and the fact of independent execution. \
Do not fabricate yields.

Example opening (register only): \
"[PAPER TITLE], published in [JOURNAL] in [YEAR], sets out a procedure its authors describe as \
operationally simple and tolerant of moisture."\
"""),

    "3B": ("3B: The Quiet Confirmation", """\
Condition: 3 stars: reproduced as published, second rotation slot. Same tier as 3A.

Opening hook mechanic: Open with a wry observation about what gets published versus what gets \
tested: methods are cited far more often than they are independently run exactly as written. Sets \
the post up as being about the unglamorous, valuable act of just checking. Do NOT reuse the \
example opening below.

Narrative arc:
1. Most citations of a method never involve anyone actually running it; they cite the claim and \
move on.
2. Here, someone did run it, exactly as written, no modification, no extension, and reported back.
3. State plainly why that is worth a post even though nothing dramatic happened: an exact match is \
the quietest possible outcome and the hardest one to manufacture attention for, which is exactly \
why it is worth recording.

Tone: Wry, understated, quietly insistent on the value of boring data.
Foreground: The fact of exact correspondence between written and executed procedure. paper_title, \
journal.
Downplay: career_stage, doi. Resist adding drama that is not there; the whole point is that there \
is not any.
Empty-excerpt fallback: Stay at the level of the claim and the fact of independent, unmodified \
execution. Do not fabricate specifics.

Example opening (register only): \
"Most people who cite a method have never actually run it, which is not a criticism, it is just \
how the literature works."\
"""),

    "2A": ("2A: The Written and the Executed", """\
Condition: 2 stars: reproduced with deviation. Worked but required modifications from the written \
procedure.

Opening hook mechanic: Open by naming the distance between the procedure as written and as actually \
executed, stated as a general methodological fact and immediately localised to this paper. Diagnostic \
register, no scene, no question. Do NOT reuse the example opening below.

Narrative arc:
1. The written procedure for [PAPER TITLE] specifies a particular set of conditions.
2. Reaching the described outcome required departing from those conditions in specific ways: the \
modifications from observation_excerpt, listed plainly.
3. State what that gap means practically without judging it: the chemistry is accessible, and the \
route there is longer than the page suggests.

Tone: Dry, precise, unsentimental. No warmth, no invitation, no question. This is the most clinical \
template in the set; its distinctness depends on staying that way.
Foreground: The specific modifications. journal and year for anchoring.
Downplay: career_stage.
Empty-excerpt fallback: State that reaching the described outcome required departures from the \
written conditions, keep it at that level of generality, and end on the record point.

Example opening (register only): \
"There is often a distance between a procedure as written and the same procedure as actually run, \
and for [PAPER TITLE] that distance is measurable."\
"""),

    "2B": ("2B: The Variable Nobody Reports", """\
Condition: 2 stars: reproduced with deviation, second rotation slot. Same tier as 2A.

Opening hook mechanic: Open with a question about a single experimental variable, posed as something \
the literature rarely quantifies: water content, stirring rate, addition order, reagent age, batch \
source. The reviewer's experience is the answer. Do NOT reuse the example opening below.

Narrative arc:
1. The question about the variable, posed generally.
2. This paper's chemistry supplied an answer: the variable turned out to be load-bearing, in the \
specific way observation_excerpt describes.
3. Generalise carefully: sensitivity to an unreported variable is not a defect of the paper, it \
is information that only surfaces when someone else runs it.

Tone: Inquisitive, teacherly, collegial.
Foreground: The single variable. One variable only; do not list three.
Downplay: paper_title can sit later in the post rather than in sentence one. doi, year light.
Empty-excerpt fallback: Do not use. Fall back to 2A. The template is built around a specific variable.

Example opening (register only): \
"How much does the age of the reagent bottle actually matter? For most published procedures, there \
is no way to know from the page."\
"""),

    "1A": ("1A: The Stakes First", """\
Condition: 1 star: did not work.
STANDING CAUTION: Dan reviews every 1A draft personally before publishing, without exception.

Opening hook mechanic: Open with why the transformation matters if it works: the synthetic problem \
it would solve, the step it would shorten, the reagent it would replace. Establish the value of \
the claim before touching the attempt. Sentence one contains no hint of outcome. Do NOT reuse the \
example opening below.

Narrative arc:
1. The stakes: what [PAPER TITLE] would enable, stated seriously and without irony.
2. A verified chemist ran it. Under the conditions tried, the described outcome did not follow, in \
the specific way observation_excerpt reports.
3. Frame carefully: one report is one report. State explicitly that this is a single independent \
attempt and that the record benefits from more of them, not fewer.

Tone: Sober, careful, non-accusatory. No rhetorical flourish, no bench scene, no wit. Nothing that \
could read as relish.
Foreground: The scientific significance of the claim, and the explicit single-data-point caveat. \
Both are load-bearing, the second legally as well as scientifically.
Downplay: career_stage.
Empty-excerpt fallback: Keep beats 1 and 3; in beat 2 state only that the described outcome did \
not follow under the conditions tried. Do not speculate about causes.

Example opening (register only): \
"A one-step route to [COMPOUND CLASS] under ambient conditions would remove two protecting group \
operations from a lot of synthetic sequences."\
"""),

    "1B": ("1B: The Completeness Audit", """\
Condition: 1 star: did not work, second rotation slot. Same tier as 1A.
STANDING CAUTION: Dan reviews every 1B draft personally before publishing, without exception.

Opening hook mechanic: Open with a systems-level statement about what a procedure has to specify \
in order to be runnable by a stranger, framed as a standard applying to all papers, not this one. \
Localise in sentence two or three. Do NOT reuse the example opening below.

Narrative arc:
1. The standard: a procedure is runnable when a competent chemist with no access to the original \
lab can execute it from the text alone.
2. Applied here: a verified reviewer worked from the published procedure and supporting information, \
and the account did not support execution to the described endpoint. Point at what was absent or \
underspecified, using observation_excerpt.
3. Constructive turn: this is a documentation problem as much as a chemistry problem, and it is \
fixable. Note that authors can respond and clarify on the ChemRepro page.

Tone: Systemic, constructive, unsentimental. Never personalise to the authors.
Foreground: Documentation completeness as the subject. The chemistry is secondary, which is what \
separates this from 1A.
Downplay: Individual chemical detail, career_stage, year.
Empty-excerpt fallback: Run at the level of the general standard and note that execution from the \
published account did not reach the described endpoint. Weight the closing move heavily.

Example opening (register only): \
"A procedure is complete when a chemist who has never spoken to its authors can run it from the \
page alone."\
"""),

    "EF": ("EF: The Adaptation", """\
Condition: Extension failed. The reviewer tried to extend, adapt or repurpose the chemistry and \
the extension did not work.

Opening hook mechanic: Open with the reviewer's intent as a hypothesis: the "what if" that \
motivated the attempt. Sentence one is a plan, not an outcome. The reader is positioned alongside \
the chemist at the point of deciding to try. Do NOT reuse the example opening below.

Narrative arc:
1. The hypothesis: the published chemistry suggested it might transfer to a new context, and here \
is what that context was.
2. The attempt and where it stopped: the boundary the chemistry did not cross, from observation_excerpt.
3. The value of a mapped edge: negative extension data almost never gets published, and knowing \
where a method stops is as useful as knowing where it works. Be explicit that this says nothing \
about the original paper's own claims.

Tone: Reflective, exploratory, matter-of-fact about the boundary.
Foreground: The extension hypothesis and the boundary. The explicit separation between the extension \
result and the paper's own scope.
Downplay: journal, year. Do not let the post read as a criticism of the original work.
Empty-excerpt fallback: Keep the structure at the level of "an attempted extension beyond the \
reported scope did not carry", and lean the closing move on soliciting others' extension attempts.

Example opening (register only): \
"The reasoning was straightforward: if the catalyst tolerates free alcohols, it should tolerate a \
free amine in the same position."\
"""),

    "INC": ("INC: The Open Question", """\
Condition: Inconclusive. Ambiguous results, or the experiment could not be completed as described.

Opening hook mechanic: Open with the unresolved thing itself, stated as a question that currently \
has no answer. Not a rhetorical question, a live one. The post does not resolve it, and that is \
the structure. Do NOT reuse the example opening below.

Narrative arc:
1. The open question, stated cleanly.
2. What was attempted and what blocked resolution: material availability, analytical ambiguity, \
incomplete conversion, whatever observation_excerpt supports. Describe the obstacle, not a conclusion.
3. State plainly that the question remains open and that ChemRepro records it as open rather than \
forcing a verdict.

Tone: Honest, unresolved, inviting. The word "open" or "unresolved" should appear.
Foreground: The obstacle and the request.
Downplay: Any suggestion of a verdict in either direction. No valence.
Empty-excerpt fallback: Run generically: an attempt was made, the outcome could not be resolved, \
the record is open. Closing move becomes a general call for a second independent run.

Example opening (register only): \
"Does the reaction described in [PAPER TITLE] reach full conversion, or does it stall short of it? \
As of this week, that is still an open question."\
"""),
}


# ─────────────────────────────────────────────────────────────────────────────
# Closing moves (C1-C4 safe for all; C5/C6 valence-restricted)
# ─────────────────────────────────────────────────────────────────────────────

_CLOSING_MOVES: dict[str, tuple[str, str]] = {
    "C1": (
        "C1: Name the beneficiary",
        "Close by stating concretely who this record is now useful to and for what decision. "
        "Be specific: 'Anyone planning this step on a synthesis route now has a second data point.'",
    ),
    "C2": (
        "C2: Open question to the reader",
        "Close by posing a live question about the same chemistry in the reader's own hands. "
        "A genuine invitation to compare notes, not a rhetorical device.",
    ),
    "C3": (
        "C3: Invite the tacit detail",
        "Close by asking readers who have run this chemistry to contribute the practical knowledge "
        "the paper could not fit: the batch source, the stirring rate, the workup quirk.",
    ),
    "C4": (
        "C4: Name the adjacent unknown",
        "Close by identifying the next unanswered question and asking who has tried it. "
        "Name the specific extension or follow-up that would be most informative.",
    ),
    "C5": (
        "C5: Call for independent attempts",
        "Close by noting that convergence across several reports is what makes a signal, "
        "and invite more independent runs of this same procedure.",
    ),
    "C6": (
        "C6: Point to the open page",
        "Close by noting that the ChemRepro page for this paper is open to the authors and "
        "other chemists, and that clarification or additional detail is a legitimate outcome "
        "of this process.",
    ),
}

# Valence constraint per spec section 3.1:
# C5 and C6 read as doubt-signalling; only appropriate where doubt is the message.
_C5_C6_FREE = {"1A", "1B", "EF", "INC"}       # freely usable
_C5_C6_OCCASIONAL = {"2A", "2B", "3A", "3B"}  # usable occasionally (~25%)
_C5_C6_NEVER = {"5A", "5B", "4A", "4B"}       # never: extension held, corroboration leaks wrong


def _select_closing(state: dict, template_label: str) -> str:
    """Return a closing move ID respecting valence constraint and anti-repeat."""
    last = state.get("last_closings", [])

    if template_label in _C5_C6_NEVER:
        base_pool = ["C1", "C2", "C3", "C4"]
    elif template_label in _C5_C6_FREE:
        base_pool = list(_CLOSING_MOVES.keys())
    else:
        # Occasional: include C5/C6 only about 25% of the time
        if random.random() < 0.25:
            base_pool = list(_CLOSING_MOVES.keys())
        else:
            base_pool = ["C1", "C2", "C3", "C4"]

    available = [k for k in base_pool if k not in last[-4:]]
    if not available:
        # All recently used; reset to C1-C4 (always safe fallback)
        available = [k for k in base_pool if k in ("C1", "C2", "C3", "C4")]
    if not available:
        available = ["C1", "C2", "C3", "C4"]
    return random.choice(available)


# ─────────────────────────────────────────────────────────────────────────────
# Rhythm profiles
# ─────────────────────────────────────────────────────────────────────────────

_RHYTHMS: dict[str, tuple[str, str]] = {
    "R1": (
        "R1: Single block",
        "Write the entire post as one unbroken paragraph. Dense, reads as a considered note. "
        "Suits 3A, 2A, 1B and short-output posts. This is also the default when word_target is "
        "below 110 because R2 reads as choppy one-line fragments at that length.",
    ),
    "R2": (
        "R2: Three movements",
        "Three short paragraphs (one per narrative beat), separated by blank lines. "
        "The default at typical length; suits all templates.",
    ),
    "R3": (
        "R3: Cold open",
        "One or two lines standing alone, then a blank line, then the body as one or two "
        "paragraphs. Highest scroll-stopping power. Suits 4B, 2B, INC.",
    ),
}


def _select_rhythm(state: dict, word_target: int) -> str:
    """Return rhythm profile ID. Falls back to R1 for short posts; weighted 25/50/25 otherwise."""
    # Below the floor, R2 creates choppy one-line fragments and R3 has no room after the hook
    if word_target < 110:
        return "R1"

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

def _select_template(
    nd_star: int | None,
    nd_failure_context: str | None,
    has_observation: bool,
    state: dict,
) -> tuple[str | None, str | None]:
    """
    Return (template_label, skip_reason).
    If template_label is None: skip_reason explains why ('observation_required', 'unknown_outcome').
    Failure context takes precedence over nd_star.
    """
    # Non-star outcomes (failure context takes precedence)
    if nd_failure_context == "extension_failed":
        return "EF", None
    if nd_failure_context == "inconclusive":
        return "INC", None

    if nd_star not in (1, 2, 3, 4, 5):
        return None, "unknown_outcome"

    # Tiers 5 and 4 require an observation excerpt (the specific functional group is the content)
    if nd_star in (5, 4) and not has_observation:
        return None, "observation_required"

    # For tier 2 without observation: 2B cannot run (it needs a specific variable), use 2A
    # For all other tiers without observation: fall back to the A variant
    if not has_observation:
        return f"{nd_star}A", None

    # Alternate A and B within the tier, based on last published label in this tier
    a = f"{nd_star}A"
    b = f"{nd_star}B"
    last_labels: list[str] = state.get("last_labels", [])
    tier_set = {a, b}
    last_in_tier = next((lbl for lbl in reversed(last_labels) if lbl in tier_set), None)
    # If last was A (or never used), use A; if last was B, switch to B (alternating)
    # Pattern: if never used → A; last was A → B; last was B → A
    return b if last_in_tier == a else a, None


# ─────────────────────────────────────────────────────────────────────────────
# Automatic validator (runs after generation; retry once on failure)
# ─────────────────────────────────────────────────────────────────────────────

_BANNED_RATING_PHRASES = [
    "high marks", "top score", "did not fare well", "rated poorly",
    "glowing", "damning", "strong result", "positive outcome",
]


def _validate_draft(draft: str, word_target: int, paper_url: str) -> list[str]:
    """
    Run mechanical checks on the generated draft.
    Returns a list of failed check descriptions (empty = all pass).
    Checks 1, 2, 6, 7 from the spec's section 7 checklist.
    """
    issues = []

    # Check 2: no em dashes (check for U+2014 em dash and HTML entity)
    if chr(0x2014) in draft or "&mdash;" in draft:
        issues.append("em dash present in draft")

    # Check 6: paper_url on its own line
    if paper_url not in draft:
        issues.append("paper URL missing from draft")
    else:
        url_on_own_line = any(line.strip() == paper_url for line in draft.split("\n"))
        if not url_on_own_line:
            issues.append("paper URL not alone on its own line")

    # Check 7: hashtag count and #ChemRepro
    hashtags = re.findall(r"#\w+", draft)
    if len(hashtags) < 3 or len(hashtags) > 5:
        issues.append(f"hashtag count {len(hashtags)} (need 3 to 5)")
    if "#ChemRepro" not in draft:
        issues.append("#ChemRepro hashtag missing")

    # Check 3: banned rating-adjacent phrases
    for phrase in _BANNED_RATING_PHRASES:
        if phrase.lower() in draft.lower():
            issues.append(f"banned phrase found: \"{phrase}\"")

    # Check 1: word count of post body (excluding URL line and hashtag lines)
    if paper_url in draft:
        body = draft.split(paper_url)[0].strip()
    else:
        body = draft
    body_lines = [ln for ln in body.split("\n") if not ln.strip().startswith("#")]
    body_text = " ".join(body_lines).strip()
    wc = len(body_text.split()) if body_text else 0
    lo, hi = word_target - 15, word_target + 15
    if wc < lo or wc > hi:
        issues.append(f"word count {wc} outside target {word_target}±15 (body only)")

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# Prompt assembly
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_RULES_TMPL = """\
## Global rules (always apply)

Format:
- {word_target} words (soft target: a few words over or under is fine if the sentence needs it; \
do not cut a thought short to hit a number). Excludes the URL line and hashtags.
- Third person, from ChemRepro's institutional voice. Never "I", never "we tried".
- No em dashes. Use commas, semicolons or colons instead.
- Blank line, then the paper URL alone on its own line.
- Blank line, then 3 to 5 hashtags. #ChemRepro always. Others matched to the actual chemistry.

Never:
- Never state, imply, approximate or gesture at the star rating. No "high marks", "top score", \
"did not fare well", "rated poorly", "glowing", "damning", "strong result", "positive outcome", \
or any synonym. The reader should not be able to infer the valence of the rating from the post alone.
- Never name, number or characterise the reviewer beyond career_stage, and only where the template calls for it.
- Never allege misconduct, fraud, fabrication or negligence. Discrepancies are described as \
observed differences, never as intent.
- Never write "the reviewer gave", "scored", "rated". Write what was observed, not what was judged.
- Never quote more than one fragment of observation_excerpt, and never longer than 15 words. \
Paraphrase the rest.
- Do NOT reuse the example opening sentence from the template spec; generate a fresh entry point.

Attribution language: use "reported", "observed", "noted", "found", \
"did not reproduce under the conditions tried". Avoid: "failed", "wrong", "false", "debunked", \
"does not work" as a general claim. A single reviewer report is one data point.

If observation_excerpt is empty: do not invent chemical detail. Shift weight to paper_title, \
journal, year and the general template framing, and use the closing move to solicit the detail \
that is missing.
If career_stage is empty: omit silently. Never write "an anonymous reviewer"; use \
"a verified reviewer" or drop the clause.\
"""

_CHECKLIST = """\
## Pre-publish checklist (verify before returning)

1. Word count close to the target stated in the global rules (soft target, +/- 15 words), excluding URL and hashtags?
2. Zero em dashes?
3. No number, adjective or phrase that maps to a star rating or outcome valence?
4. Reviewer unidentified beyond career_stage?
5. Third person throughout?
6. paper_url on its own line, nothing after it except hashtags?
7. Between 3 and 5 hashtags, #ChemRepro among them?
8. For 1A or 1B: is the single-data-point framing explicit, and is there no language attributing \
intent to the authors?
9. Quoted material from observation_excerpt under 15 words?
10. Opening matches the template's stated mechanic and is NOT the example sentence from the spec?
11. Closing move is the one specified?\
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
    word_target: int = 100,
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
    reviewer_info = (
        f"Career stage: {career_stage}" if career_stage else "Career stage: (not provided)"
    )
    global_rules = _GLOBAL_RULES_TMPL.format(word_target=word_target)

    return (
        f"{global_rules}\n\n"
        f"---\n\n"
        f"## Structural template: {template_name}\n\n"
        f"{template_text}\n\n"
        f"---\n\n"
        f"## Closing move to use\n\n"
        f"{closing_name}: {closing_desc}\n\n"
        f"---\n\n"
        f"## Paragraph rhythm\n\n"
        f"{rhythm_name}: {rhythm_desc}\n\n"
        f"---\n\n"
        f"## Paper and review data\n\n"
        f'Paper: "{paper_title}"{f" ({journal_info})" if journal_info else ""}\n'
        f"Paper URL: {paper_url}\n"
        f"Observation excerpt (up to 600 chars): "
        f"{obs_snippet if obs_snippet else '(no written observation, use the empty-excerpt fallback from the template)'}\n"
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
) -> tuple[str, dict]:
    """
    Call Claude Haiku and return (draft_text, metadata).

    metadata dict keys:
        label       -- template used, e.g. "3A"
        closing_id  -- closing move used, e.g. "C2"
        rhythm_id   -- rhythm profile used, e.g. "R2"
        word_count  -- approximate body word count of the generated draft
        issues      -- list[str] of validator failures (empty = clean pass)

    On hard failure returns ("", {"error": reason_string}).
    Caller should store metadata in rating.linkedin_post_metadata.
    Rotation state is NOT updated here; call update_rotation_on_publish() when the post is published.
    """
    if not settings.ANTHROPIC_API_KEY:
        return "", {"error": "no_api_key"}

    obs_text = (observation or "").strip()
    has_obs = bool(obs_text)

    state = _load_state()
    label, skip_reason = _select_template(nd_star, nd_failure_context, has_obs, state)
    if label is None:
        return "", {"error": skip_reason or "unknown_outcome"}

    # Proportional word target: max 60% longer than source review, floor 80, ceiling 180.
    # No-observation default: 100 words so the post still has substance.
    obs_word_count = len(obs_text.split()) if obs_text else 0
    word_target = (
        max(80, min(180, int(obs_word_count * 1.6)))
        if obs_word_count > 0
        else 100
    )

    closing_id = _select_closing(state, label)
    rhythm_id = _select_rhythm(state, word_target)

    paper_url = f"{site_url.rstrip('/')}/paper/{doi}"

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

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _call_haiku() -> str:
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        except Exception:
            return ""

    draft = _call_haiku()
    if not draft:
        return "", {"error": "api_error"}

    # Validate; regenerate once automatically if checks fail
    issues = _validate_draft(draft, word_target, paper_url)
    if issues:
        draft2 = _call_haiku()
        if draft2:
            issues2 = _validate_draft(draft2, word_target, paper_url)
            # Keep whichever draft has fewer (or no) issues
            if not issues2 or len(issues2) < len(issues):
                draft = draft2
                issues = issues2

    # Approximate body word count for metadata
    if paper_url in draft:
        body = draft.split(paper_url)[0].strip()
    else:
        body = draft
    body_lines = [ln for ln in body.split("\n") if not ln.strip().startswith("#")]
    word_count = len(" ".join(body_lines).split()) if body_lines else 0

    metadata: dict = {
        "label": label,
        "closing_id": closing_id,
        "rhythm_id": rhythm_id,
        "word_count": word_count,
        "issues": issues,
    }

    # NOTE: rotation state (_save_state) is intentionally NOT called here.
    # It is updated only when Daniel clicks "Posted" via update_rotation_on_publish().

    return draft, metadata


# ─────────────────────────────────────────────────────────────────────────────
# DB entry point (used by the admin manual-generate endpoint)
# ─────────────────────────────────────────────────────────────────────────────

def generate_linkedin_post_for_rating(rating_id: int) -> None:
    """
    Fetch the rating and paper from DB, generate a draft, store both draft and metadata.
    Called from admin router only.
    """
    from sqlalchemy.orm import Session

    from app.database import engine
    from app.models.paper import Paper
    from app.models.rating import Rating

    with Session(engine) as db:
        rating = db.get(Rating, rating_id)
        if not rating:
            return
        paper = db.get(Paper, rating.doi)
        if not paper:
            return

        draft, metadata = generate_linkedin_post(
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
            rating.linkedin_post_metadata = metadata
            db.commit()
