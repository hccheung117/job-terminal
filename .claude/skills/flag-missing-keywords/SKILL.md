---
name: spider:flag-missing-keywords
description: Run `./spider upload --dry-run` and flag dropped job titles that are semantically close to a group's existing keywords — i.e., role variants, synonyms, abbreviations the user should consider adding to the spider `keywords` table.
disable-model-invocation: true
---

# Flagging missing keywords for spider upload

## Why this exists

`./spider upload` filters scraped LinkedIn CSVs against per-group keywords from the `keywords` DB table (case-insensitive word-boundary regex). Titles that don't match are dropped silently. Some of those drops are correct (off-topic roles), but others are coverage gaps — role variants, synonyms, abbreviations, or related sub-specialties the user just hasn't added yet. This skill surfaces those gaps so the user can decide what to add.

The implementation lives in `apps/spider/src/services/jobs.py`: filtering at `_title_pattern` / `plan_upload_snapshots`, the stderr output at `render_upload_plan`. You don't modify any of it.

## How to run it

### 1. Run the dry-run

From the repo root:

```
./spider upload --dry-run 2>/tmp/spider_dryrun_stderr.txt >/tmp/spider_dryrun_stdout.txt
```

Use the Bash tool. This is safe to run without asking — `--dry-run` only reads local CSV snapshots and the `keywords` table, never writes to the DB and never invokes the scraper. The "ask before running spider" rule in `apps/spider/CLAUDE.md` is about scraping cost; it doesn't apply here.

Then read `/tmp/spider_dryrun_stderr.txt` — that's where the interesting data is.

### 2. Parse the stderr

The format (one block per snapshot CSV, produced by `render_upload_plan`):

```
<filename>.csv  (group: <group-name>)
  keywords: <comma-separated current keywords>
  kept N / dropped M / total T
  + <kept title>
  + <kept title>
  ...
  - <dropped title>
  - <dropped title>
  ...
```

Lines that start with `warning:` mean the group has no keywords configured — skip those groups entirely (there's no "missing keyword" question if the group itself is empty).

For each non-warning block, capture: group name, current keywords (split the `keywords:` line on `, `), and dropped titles (every line starting with `  - `).

### 3. Analyze per group

For each group, with its current keywords as the reference frame, look at the dropped titles and identify ones that clearly belong to the same role family. Then propose a **specific keyword string** that, if added, would catch a family of related dropped titles.

What counts as a candidate:

- **Synonyms** — e.g., group has "data engineer", dropped includes "analytics engineer", "data platform engineer".
- **Abbreviations / expansions** — "ML engineer" ↔ "machine learning engineer", "SWE" ↔ "software engineer".
- **Seniority or qualifier variants** that aren't covered by the existing patterns — "lead", "principal", "staff" prefixes, or domain qualifiers like "backend", "infrastructure".
- **Adjacent sub-specialties** that the user is plausibly interested in given the group's existing scope.

What to **skip**:

- Titles that are off-topic for the group (different role family entirely). Those are genuine filter wins, not gaps.
- Proposals that are already in the current keyword list, even as a substring (case-insensitive). The existing pattern uses `\bword\b`, so if "engineer" is already a keyword, "data engineer" is already caught — don't re-propose.
- Long phrases. Keywords get `re.escape`d and joined into a regex alternation; short word-boundary-friendly fragments work best.

Be conservative. A short list of high-confidence candidates is more useful than a noisy long list. If you're unsure whether a dropped title is on-topic for the group, leave it out.

### 4. Output the report

Print a single markdown report to the conversation. Structure:

```markdown
# Suggested missing keywords

## Group: <group-name>

Current keywords: `kw1`, `kw2`, `kw3`

### Candidate: `<proposed keyword>`
Reasoning: <one-line — e.g., "variant of 'data engineer'">
Sample dropped titles:
- <title 1>
- <title 2>
- <title 3>

### Candidate: `<proposed keyword>`
...

## Group: <next-group-name>
...
```

If a group has no plausible candidates, write `_no candidates_` under it instead of fabricating suggestions. Cap the sample dropped-title list per candidate at ~5 (pick the clearest examples).

End the report with a one-line reminder that nothing has been written — the user adds anything they like to the `keywords` table themselves.

## Constraints

- **No edits.** Don't modify the `keywords` table, don't edit code, don't write SQL to apply changes. This skill flags only.
- **No re-proposing.** Before listing a candidate, check (case-insensitive substring) that it isn't already in the group's current keywords.
- **Stay in budget.** If the dry-run output is huge, you don't have to enumerate every dropped title — sample broadly and prioritize the highest-signal candidates.
