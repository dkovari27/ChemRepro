# ══════════════════════════════════════════════════════════════════════════
# ChemRepro — Review form placeholder / guidance texts
# ══════════════════════════════════════════════════════════════════════════
# Edit the strings below to change what users see inside the text boxes
# on the review form. Save this file; the server picks up changes on
# the next restart (or automatically if you run with --reload).
#
# Keep the text concise — it disappears once the user starts typing.
# ══════════════════════════════════════════════════════════════════════════


# ── Reproducibility section ───────────────────────────────────────────────

REPRO_OBSERVATION = """\
• Which compound did you reproduce? (e.g. compound 5g, 50 mg scale)
• Which method did you use, if more than one is described in the paper?
• Any deviation from the original procedure?
• Any observations worth mentioning?"""


# ── Scope extension section ───────────────────────────────────────────────

SCOPE_OBSERVATION = """\
• Which substrate or scaffold did you test for scope extension?
• Which conditions did you use (solvent, temperature, catalyst, atmosphere)?
• What yield / ee / dr did you observe?
• Any notable differences compared to the original scope?"""


# ── Modification details (shown when a scope level is selected) ───────────

MODIFICATION_DETAILS = """\
• Describe the specific modifications you made to the procedure.
• e.g. different solvent, temperature, catalyst loading, scale, atmosphere."""


# ── Reply / comment box ──────────────────────────────────────────────────

COMMENT_PLACEHOLDER = \
    "Share a method tip, ask a question, or flag an issue with this review…"
