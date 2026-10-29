# QpiAI SDK execution notes

Recorded checks used `qpiai-quantum==0.7.5` and `qpiai-opt==0.0.9`. SDK integration and execution location are separate properties: the application uses authenticated QpiAI SDKs, with computation configured locally.

## QCloud local execution

An exact copy of the production worker executed two synthetic six-qubit circuits with 512 shots each. Inputs were six zeros and six 0.3-radian angles. It returned 12 finite Z/ZZ features per circuit; the zero-angle observables were all +1 as expected. Its features successfully fed the deployed point and early-quantile model artifacts, producing finite predictions. This checks the SDK-to-predictor boundary; it is not a complete dashboard/scheduler verification.

The subsequent benchmark executed 15,360 circuits through the actual SDK's `QpiAI-QSV-Local` backend. Authentication contacted the vendor service. Installed SDK code dispatches this backend to a local state-vector simulator and returns before the remote-job path.

Repeated calls with the same `seed_simulator` argument produced different counts. The installed local `Circuit.run` wrapper does not forward that argument to the simulator. Therefore the benchmark records independent shot realizations rather than claiming controlled quantum seeds. No SDK or application change was made to alter this behavior.

## Opt local execution

Recorded scheduling runs use QpiAI Opt with `mode="local"` and `allow_platform=False`. The retained solver metadata reports simulated annealing, completed termination, local execution, timing, seeds, reads, and sweeps. Local simulated annealing is a classical computation; it is not physical quantum annealing or a proof of global optimality.

The raw output file includes all 11 saved solver attempts from three recorded QpiAI Opt scenario runs, including attempts later rejected by schedule validation. A completed solver call alone does not establish a valid charging schedule. The application separately validates schedules, and the full recorded context remains in [the shipped scheduling benchmark](../artifacts/shipping/benchmark.json).

## Raw-output provenance

[QpiAI_RAW_OUTPUT.txt](raw_outputs/QpiAI_RAW_OUTPUT.txt) is a JSON-formatted text export containing two saved SDK measurement-count dictionaries and 11 Opt solution vectors with solver metadata. Values were extracted from existing local-run records; no new computation was performed to create this export. It is not a verbatim console transcript or a dump of every SDK result field. It excludes analysis prose, classical predictions, QUBO input matrices, schedules, and credentials.

The two count dictionaries come from repeated synthetic 0.3-angle circuits, each totaling 512 shots. The Opt solution vectors and metadata come from the shipped scheduling benchmark. Source/output hashes are recorded in [the manifest](results/manifest.json).

## Remote execution status

An isolated two-qubit Bell test was prepared for `QpiAI-QSV-Simulator`, 128 shots. The hosted estimator quoted 1 credit. Authentication, experiment lookup, and circuit upload succeeded, but remote job creation was rejected with: `an active subscription is required to run jobs`.

No completed remote QCloud computation or physical-QPU execution is claimed. Remote QpiAI Opt execution was not submitted because its total cost was not confirmed. Neither check changed the application's configured local backends. Subscription prices are time-dependent and are not part of this research package.
