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

## Website execution logging

Fifteen automated tests pass, including per-request input/result persistence, actual status preservation, replay forecast reuse, separate filenames, and credential redaction on success and failure. A fresh website `Run charging plan` request executed the default six-vehicle scenario through QCloud's local SDK (six circuits, 512 shots each) and five local Opt QUBO attempts. The returned plan passed independent validation, satisfied six of six energy commitments, and had zero capacity violations. The browser reported live independently verified execution without console errors. The exact matching input and actual returned outputs are in [the submission log](../artifacts/run_logs/submission_qpiai_local.txt). These are local SDK results, not remote cloud results.

## Operational screen rebuild

The new allocation-first root page was built independently from the earlier layout. Seventeen tests pass, including bay release with frozen history and safe hold when a future solver fails after an observed departure. Browser checks cover six allocations, shared vehicle selection, V2 early departure, visible shortfall, bay hold/release, current execution evidence, optional 3D and mobile overflow. A fresh QCloud + Opt run through Generate plan returned feasible_heuristic and met all six commitments. No browser page errors were observed.

The screen exposes required energy, allocation, confirmed/predicted/actual times, site load/limit, peak, energy/demand bill and service/capacity outcomes. Automatic vehicle-linked charger clearance remains an explicit operating assumption, not a demonstrated lifecycle. Human comprehension testing is still pending.
