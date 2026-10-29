# Verification

Release checks performed on the exported Git staging tree:

- Four pipeline/configuration tests passed.
- Exhaustive small-QUBO checks passed at three capacity levels, including bounded slack and charger conflicts.
- Twenty-one shipping checks passed: recorded-plan recomputation, tampered-plan rejection, shared quantum-feature comparisons and all-state Ising equivalence.
- Classical predictor inference and scheduling passed without raw data or local research files.
- The uv application completed a live QCloud + Opt run with independent validation; browser scene, roster and tariff rendering passed without page errors.
- Ruff lint and format checks passed; uv lockfile consistency checked.

Recorded results demonstrate small-instance functionality, not physical hardware performance or quantum advantage. Full model retraining is outside the distributed reproduction package.
