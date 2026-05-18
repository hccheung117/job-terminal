---
name: pipeline:flag-title-judge-errors
description: Run `./pipeline eval title-judge` and flag past LLM title-judge rejections that look wrong against the user's stated criteria — overkill (clearly should have passed) and miskill (rejection reason doesn't hold up). Read-only review of an LLM's screening decisions.
disable-model-invocation: true
---

# Flagging title-judge errors

## Why this exists

`./pipeline title judge` uses an LLM (see `apps/pipeline/src/steps/judge_title.py`) to screen surviving job titles against each user's free-text `criteria`. The judge prompt (`apps/pipeline/src/prompts/judge_title.md`) tells the model to **reject only when the title clearly violates the criteria** and to pass anything ambiguous — "better for some bad jobs to survive than for a good job to die at title judging."

The LLM doesn't always honor that. It sometimes rejects on thin evidence, on a guess about seniority, or on a keyword that the criteria didn't actually exclude. Those false rejects are exactly what kills good jobs at this stage. This skill replays the recorded `reason`s so the user can spot judge drift and decide whether to reset rows or rewrite the prompt.

You read the eval output. You don't modify the database, the prompt, or any code.

## How to run it

### 1. Run the eval

From the repo root:

```
./pipeline eval title-judge > /tmp/title_judge_eval.txt
```

Use the Bash tool. Safe to run unprompted — `eval title-judge` is read-only (see `apps/pipeline/src/commands/eval.py`); it only loads users, criteria, jobs, and existing `title_judge` decisions and prints them. No LLM calls, no DB writes.

### 2. Parse the output

The renderer (`render_judge_title_eval` in `judge_title.py`) prints one block per user:

```
# <user name> (<email>)

<criteria — free-form markdown, can be multi-line>

- <source_name>/<source_id>  <title> — pass
- <source_name>/<source_id>  <title> — reject: <reason>
- ...
```

Decisions are sorted newest first. `_no past judgments_` means the user has no decisions yet — skip that user.

For each user, capture: name/email, the full criteria block (everything after the heading until the first `- ` bullet), and the list of `(title, passes, reason)` tuples.

### 3. Analyze rejections against the criteria

This is the core work. For each user, hold their criteria as the reference frame and walk every **rejection**. For each rejected title, ask: given only the title text and the criteria, would a careful reader following the prompt's "reject only when clearly violating" rule have rejected this?

Two ways a rejection can be wrong:

- **overkill** — The title plainly fits the criteria, or fits a role the criteria explicitly invites. The rejection contradicts the criteria, not just shades it. *Example:* criteria says "backend, infra, platform engineering roles", title is "Senior Platform Engineer", reason is "too generic" → overkill.
- **miskill** — The reason itself doesn't hold up. The model invented a constraint the criteria didn't state, hallucinated a detail not in the title (e.g. "this is a contract role" when nothing in the title says so), or rejected on a property that the criteria are silent on. The outcome might be defensible by some reading, but the *stated reason* is bad. *Example:* criteria say nothing about seniority, title is "Staff Engineer", reason is "too senior" → miskill.

Be **super conservative**. The cost of a false flag here is high — it makes the user re-litigate decisions that were actually fine. Only flag a rejection when you can articulate, in one short sentence, why it contradicts the criteria as written. If you find yourself reasoning "the user *probably* didn't mean to include this" or "this is borderline", skip it. Pass-decisions are out of scope; we are not auditing what the judge let through.

What to **skip**:

- Rejections where the title clearly violates an explicit criterion. Those are the judge doing its job.
- Rejections you're unsure about. Silence is fine.
- Rejections where the reason is terse but plausible (e.g. "outside scope" on a title that genuinely is). Don't flag a reason just for being short.
- Anything ambiguous about seniority, domain, or industry unless the criteria speak to it directly.
- Pass decisions — even if they look wrong, this skill doesn't audit them.

### 4. Output the report

Print a single markdown report to the conversation. Structure:

```markdown
# Suggested title-judge misses

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

If a user has no flagged rejections, write `_no flags_` under their heading instead of fabricating any. If a section (Overkill or Miskill) is empty for a user, omit the section heading entirely rather than printing "none".

Cap each section at ~10 entries per user. If there are more, pick the clearest cases and add a trailing `_…and N more similar_` line.

End the report with a one-line reminder that nothing has been written — the user decides what (if anything) to do with the flagged rows (e.g. delete decisions, refine criteria, edit the prompt) themselves.

## Constraints

- **No edits.** Don't touch the `decision` table, the prompt file, or the judge code. This skill flags only.
- **Conservative bias.** When in doubt, don't flag. A short, high-signal report is the goal.
- **Don't audit passes.** The prompt deliberately leans permissive; passes that look weak are by design.
- **Stay grounded in the criteria text.** Don't import outside knowledge of what the user "really" wants — judge only against what's written in the criteria block.
