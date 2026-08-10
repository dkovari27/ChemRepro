import re

_BLOCKED_RE = re.compile(
    r'\b(fuck(?:er|ing|s|ed)?|shit(?:ting)?|bullshit|cunts?|bitches?|ass(?:hole|holes)'
    r'|arsehole|bastards?|cocks?|dicks?|puss(?:y|ies)|whores?|sluts?|pricks?'
    r'|wankers?|tossers?|twats?|bollocks|nigg(?:er|ers|a|as)|fagg?ots?|retards?'
    r'|spics?|kikes?|chinks?|gooks?|wetbacks?|trann(?:y|ies)|dykes?|cracker)\b',
    re.IGNORECASE,
)


def get_banned_terms() -> list[str]:
    """Admin-curated word/phrase list from the DB (app.models.banned_term.BannedTerm).
    Uses its own short-lived session so callers never need to thread `db` through."""
    from app.database import SessionLocal
    from app.models.banned_term import BannedTerm

    db = SessionLocal()
    try:
        return [t.term for t in db.query(BannedTerm).order_by(BannedTerm.term.asc()).all()]
    except Exception:
        return []
    finally:
        db.close()


def _custom_terms_re(terms: list[str]) -> re.Pattern | None:
    if not terms:
        return None
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r'\b(' + '|'.join(escaped) + r')\b', re.IGNORECASE)


def is_clean(*texts: str | None) -> bool:
    custom_re = _custom_terms_re(get_banned_terms())
    for t in texts:
        if not t:
            continue
        if _BLOCKED_RE.search(t):
            return False
        if custom_re and custom_re.search(t):
            return False
    return True


def _find_matched_term(*texts: str | None) -> str | None:
    """Returns the exact banned word/phrase found in `texts`, or None if clean."""
    custom_re = _custom_terms_re(get_banned_terms())
    for t in texts:
        if not t:
            continue
        m = _BLOCKED_RE.search(t)
        if m:
            return m.group(0)
        if custom_re:
            m = custom_re.search(t)
            if m:
                return m.group(0)
    return None


# ── Repeated-violation warning system ──────────────────────────────────────
# Every blocked submit attempt on a given (orcid_id, doi) pair is logged as
# evidence (SubmissionWarning). The 3rd one on the same paper flips
# User.submission_blocked, restricting that account from posting anywhere on
# the site until an admin clears it from /admin/submission-warnings.

WARNING_LIMIT = 3

BLOCKED_MESSAGE = (
    "Your account has been restricted from posting anywhere on ChemRepro "
    "due to repeated content violations."
)


def enforce_moderation(db, orcid_id: str, doi: str, content_type: str, *texts: str | None) -> None:
    """Central moderation gate for every review/comment/reply submit and edit.

    Raises HTTPException(403) if the account is already blocked, or if this
    call is the 3rd logged warning on this paper (which blocks it now).
    Raises HTTPException(422) with the running warning count for a 1st/2nd
    violation. Returns None (no-op) if `texts` pass moderation and the
    account isn't blocked. Call this before constructing/committing any
    content object, exactly where the old `if not is_clean(...)` checks were.
    """
    from fastapi import HTTPException
    from sqlalchemy import func as _func
    from sqlalchemy.exc import IntegrityError
    from app.models.user import User
    from app.models.submission_warning import SubmissionWarning

    user = db.get(User, orcid_id)
    if user and user.submission_blocked:
        raise HTTPException(status_code=403, detail={
            "code": "submission_blocked",
            "message": BLOCKED_MESSAGE,
        })

    term = _find_matched_term(*texts)
    if term is None:
        return

    db.add(SubmissionWarning(
        orcid_id=orcid_id,
        doi=doi,
        content_type=content_type,
        matched_term=term,
        content_snippet=" ".join(t for t in texts if t)[:500],
    ))
    try:
        db.flush()
    except IntegrityError:
        # doi (or, in principle, orcid_id) doesn't reference an existing row,
        # e.g. a bad-word submission against a tampered/stale URL. Every call
        # site checks in this codebase run this content check before their
        # own paper/comment/rating existence check, so on Postgres (FK
        # constraints always enforced, unlike local SQLite by default) this
        # would otherwise crash with an unhandled 500 instead of the normal
        # 404 downstream. Skip logging evidence for a target that doesn't
        # exist and let the caller's own existence check 404 as usual.
        db.rollback()
        return

    count = db.query(_func.count(SubmissionWarning.id)).filter(
        SubmissionWarning.orcid_id == orcid_id,
        SubmissionWarning.doi == doi,
    ).scalar()

    if count >= WARNING_LIMIT:
        if user:
            user.submission_blocked = True
        db.commit()
        raise HTTPException(status_code=403, detail={
            "code": "submission_blocked",
            "message": BLOCKED_MESSAGE,
        })

    db.commit()
    raise HTTPException(status_code=422, detail={
        "code": "prohibited_language",
        "warning_count": count,
        "message": "Content contains prohibited language.",
    })
