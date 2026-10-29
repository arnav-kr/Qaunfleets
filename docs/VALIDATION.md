# Verification

Release checks performed on the exported Git staging tree:

- Four pipeline/configuration tests passed.
- Exhaustive small-QUBO checks passed at three capacity levels, including bounded slack and charger conflicts.
- Twenty-one shipping checks passed: recorded-plan recomputation, tampered-plan rejection, shared quantum-feature comparisons and all-state Ising equivalence.
- Classical predictor inference and scheduling passed without raw data or local research files.
- The uv application completed a live QCloud + Opt run with independent validation; browser scene, roster and tariff rendering passed without page errors.
- Ruff lint and format checks passed; uv lockfile consistency checked.

Recorded results demonstrate small-instance functionality, not physical hardware performance or quantum advantage. Full model retraining is outside the distributed reproduction package.

## Stateful execution replay

Twelve pipeline/replay tests cover immutable past power, actual early-departure shortfalls, occupied-bay exclusion, increased background load, accumulated energy cost, sequential events, revised deadlines, input immutability and fixed-rate charging with final partial slots. Existing 21 shipping checks remain passing.

Browser replay on the recorded QCloud + Opt plan: V2 leaves at slot 14 with 6.48 kWh delivered and 12.96 kWh unmet; later bay and load events preserve history and return valid future allocations for the remaining vehicles. The interface reports five of six requests satisfied, physical validation separately, zero capacity violations, and the departed vehicle's shortfall. Desktop/mobile checks found no page errors or horizontal overflow.

## Repository layout verification

The development utilities now live under `tools/`; see [commands and output behavior](../tools/README.md). On 30 October 2026, a clean export containing only distribution files passed all 12 automated tests, exhaustive QUBO checks, 21 shipping acceptance checks, and Ruff lint/format checks. The export omitted credentials, raw datasets, and local research captures. Benchmark generators were not rerun, and the recorded evidence, fitted models, and application runtime sources were unchanged by this organization pass.
