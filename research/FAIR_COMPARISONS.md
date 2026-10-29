# Matched prediction comparisons

Every method uses the same saved row IDs and order: 2,048 training, 512 validation, and 512 test examples within pre-existing chronological partitions. Chronological ordering, finite feature arrays, correct shapes, and finite test predictions were checked. The target is observed disconnection minus declared departure in minutes; lower MAE is better. Negative targets represent leaving before the declared time.

## Common protocol

The six inputs, in order, are request-hour sine/cosine, weekday sine/cosine, hours until declared departure, and requested energy in kWh. Both tree methods use absolute-error HistGradientBoosting with 15 leaves, 150 iterations, L2 regularization 10, and otherwise the recorded defaults. This holds the learner fixed when testing the value of quantum features. It differs from the teammate's earlier default squared-error classical baseline.

- **Classical-only:** six raw inputs feed the tree regressor.
- **Fixed-circuit hybrid:** training-only mean/std normalization, clipping to [-3, 3], and multiplication by pi/3. The circuit applies RY(a) and RZ(0.5a) per qubit, a five-edge CX chain, then RY(0.7a). Common computational-basis samples produce six Z and six cyclic ZZ expectations for the tree regressor.
- **Trainable VQC:** the original control model described in [Findings](FINDINGS.md), with training-only MinMax input scaling and Robust target scaling. Adam learning rate 0.08, Huber delta 1, batch size 64, at most 15 epochs, and patience 3. Checkpoints are selected by validation MAE.

All methods receive the teammate's saved hourly sine/cosine values. The deployed app normally calculates fractional-hour features at inference. Published fitted models were not reused, because their training row selection differed. These experiments compare retrained model designs on common inputs. No settings or best seed were selected using these test results.

## Single-run simulator comparison

The hybrid circuit was reproduced in PennyLane with 512 shots and shot seed 42. This run was not actual QCloud SDK execution. The VQC used initialization seed 19 and shuffle seed 20261029; both trees used seed 42.

| Approach | Validation MAE (minutes) | Test MAE (minutes) |
|---|---:|---:|
| Classical-only | 235.25 | 133.34 |
| Fixed-circuit hybrid, PennyLane reproduction | 247.20 | 142.18 |
| Trainable VQC | 247.39 | 149.84 |

[Metrics](results/single_run_metrics.json), [configuration](results/single_run_config.json), and [paired comparisons](results/single_run_paired_comparisons.json) retain the recorded values. The paired intervals use 5,000 bootstrap resamples of calendar days, preserving within-day dependence. They are conditional on these fitted models and do not capture training-seed variation or possible dependence across days.

## Actual QCloud SDK repeated runs

The hybrid features were regenerated through the actual QpiAI SDK using `Circuit.run(device_name="QpiAI-QSV-Local")`, with 512 shots for each row. Five repetitions executed 15,360 circuits in total. There was no PennyLane substitution for the hybrid in this experiment.

Training seeds were 19, 42, 73, 101, and 202. Both VQC initialization and batch shuffle used each seed, explaining why these results differ from the single-run initialization19/shuffle20261029 result. The tree learners used the corresponding seed. The SDK's local wrapper ignores `seed_simulator`; these are five independent uncontrolled shot realizations, not five reproducible quantum shot seeds. The saved protocol explicitly records that limitation.

| Approach | Mean test MAE ± sample SD (minutes) | Test MAE range | Mean validation MAE |
|---|---:|---:|---:|
| Classical-only | 133.34 ± 0.00 | 133.34–133.34 | 235.25 |
| Fixed-circuit hybrid, actual local QCloud SDK | 144.29 ± 1.05 | 142.96–145.77 | 247.67 |
| Trainable VQC | 154.69 ± 2.99 | 152.01–159.82 | 252.94 |

Classical-only ranked first, the hybrid second, and the VQC third in all five test comparisons. The classical learner has no effective random variation with these settings and rows; five identical scores are not five independent datasets. Mean ± SD describes run variation, not a confidence interval for future prediction accuracy.

See [per-run metrics](results/sdk_repeated_runs.json), [aggregate statistics](results/sdk_summary.json), [protocol](results/sdk_protocol.json), and [dependency versions](results/versions.json).

This confirms the observed ranking on the reused test data. It does not test early-quantile calibration, charging outcomes, remote-cloud performance, physical hardware, or generalization to new fleets. Raw records and per-session predictions are not distributed in this package, so the included summaries cannot independently reproduce the complete training process.
