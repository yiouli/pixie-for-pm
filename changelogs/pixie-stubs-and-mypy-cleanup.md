# Pixie Stubs And Mypy Cleanup

## What Changed

- replaced the incomplete top-level `pixie.pyi` file with a minimal local stub package under `pixie/` so mypy can type-check the actual imports used by this repository: `pixie.wrap`, `pixie.Runnable`, `pixie.eval.evaluable`, `pixie.eval.evaluation`, and `pixie.instrumentation.wrap`
- modeled the eval-facing `Evaluable`, `Evaluation`, and `NamedData` types permissively enough for the existing tests and eval harness code to type-check without adding `type: ignore` workarounds
- fixed the remaining orchestration test typing issue by narrowing the mocked Notion page payload before reading nested properties instead of indexing through `object`

## Validation

- `uv run mypy .`
- `uv run ruff check pixie_for_pm/integrations/runtime_providers.py pixie/__init__.pyi pixie/eval/__init__.pyi pixie/eval/evaluable.pyi pixie/eval/evaluation.pyi pixie/instrumentation/__init__.pyi pixie/instrumentation/wrap.pyi web/tests/e2e/test_live_vercel_mcp_tools.py web/tests/pixie_for_pm/integrations/test_runtime_providers.py web/tests/pixie_for_pm/orchestration/test_runtime.py`
