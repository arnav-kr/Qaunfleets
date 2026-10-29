# Predictor artifacts

`artifacts/four-way/{classical,qml}.joblib` are the saved histogram gradient-boosting model bundles used by the application. `scaler.json` contains training-set feature means and standard deviations only; it contains no session rows. The classical bundle consumes six request-time features; the hybrid bundle consumes twelve measured quantum features.

The exploratory experiment used 4,091 matched NREL workplace-request examples: 2,048 training, 919 tuning and 1,124 previously exposed test examples. The target is observed session-end minus declared-departure time in minutes. This is an unplugging proxy. Test reuse prevents a fresh-holdout claim.

Point model: absolute-error loss, 150 iterations, selected from 7/15 leaf nodes on tuning MAE. Early estimate: 10th-percentile quantile loss, 150 iterations, 7 leaves. Both use L2 regularization 10 and random state 42. The quantum feature map is fixed, not variationally trained.

The repository supports reproducing inference, scheduling and mathematical checks from the supplied artifacts. It does not contain the historical data preparation/training experiment or raw data, so it is not a complete training-reproduction package. Recorded operational scenarios are synthetic and contain no original driver identifiers. Inspect JSON evidence for the exact scenario, solver parameters and outputs.

Only load the bundled, trusted joblib files: deserializing untrusted joblib/pickle files can execute code.
