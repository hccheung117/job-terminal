Always request explicit permission before running the spider, as it incurs significant costs.

Patterns
- Spider is intentionally lightweight: command modules (`commands/*.py`) act as the step boundary and contain their own plan/render/execute helpers. Do not add a `steps/` layer.
- Keep `services/` for lower-level reusable helpers only, not command workflow orchestration.