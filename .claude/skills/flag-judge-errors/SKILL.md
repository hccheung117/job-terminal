---
name: pipeline:flag-judge-errors
description: Run `./pipeline eval title-judge` and `./pipeline eval jd-judge` and flag past LLM rejections that look wrong against the user's stated criteria — overkill (clearly should have passed) and miskill (rejection reason doesn't hold up). Read-only review of an LLM's screening decisions.
disable-model-invocation: true
---

# Flagging judge errors

## Why this exists

The pipeline has two LLM screening stages:

1. **title-judge** (`apps/pipeline/src/steps/judge_title.py`, prompt `apps/pipeline/src/prompts/judge_title.md`) — screens job titles against each user's free-text `criteria`.
2. **jd-judge** (`apps/pipeline/src/steps/judge_jd.py`, prompt `apps/pipeline/src/prompts/judge_jd.md`) — screens the full job description for titles that survived stage 1.

Both prompts tell the model to **reject only when the job clearly violates the criteria** and to pass anything ambiguous — "better for some bad jobs to survive than for a good job to die at this stage."

The LLM doesn't always honor that. It rejects on thin evidence, on a guess, or on a constraint the criteria didn't actually state. Those false rejects kill good jobs. This skill replays the recorded `reason`s so the user can spot judge drift and decide whether to reset rows or rewrite a prompt.

You read the eval output. You don't modify the database, the prompts, or any code.

## How to run it

Run **two passes**: pass 1 over title-judge, pass 2 over jd-judge. They share the same analysis approach but differ in what evidence is available — see the per-pass notes below.

### Pass 1 — title-judge

```
./pipeline eval title-judge > /tmp/title_judge_eval.txt
```

Safe to run unprompted — `eval title-judge` is read-only (see `apps/pipeline/src/commands/eval.py`); it loads users, criteria, jobs, and existing `title_judge` decisions and prints them. No LLM calls, no DB writes.

The judge saw **only the title** when deciding. So any reason that depends on details not in the title (seniority, contract status, location, comp) is suspect — the model couldn't have known.

### Pass 2 — jd-judge

```
./pipeline eval jd-judge > /tmp/jd_judge_eval.txt
```

Read-only. Same renderer shape (one block per user; rejections shown as `- <source>/<id>  <title> — reject: <reason>`).

The judge saw the **full job description**, but this output only shows the title and the reason. So a reason like "requires 10+ years experience" or "this is a contract role" may be perfectly grounded in JD text you can't see. **Don't flag a rejection as miskill just because the constraint isn't visible in the title.**

When a single rejection's reason looks suspicious and you need to verify it against the JD, use the inspection shortcut to fetch only that one job:

```
./pipeline eval jd-judge --job <source_name>/<source_id>
```

This narrows the report to just that one decision (across whichever user owns it) and inlines the JD inside `<jd>...</jd>`. All other jobs are omitted — it's an inspection shortcut, not a full eval. Use it surgically — one job at a time.

### Output shape (both passes)

The renderer (`render_judge_*_eval`) prints one block per user:

```
# <user name> (<email>)

<criteria — free-form markdown, can be multi-line>

- <source_name>/<source_id>  <title> — pass
- <source_name>/<source_id>  <title> — reject: <reason>
- ...
```

Decisions are sorted newest first. `_no past judgments_` means the user has no decisions at this stage yet — skip that user.

For each user, capture: name/email, the full criteria block (everything after the heading until the first `- ` bullet), and the list of `(title, passes, reason)` tuples.

### Analyze rejections against the criteria

This is the core work. For each user, hold their criteria as the reference frame and walk every **rejection**. For each rejected title, ask: given the available evidence and the prompt's "reject only when clearly violating" rule, would a careful reader have rejected this?

Two ways a rejection can be wrong:

- **overkill** — The job plainly fits the criteria, or fits a role the criteria explicitly invites. The rejection contradicts the criteria, not just shades it. *Example:* criteria says "backend, infra, platform engineering roles", title is "Senior Platform Engineer", reason is "too generic" → overkill. Applies to both passes.
- **miskill** — The reason itself doesn't hold up. The model invented a constraint the criteria didn't state, or rejected on a property the criteria are silent on. *Example:* criteria say nothing about seniority, title is "Staff Engineer", reason is "too senior" → miskill.
  - **Pass 1 only:** also flag when the reason cites a detail the title cannot reveal (e.g. "this is a contract role" when nothing in the title says so) — the title-judge had no other information.
  - **Pass 2:** do not flag for "the title doesn't show that" — the JD might. Only flag when the reason names a constraint the criteria itself doesn't impose. If the reason cites a specific JD claim (e.g. "requires 10+ years"), inspect that one JD with `--job <source>/<id>` to verify before flagging — only flag if the JD does **not** support the reason.

Be **super conservative**. The cost of a false flag is high — it makes the user re-litigate decisions that were actually fine. Only flag a rejection when you can articulate, in one short sentence, why it contradicts the criteria as written. If you find yourself reasoning "the user *probably* didn't mean to include this" or "this is borderline", skip it. Pass-decisions are out of scope; we are not auditing what the judge let through.

What to **skip**:

- Rejections where the title clearly violates an explicit criterion. Those are the judge doing its job.
- Rejections you're unsure about. Silence is fine.
- Rejections where the reason is terse but plausible (e.g. "outside scope" on a title that genuinely is). Don't flag a reason just for being short.
- Anything ambiguous about seniority, domain, or industry unless the criteria speak to it directly.
- Pass decisions — even if they look wrong, this skill doesn't audit them.
- (Pass 2) Rejections grounded in JD facts you can't see. Assume the JD said what the reason claims unless it contradicts the criteria.

### Output the report

Print a single markdown report per pass to the conversation. Structure:

```markdown
# Suggested <pass> misses

## <user name> (<email>)

Criteria summary: <one sentence in your own words, so it's clear what frame you're judging against>

### Overkill
- `<source>/<id>` **<title>** — rejected: "<reason>"
  Why this looks wrong: <one line — point to the specific criterion it actually fits>

### Miskill
- `<source>/<id>` **<title>** — rejected: "<reason>"
  Why this looks wrong: <one line — name the unstated constraint or hallucinated detail>

## <next user>
...
```

Replace `<pass>` with `title-judge` or `jd-judge` in the top heading.

If a user has no flagged rejections, write `_no flags_` under their heading instead of fabricating any. If a section (Overkill or Miskill) is empty for a user, omit the section heading entirely rather than printing "none".

Cap each section at ~10 entries per user. If there are more, pick the clearest cases and add a trailing `_…and N more similar_` line.

End each pass's report with a one-line reminder that nothing has been written — the user decides what (if anything) to do with the flagged rows (e.g. delete decisions, refine criteria, edit the prompt) themselves.

## Constraints

- **No edits.** Don't touch the `decision` table, the prompt files, or the judge code. This skill flags only.
- **Conservative bias.** When in doubt, don't flag. A short, high-signal report is the goal.
- **Don't audit passes.** The prompts deliberately lean permissive; passes that look weak are by design.
- **Stay grounded in the criteria text.** Don't import outside knowledge of what the user "really" wants — judge only against what's written in the criteria block.
- **Pass 2 has hidden evidence by default.** The jd-judge saw the JD; you don't, unless you inspect a specific one with `--job <source>/<id>`. Fetch JDs surgically — one at a time — only when needed to verify a suspicious reason. Don't bulk-load JDs.
