Python Package Management
- Use `uv` as the package manager exclusively.
- Avoid editing `pyproject.toml` manually unless the `uv` CLI cannot accomplish your goal.

SQL style
- In raw SQL strings (`text(...)`, migrations): keywords UPPERCASE (`SELECT`, `FROM`, `COALESCE`, etc.); identifiers, aliases, and table/column names lowercase.

Running apps
- From repo root: `./spider <args>` and `./pipeline <args>` (wrapper scripts that `cd` into the app and `uv run` its entry script).