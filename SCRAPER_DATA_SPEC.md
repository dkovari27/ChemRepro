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

| Field | Type | Notes |
|---|---|---|
| `nd_star` | int 1-5 | Star rating inferred from the extracted sentences. See mapping guide below. |
| `nd_failure_context` | string or null | `"original_tested"` or `"extension_only"`. Required only when `nd_star = 1`. |
| `observation_text` | string | The text shown on the review card. Written by the AI in 2-4 sentences. Should cite the source and describe what was done. Max 800 chars. |
| `ai_confidence` | float 0-1 | AI self-assessed confidence in the star assignment. |

### Star assignment guide for the AI agent

| Situation described in the source text | `nd_star` |
|---|---|
| Procedure followed without modification, yield matches | 3 |
| Procedure followed, yield lower or minor workup changes | 2 |
| Procedure adopted and extended to new substrates or conditions | 4 |
| Procedure adopted and extended to a new functional group class | 5 |
| Procedure attempted, failed completely | 1 |
| Unclear or ambiguous | Do not import (flag for manual review) |

For `nd_star = 1`: set `nd_failure_context = "original_tested"` if the
original procedure was tested. Set `"extension_only"` if only an extension
was attempted and the original was not tested.

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
  "observation_text": "Sourced from Org. Synth. (Jones A et al., 2024). The procedure was followed with minor workup modification; yield 78% vs. reported 81%. Lower yield attributed to technical-grade solvent.",
  "ai_confidence": 0.88
}
```

---

## Bot users (one per source)

Each source gets its own user row in the ChemRepro database.
The DB import script creates these automatically if they do not exist.

| Source | `orcid_id` (bot key) | Display name |
|---|---|---|
| OrgSyn | `bot:orgsyn` | OrgSyn |
| Europe PMC | `bot:europepmc` | Europe PMC |
| ChemRxiv | `bot:chemrxiv` | ChemRxiv |
| RSC Open Access | `bot:rsc_oa` | RSC Open Access |

These users are flagged `is_bot = true` in the `users` table so the UI
can display a "Sourced from X" badge instead of a reviewer name.

The unique constraint `(doi, orcid_id, scoring_mode)` means each bot user
can submit only ONE review per target paper. If multiple source documents
all reference the same target paper, the import script should keep the
highest-confidence record and discard the rest (or aggregate them into one
observation text).

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
