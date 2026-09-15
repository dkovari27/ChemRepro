# ChemRepro Review Extraction Prompt

Use this prompt with any AI (Claude, ChatGPT, etc.).
Paste the prompt, then paste the paper text or the relevant excerpt below it.

---

## Prompt (copy everything below this line)

You are helping write a reproducibility review for ChemRepro. I will give you a section from a scientific paper where the authors describe reproducing, extending, or failing to reproduce a previously published reaction or procedure.

Extract the key claim and return ONLY this structured block — no introduction, no explanation, no extra text:

---
TARGET DOI: [DOI of the paper being reproduced — not the citing paper; write UNKNOWN if not stated]
OUTCOME: [number or ?]
FAILURE CONTEXT: [see rules below, or leave blank]
OBSERVATION:
[your text here]
---

**OUTCOME choices:**
- 5: Major extension — scope substantially extended beyond the original
- 4: Minor extension — small extension; original also worked
- 3: Reproduced as published — exact or near-exact procedure, matching outcome
- 2: Reproduced with deviation — reproduced but with different yield, conditions, or scope
- 1: Did not work — procedure failed
- ?: Inconclusive or extension failed — outcome unknown or ambiguous

**FAILURE CONTEXT (only fill when OUTCOME is 1 or ?):**
- If ?: write "inconclusive" or "extension_failed"
- If 1: write "original_tested", "extension_only", or leave blank

**OBSERVATION rules:**
- 2 to 4 sentences maximum; target 60-80 words
- State what was reproduced, at what scale if reported, and the outcome (yield, ee, dr, or other key metric)
- Note whether it matches the original claim
- If the original paper's DOI is known, cite it inline as [[DOI]]
- Use past tense, active voice; no hedging ("appears to", "seems to", "might")
- No interpretation, no summary of the whole paper, only the reproducibility claim

[PASTE YOUR PAPER TEXT HERE]
