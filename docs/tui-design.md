# CLI / TUI Design Guidelines

This document outlines the design principles and output formatting for the job-terminal CLI (`spider` and `pipeline` commands). The goal is to provide outputs that are consistent, easy to scan, minimal, modern, and informative.

## 📐 Design Principles

1. **Clear Iconography**
   Use standard, simple prefixes to convey state instantly:
   - `•` : Info / processing step / context
   - `✓` : Success / pass / completion
   - `✗` : Fail / reject / error
   - `+` : Added / kept item
   - `-` : Removed / skipped item / list bullet

2. **Progressive Disclosure**
   - Hide massive lists. For example, during bulk operations, show the "Kept" items but summarize the "Dropped" items (e.g., `- 92 jobs skipped`).
   - Use a `--verbose` flag if full details of skipped or dropped items are needed.

3. **Dimmed Metadata**
   - Visually deemphasize metadata like raw Job IDs (`li-4415787083`), internal grouping tags, or emails using dimmed (grey) terminal text, allowing the primary data (Job Titles, Names, Actions) to pop out.
   - Do not print raw Python logger outputs (e.g., `2026-05-19 14:12:38,972 - INFO - JobSpy...`) to standard output. Suppress them or log to a file instead.

4. **Action-Result Grouping**
   - Standardize on printing the context/header first.
   - Indent the related items cleanly under their context (e.g., 2 spaces for user group, 4 spaces for items under user).
   - Conclude with a final summary `✓` at the end of the command execution.
   - Skip printing duplicate lists (e.g., "To judge" followed immediately by the same list with decisions). Stream or print the final results directly.

5. **Clean Rejection Reasons**
   - When an LLM or filter rejects an item, print the rejection reason indented on the next line using a clean `Reason:` prefix, making it incredibly easy to scan why an item was dropped.