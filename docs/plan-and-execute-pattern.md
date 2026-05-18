# Plan-and-Execute CLI Pattern

This document explains the "Plan-and-Execute" pattern used in our CLI applications (like `spider` and `pipeline`).

## The Core Idea

Instead of mixing business logic with side effects (like writing to a database, making network calls, or creating files), we split our commands into three distinct steps:

1. **Plan:** Figure out exactly what needs to be done.
2. **Report (Dry Run):** Show the user what would happen.
3. **Execute:** Actually do the work.

## Why We Use It

* **Safe and Accurate Dry Runs:** Because the `--dry-run` flag uses the exact same "Plan" as the real execution, it is 100% accurate. You never have to worry about a dry-run lying to you.
* **Easy Testing:** You can test the complex logic (the "Plan" step) without needing to mock databases or network requests. 
* **Clear Boundaries:** It's obvious which functions are safe to call and which ones will change data.

## How It Works

Every command follows this lifecycle, with a strict separation between core logic and CLI output. **The CLI layer (`commands/*.py`) is the *only* place allowed to print to the terminal.**

### 1. The Planner (`build_*_plan` or `plan_*`)
This function reads the current state (like reading from the database or parsing files) and returns a list of "Plan" objects (usually Python dataclasses). 
* **Rule:** Planners are read-only. They never write data, make API calls, commit database transactions, or print to the terminal.

### 2. The Reporter (`render_*_plan`)
This function takes the Plan objects and formats them into a nice, human-readable string.
* **Rule:** Reporters only format and return text. They do not change state and **never** print to the terminal directly.

### 3. The Executor (`execute_*_plan`)
This function takes the Plan objects and performs the actual side effects.
* **Rule:** Executors are the *only* place where we write to the database, call external APIs, or create files. They should contain very little business logic. They **never** print to the terminal. To report progress, executors should `yield` results back to the CLI layer.