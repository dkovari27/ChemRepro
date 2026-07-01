import re

_BLOCKED_RE = re.compile(
    r'\b(fuck(?:er|ing|s|ed)?|shit(?:ting)?|bullshit|cunts?|bitches?|ass(?:hole|holes)'
    r'|arsehole|bastards?|cocks?|dicks?|puss(?:y|ies)|whores?|sluts?|pricks?'
    r'|wankers?|tossers?|twats?|bollocks|nigg(?:er|ers|a|as)|fagg?ots?|retards?'
    r'|spics?|kikes?|chinks?|gooks?|wetbacks?|trann(?:y|ies)|dykes?|cracker)\b',
    re.IGNORECASE,
)


def is_clean(*texts: str | None) -> bool:
    return all(not (t and _BLOCKED_RE.search(t)) for t in texts)
