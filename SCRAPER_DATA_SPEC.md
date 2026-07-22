# ChemRepro — Scraper Data Specification (B17)

This document defines what the scraper must produce so the data can be
imported into ChemRepro as review cards. Hand this file to the scraper
before finalising its output schema.

---

## Overview: two-stage pipeline

```
Stage 1 — Scraper (rule-based)
  Source paper (OrgSyn / EuropePMC / etc.)
    → extract raw facts
    → output: JSONL  (one record per reproducibility claim)

Stage 2 — AI Review Writer (Claude agent)
  Takes Stage 1 JSONL
    → assigns nd_star (1-5)
    → writes observation_text
    → output: enriched JSONL, ready for DB import
```

The scraper only handles Stage 1.
Stage 2 (AI enrichment) is a separate script that reads Stage 1 output.
The DB import script reads Stage 2 output.

---

## Stage 1 — Scraper output format

One JSONL file per run. Each line is one reproducibility claim found in
one source paper.

### Required fields

| Field | Type | Notes |
|---|---|---|
| `target_doi` | string | DOI of the paper being reproduced/referenced. Normalised: lowercase, no `https://doi.org/` prefix. |
| `source_name` | string | Name of the source database or publication: `"OrgSyn"`, `"EuropePMC"`, `"ChemRxiv"`, `"RSC_OA"`, `"PMC"`. |
| `source_doi` | string or null | DOI of the source document (the one that contains the reproducibility claim). Null if no DOI (e.g. OrgSyn procedures without a DOI). |
| `source_url` | string or null | Direct URL to the source document. Required if `source_doi` is null. |
| `extracted_sentences` | string | The 1-3 sentences from the source that describe what was done. Verbatim. Max 800 chars. |
| `sentence_id` | string | Unique dedup key: `"{source_doi_or_url}::{paragraph_index}s{sentence_index}"`. Must be stable across re-runs. |
| `scrape_timestamp` | string | ISO 8601 UTC timestamp of when this record was extracted. |

### Recommended fields (include if available)

| Field | Type | Notes |
|---|---|---|
| `source_authors` | string | First 3 authors of the source document, comma-separated. |
| `source_journal` | string | Journal name, book series, or "OrgSyn Collective Volume N". |
| `source_year` | int | Year of source publication. |
| `yield_reported` | float or null | Yield percentage if mentioned in the extracted sentences. |
| `extraction_confidence` | float 0-1 | How confident the scraper is that this is a genuine reproducibility claim. Use ≥ 0.75 as the import threshold. |

### Example Stage 1 record

```json
{
  "target_doi": "10.1021/jacs.2c00001",
  "source_name": "OrgSyn",
  "source_doi": null,
  "source_url": "https://orgsyn.org/demo/orgSynAll/pdfs/CV13P0123.pdf",
  "extracted_sentences": "The procedure of Smith et al. was followed with minor modification to the workup. Compound 3 was isolated in 78% yield (lit. 81%). The lower yield was attributed to the use of technical-grade solvent.",
  "sentence_id": "orgsyn:CV13P0123::p4s1",
  "scrape_timestamp": "2026-07-09T10:00:00Z",
  "source_authors": "Jones A, Müller K, Tanaka R",
  "source_journal": "Org. Synth.",
  "source_year": 2024,
  "yield_reported": 78.0,
  "extraction_confidence": 0.92
}
```

---

## Stage 2 — AI Review Writer output (enriched JSONL)

The AI agent reads Stage 1 JSONL and adds the following fields.
The DB import script reads this enriched file.

### Core review fields

| Field | Type | Notes |
|---|---|---|
| `nd_star` | int 1-5 or null | Star rating. See rubric below. null = inconclusive or extension failed. |
| `nd_failure_context` | string or null | Required when `nd_star` is null: `"extension_failed"` or `"inconclusive"`. |
| `reproducibility_observation` | string | Text shown on review card. 2-4 sentences, max 900 chars. |
| `ai_confidence` | float 0-1 | AI self-assessed confidence in the star assignment. |
| `citing_author` | string or null | First author(s) of the source paper (e.g. "Jones et al."). |
| `is_multi_target` | bool | True if a single sentence cites two or more external papers. |

### Clarification fields (records needing human review before import)

| Field | Type | Notes |
|---|---|---|
| `_needs_clarification` | bool | True when the claim is genuine but nd_star cannot be assigned confidently (ai_confidence < 0.70 or key data missing). These records are NOT imported until a human resolves them. |
| `_clarification_questions` | list[str] | What specific information is needed (e.g. "yield not stated", "compound identity unclear"). |

### Bot reviewer metadata

| Field | Type | Notes |
|---|---|---|
| `reviewer_nickname` | string | Source-specific bot name. See BOT_NICKNAMES in config.py. E.g. `"AI-ORGSYN"`, `"AI-JACSAU"`. |
| `career_stage` | string | Always `"Data curator agent"` for all bot-generated reviews. |

### Star assignment rubric

| nd_star | Label | When to assign |
|---|---|---|
| 5 | Major extension | Reproduced AND extended to new substrates or functional groups not in the original paper |
| 4 | Minor extension | Reproduced AND extended, but within the same functional group class |
| 3 | Reproduced as published | Procedure followed without significant deviation; outcome successful |
| 2 | Reproduced with deviation | Got the product but with meaningful changes (different conditions, lower yield, modified workup) |
| 1 | Did not work | Procedure failed entirely under conditions described in the paper |
| null | Inconclusive / Extension failed | Set nd_failure_context to `"extension_failed"` or `"inconclusive"` |

`nd_failure_context` values:
- `"extension_failed"`: an extension was attempted and it failed
- `"inconclusive"`: outcome was ambiguous or results were unclear

Ratings 1–5 contribute to the star average. null counts toward total review count only.

### Example Stage 2 record (same record, enriched)

```json
{
  "target_doi": "10.1021/jacs.2c00001",
  "source_name": "OrgSyn",
  "source_doi": null,
  "source_url": "https://orgsyn.org/demo/orgSynAll/pdfs/CV13P0123.pdf",
  "extracted_sentences": "The procedure of Smith et al. was followed with minor modification to the workup. Compound 3 was isolated in 78% yield (lit. 81%). The lower yield was attributed to the use of technical-grade solvent.",
  "sentence_id": "orgsyn:CV13P0123::p4s1",
  "scrape_timestamp": "2026-07-09T10:00:00Z",
  "source_authors": "Jones A, Müller K, Tanaka R",
  "source_journal": "Org. Synth.",
  "source_year": 2024,
  "yield_reported": 78.0,
  "extraction_confidence": 0.92,
  "nd_star": 2,
  "nd_failure_context": null,
  "citing_author": "Jones et al.",
  "is_multi_target": false,
  "reproducibility_observation": "Sourced from Org. Synth. (Jones A et al., 2024). The procedure was followed with minor workup modification; yield 78% vs. reported 81%. Lower yield attributed to technical-grade solvent.",
  "ai_confidence": 0.88,
  "reviewer_nickname": "AI-ORGSYN",
  "career_stage": "Data curator agent"
}
```

---

## Bot users (one per source)

Each source gets its own user row in the ChemRepro database.
The DB import script creates these automatically if they do not exist.

| Source | `orcid_id` (bot key) | `reviewer_nickname` | `career_stage` | Display name |
|---|---|---|---|---|
| OrgSyn | `AI-ORGSYN` | `AI-ORGSYN` | `Data curation agent` | OrgSyn |
| JACS Au | `AI-JACS_Au` | `AI-JACS_Au` | `Data curation agent` | JACS Au |
| Europe PMC | `AI-EUROPEPMC` | `AI-EUROPEPMC` | `Data curation agent` | Europe PMC |
| ChemRxiv | `AI-CHEMRXIV` | `AI-CHEMRXIV` | `Data curation agent` | ChemRxiv |
| RSC Open Access | `AI-RSCOA` | `AI-RSCOA` | `Data curation agent` | RSC Open Access |
| PMC | `AI-PMC` | `AI-PMC` | `Data curation agent` | PMC |

`reviewer_nickname` and `career_stage` are written into every Stage 2 record by `ReviewWriterAgent`
using the `BOT_NICKNAMES` and `BOT_CAREER_STAGE` constants from `config.py`. Add new sources there
before running any Stage 2 enrichment.

`orcid_id` for bot users equals the `reviewer_nickname` (e.g. `AI-ORGSYN`). The `bot:orgsyn`
format shown in earlier versions of this spec was never implemented.

`is_bot` on the User model is deferred. Bot users are currently identified by the `AI-` prefix
on their `orcid_id`. The UI badge is planned but not yet wired.

The DB dedup constraint is `(doi, orcid_id, scoring_mode)`, not `sentence_id`. Each bot user may
submit only ONE review per target paper. If multiple source documents reference the same target,
the scraper should pre-select the highest-confidence record before sending to the import script.
`sentence_id` is the scraper's internal dedup key and is not stored in the database.

---

## Future input: reaction scheme images (not yet implemented)

When ChemRepro adds user-facing image upload, the following tools should be evaluated:

| Tool | Scope | Output | Notes |
|---|---|---|---|
| **RxnScribe** | Full reaction schemes | Reactants + products as SMILES, condition text, bounding boxes | Best option for full scheme parsing; published in J. Chem. Inf. Model.; Python API with pre-trained checkpoint |
| **DECIMER** | Single molecules only | SMILES string | `pip install decimer`; also has web API at decimer.ai; use when user uploads a single structure image |
| **ReactionDataExtractor 2** | Reaction scheme topology | Reaction graph (nodes + adjacency) | Heavy install (Conda + Tesseract); useful for arrow detection and layout parsing |

Recommended integration path:
1. User uploads image on ChemRepro review form
2. Backend detects image type: single molecule → DECIMER; full scheme → RxnScribe
3. RxnScribe returns reactant + product SMILES + condition text
4. SMILES passed to CrossRef/PubChem to resolve compound identity and DOI
5. Pre-fill the review form fields (compound, conditions, nd_star suggestion)

New Stage 1 fields needed when source is an image upload:
- `source_image_type`: `"reaction_scheme"` or `"single_molecule"`
- `source_image_hash`: SHA-256 of the uploaded image (for dedup)
- `rxnscribe_reactants`: list of SMILES strings
- `rxnscribe_products`: list of SMILES strings
- `rxnscribe_conditions`: text extracted from above/below arrow

---

## Data quality thresholds for import

Records failing any of these are written to the `rejected/` file, not imported:

- `extraction_confidence` < 0.75
- `ai_confidence` < 0.75
- `nd_star` is null (ambiguous claim)
- `extracted_sentences` is shorter than 30 characters
- `target_doi` does not resolve in CrossRef and is not already in the ChemRepro `papers` table
- `sentence_id` already exists in the database (duplicate)

---

## File naming convention

```
scraped_YYYYMMDD_HHMMSS.jsonl          Stage 1 raw output
enriched_YYYYMMDD_HHMMSS.jsonl         Stage 2 AI-enriched output
rejected_YYYYMMDD_HHMMSS.jsonl         Records that failed quality thresholds
scrape_log_YYYYMMDD_HHMMSS.txt         Run stats: papers scanned, hits, errors, rejections
```

---

## Summary checklist for the scraper developer

Stage 1 must output:

- [ ] `target_doi` — normalised, no URL prefix
- [ ] `source_name` — one of the allowed values
- [ ] `source_doi` or `source_url` — at least one required
- [ ] `extracted_sentences` — verbatim, max 800 chars
- [ ] `sentence_id` — stable unique key for dedup
- [ ] `scrape_timestamp` — ISO 8601 UTC

Stage 1 should also output (if available):

- [ ] `source_authors`, `source_journal`, `source_year`
- [ ] `yield_reported`
- [ ] `extraction_confidence`

Stage 1 must NOT do:

- [ ] Assign star ratings (that is Stage 2)
- [ ] Write observation text (that is Stage 2)
- [ ] Touch the database

Stage 2 must output (in addition to Stage 1 passthrough fields):

- [ ] `nd_star` — 1-5 or null (never 6 or other values)
- [ ] `nd_failure_context` — `"extension_failed"` or `"inconclusive"` when nd_star is null; null otherwise
- [ ] `reproducibility_observation` — 2-4 sentences, max 900 chars, opens with citing author
- [ ] `ai_confidence` — float 0-1; records < 0.75 are rejected at import
- [ ] `citing_author` — first author(s) of source paper or null
- [ ] `is_multi_target` — bool
- [ ] `reviewer_nickname` — from BOT_NICKNAMES in config.py (e.g. "AI-ORGSYN")
- [ ] `career_stage` — always "Data curator agent"
- [ ] `_needs_clarification` — bool; if true, record is held for human review, not imported
- [ ] `_clarification_questions` — list[str]; only present when _needs_clarification is true
