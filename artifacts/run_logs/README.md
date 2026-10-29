# Website execution logs

Every valid `/solve` and `/replan` request creates a uniquely named UTF-8 `.txt` file here. The file records the UTC time, request ID, input, forecast evidence, optimizer solutions/status/timing, application schedule and validation, and completion or failure. Matching request IDs also appear in the server terminal alongside ordinary HTTP access logs.

`submission_qpiai_local.txt` is a saved fresh execution of the website's recorded default `tariff_and_peak` scenario through `/solve`, with QCloud features and the local QpiAI Opt QUBO solver. It is not a recorded-demo load or remote cloud execution. SDK sampling is stochastic, so individual outputs can differ from the older recorded plan.

`FORECAST RESULT` and `OPTIMIZER RESULT` contain returned evidence; these are application-authored log sections, not verbatim SDK console messages. Solver termination and application validation are separate. Opt attempts rejected by physical validation remain included. No optimality claim is inferred from simulated annealing completing. QCloud's local circuit worker includes its original measurement counts as well as derived Z/ZZ features.

Loading `/evidence` only reads historical results and does not create a fresh execution log. Replanning may reuse the previous forecast; its `reused_at_event` flag identifies this. Request logs contain the inputs submitted by the user; use synthetic demonstration data for shared logs. Configured credential values and credential fields are redacted. New run logs are ignored by Git; only this README and the reviewed submission file are allowlisted. The response contract, model settings, and solver choice are unchanged.
