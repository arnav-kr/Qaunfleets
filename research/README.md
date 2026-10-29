# Preliminary research

This package records exploratory work on departure-offset prediction and local QpiAI SDK execution conducted on 29–30 October 2026. It supplements the application; these experiments do not change the deployed predictor, scheduling logic, or runtime dependencies.

- [Findings](FINDINGS.md): trainable VQC and preprocessing results, interpretation, and limitations.
- [Fair comparisons](FAIR_COMPARISONS.md): matched rows, model settings, single-run and repeated-run results.
- [SDK notes](SDK_NOTES.md): verified local execution, sampling reproducibility, and remote execution status.
- [Raw QpiAI output](raw_outputs/QpiAI_RAW_OUTPUT.txt): saved measurement counts and Opt solution values with solver metadata, without report commentary.
- [Results manifest](results/manifest.json): provenance and SHA-256 hashes for the exported evidence files.

The JSON results preserve recorded numeric outputs rather than rounded report tables. They include [preprocessing metrics](results/preprocessing_metrics.json), [single-run comparison metrics](results/single_run_metrics.json), and [actual SDK repeated-run metrics](results/sdk_repeated_runs.json). Protocols, dependency versions, and aggregate statistics are alongside them.

This is an evidence package, not a standalone retraining distribution. Raw charging records, per-session timestamps and predictions, credentials, environments, and serialized model files are excluded. Row-selection identity is recorded by the saved sample-ID file hash in the single-run configuration; that hash alone cannot recreate the data. Full reruns require the original prepared partitions and experiment sources, which remain in the isolated research workspace. The product's normal installation does not install PennyLane or pandas for this research.

Classical-only achieved the lowest point-prediction error in the matched comparisons. That result is retained alongside the quantum experiments. The tests do not establish the best complete charging application: early-quantile calibration, scheduling outcomes, and commercial-fleet generalization were not compared.
