Python Package Management
- Use `uv` as the package manager exclusively.
- Avoid editing `pyproject.toml` manually unless the `uv` CLI cannot accomplish your goal.

SQL style
- In raw SQL strings (`text(...)`, migrations): keywords UPPERCASE (`SELECT`, `FROM`, `COALESCE`, etc.); identifiers, aliases, and table/column names lowercase.