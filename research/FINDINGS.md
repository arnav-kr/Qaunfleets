# Preliminary findings

The direct trainable VQC learned from the data, but did not outperform its matched classical baseline. A single preprocessing candidate also failed to improve it. In the later comparison of three approaches, classical-only had the lowest observed point-prediction MAE. These observations support further evaluation; they do not establish quantum advantage or a universal model ranking.

## Trainable VQC and input preprocessing

The teammate's direct regressor uses six qubits, two data-reuploading blocks, RY input encoding, trainable RZ–RY–RZ gates, a CNOT ring, and mean Pauli-Z readout with a learned scalar scale and bias. There are 36 gate parameters and two readout parameters. PennyLane `default.qubit` executes the circuit locally with automatic gradients. This model differs from the application's fixed QCloud feature circuit followed by classical regressors.

The control fits six MinMax input scalers to the selected training rows, mapping their extrema to [-0.8, 0.8]. The circuit multiplies these values by pi before each RY gate. There is no clipping: validation inputs reach 1.74005, corresponding to 5.46652 radians. Equal training ranges therefore do not guarantee equal ordinary-value spread or bounded held-out inputs.

The candidate maps each raw sine/cosine feature to `0.8*x`. Each continuous feature passes through `log1p`, a training-only RobustScaler, and `0.8*tanh(z/2)`. Actual continuous RY angles are `0.8*pi*tanh(z/2)`. Both continuous training features were nonnegative and right-skewed (skewness 1.85 for departure horizon and 2.24 for energy); signed logarithms were not needed. All transformed values were finite and had six columns. No continuous output exceeded absolute 0.79 in these partitions.

Target processing remained a training-only RobustScaler, with center 0.0416667 minutes and scale 176.1083333 minutes. The readout scale and bias operate before inverse target scaling. Circuit design, optimizer, loss, stopping, row selection, and target processing stayed fixed between the two VQC branches.

| Preprocessing experiment | Validation MAE (minutes) | Test MAE (minutes) |
|---|---:|---:|
| VQC, existing inputs | 247.39 | 149.84 |
| VQC, candidate inputs | 250.49 | 150.19 |
| Classical, existing scaled inputs | 234.66 | 138.03 |
| Classical, candidate inputs | 232.89 | 136.86 |

The candidate worsened VQC test MAE by 0.35 minutes, while improving the classical model by 1.17 minutes. Both VQC branches changed their gate parameters and produced 512 finite test predictions. The original control VQC's initial, selected-checkpoint, and final-epoch Huber losses were 0.487487, 0.373331, and 0.349234; candidate values were 0.466724, 0.368979, and 0.360027. Validation selects checkpoints, so lower final training loss does not imply a better selected model.

The earlier 136.70-minute classical baseline used raw inputs and default squared-error trees with 100 iterations. Its raw-input score reproduced as 136.69668. The 138.03-minute result above uses the scaled control inputs; these baselines should not be conflated. The later three-model comparison also changes tree settings to match the deployed hybrid learner, as documented in [Fair comparisons](FAIR_COMPARISONS.md).

## Interpretation for the application

The fixed-circuit hybrid beat the trainable VQC on the matched test rows, but classical-only beat both. The current application remains an SDK integration prototype with an early-departure estimator and independently checked scheduling. The prediction benchmark provides no evidence that its quantum features improve accuracy. It also provides no comparison of complete-system cost, readiness, or quantile quality. Retaining the deployed integration does not imply that it won the accuracy benchmark.

All comparisons reuse an already-exposed chronological test partition. The data describe workplace unplugging as a departure proxy. Results are exploratory, with no claim of an untouched holdout, commercial-fleet validity, physical-QPU execution, or quantum advantage.
