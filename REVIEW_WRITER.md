# ChemRepro Review Writer

A browser-based tool for writing and editing reproducibility reviews, then exporting them as a JSON file ready for import into the database.

---

## How to access it

**Option 1: Open the local HTML file (recommended for regular use)**

```
chemrepro/scripts/review_writer.html
```

Open this file directly in Chrome or Firefox. No internet connection needed. Your reviews are saved automatically in the browser's local storage between sessions.

**Option 2: Open via Claude artifact**

URL: https://claude.ai/code/artifact/d79a5fb8-91e6-4e03-ae82-be41cc45e926

Note: the file download button does not work inside the artifact viewer due to browser restrictions. Use the **Copy / view JSON** button instead, then paste into a `.json` file manually.

---

## Workflow

### 1. Write a review

Fill in the form at the top of the page:

- **DOI**: the target paper's DOI, e.g. `10.1021/jacs.2c00001`
- **Outcome**: click one of the outcome pills (see scale below)
- **Observation**: free-text description of what was attempted and what happened
- **Optional fields**: reviewer profile, nickname, citing author, source DOI/URL

Click **Add Review**. The review appears as a card below the form.

### 2. Edit a review

Each card has a **Preview / Edit** toggle. In Edit mode you can change any field including the star rating. Click **Done editing** to return to Preview.

Click **Remove** to delete a card.

### 3. Export the JSON

Click **Export JSON** to download the file (works when opened locally).

Or click **Copy / view JSON** to open a modal with the full JSON text you can copy and paste into a file. Save it as something like `cr_reviews_2026-09-15.json`.

### 4. Import into the database

Run the import script from the `chemrepro/` directory:

```bash
# Local SQLite (default):
python scripts/import_reviews.py cr_reviews_2026-09-15.json --ai-name Lab-Berlin

# Dry run first (recommended):
python scripts/import_reviews.py cr_reviews_2026-09-15.json --ai-name Lab-Berlin --dry-run

# Railway PostgreSQL:
set DATABASE_URL=postgresql://postgres:YOUR-PASSWORD@YOUR-RAILWAY-HOST:PORT/railway
python scripts/import_reviews.py cr_reviews_2026-09-15.json --ai-name Lab-Berlin
```

The `--ai-name` flag creates a named reviewer profile automatically if it does not exist yet.
To import under your own ORCID instead: `--orcid 0009-0007-7610-9001`

---

## Star rating scale

| Star | Label | When to use |
|------|-------|-------------|
| 5 | Major extension | Reaction scope substantially extended beyond the original paper |
| 4 | Minor extension | Small extension; original procedure also worked |
| 3 | Reproduced as published | Exact procedure reproduced with matching outcome |
| 2 | Reproduced with deviation | Reproduced but with differences in yield, conditions, or scope |
| 1 | Did not work | Procedure failed entirely |
| null / ? | Extension failed / Inconclusive | Outcome ambiguous or unknown; must choose a failure context |

When star = null, select one failure context:
- **inconclusive**: outcome is unknown or ambiguous
- **extension_failed**: extension was attempted and did not work

When star = 1, an optional failure context is available:
- **original_tested**: the original published procedure was tested
- **extension_only**: only an extension was tested, not the original

---

## Multiple reviews for the same paper

The database has a one-review-per-user-per-paper constraint. To add two reviews for the same DOI, use a different reviewer profile for each:

1. In the **Optional fields** section, set a different **Reviewer profile** for each review (e.g. `Lab-Berlin` and `Lab-Zurich`).
2. Export the JSON once.
3. The CLI panel shows a separate command per profile. Run each one:

```bash
python scripts/import_reviews.py cr_reviews.json --ai-name Lab-Berlin
python scripts/import_reviews.py cr_reviews.json --ai-name Lab-Zurich
```

Each `--ai-name` is a separate user in the database, so both reviews appear on the same paper page.

---

## JSON field reference

The exported file is a list of objects. Only `target_doi` and `nd_star` are required.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `target_doi` | string | yes | DOI of the paper being reviewed |
| `nd_star` | 1-5 or null | yes | Outcome score; null = inconclusive / extension failed |
| `nd_failure_context` | string or null | conditional | Required when `nd_star` is null; optional when `nd_star` is 1 |
| `reproducibility_observation` | string or null | no | Free-text review body |
| `reviewer_nickname` | string or null | no | Overrides the profile's display name for this review |
| `citing_author` | string or null | no | Author who cited the original work |
| `source_doi` | string or null | no | DOI of the paper that cited/reported the reproduction |
| `source_url` | string or null | no | URL source for the review data |

Example minimal review:

```json
[
  {
    "target_doi": "10.1021/jacs.2c00001",
    "nd_star": 3,
    "reproducibility_observation": "Reproduced the reported Suzuki coupling in 78% yield (literature: 81%). Conditions matched exactly. No issues with the procedure."
  }
]
```

Example with null star:

```json
[
  {
    "target_doi": "10.1021/jacs.2c00001",
    "nd_star": null,
    "nd_failure_context": "inconclusive",
    "reproducibility_observation": "Reproduction was attempted but the outcome could not be assessed due to incomplete characterisation data in the source."
  }
]
```

---

## Tips

- **Progress is auto-saved** in your browser's local storage. If you close and reopen the HTML file in the same browser, your reviews are still there.
- **Load saved** imports a previously exported JSON back into the editor so you can continue editing.
- **Dry run first**: always pass `--dry-run` on the first run to check for validation errors before writing to the database.
- The import script automatically fetches paper metadata from CrossRef if the DOI is not already in the database.
- Citation links in the observation text are resolved automatically after import (the script calls the citation resolver on newly added reviews).
