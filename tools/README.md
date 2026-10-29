# Development tools

Run these commands from the repository root after `uv sync --locked`. They use the same application modules as the server; they are not part of the request-handling path.

| Command | Purpose | Output / access |
|---|---|---|
| `uv run python -m tools.verify_qubo` | Exhaustive small-QUBO mathematics checks | Writes `artifacts/shipping/math_checks.json`; no credentials |
| `uv run python -m tools.verify_shipping` | Audit bundled schedules, tamper rejection, feature reuse, and Ising equivalence | Writes `artifacts/shipping/acceptance.json`; no credentials |
| `uv run python -m tools.shipping_benchmark` | Regenerate full-menu, same-menu, and SDK scheduling evidence | Replaces `artifacts/shipping/benchmark.json`; requires local Opt and QCloud SDK authentication |
| `uv run python -m tools.quantum_shipping_demo` | Regenerate the small circuit-scale scheduling demonstration | Replaces `artifacts/shipping/quantum_demo.json`; requires local Opt and QCloud SDK authentication |

The benchmark generators overwrite the recorded artifacts used by the application. Use a separate checkout for experimental regeneration and review the resulting evidence before committing it. Neither generator configures a remote compute backend.

These utilities previously lived at the repository root as standalone Python scripts. Use the module commands above so Python resolves the application's root modules consistently. Data and output paths resolve from the repository location rather than the current process directory.
