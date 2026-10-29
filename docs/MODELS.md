# Prediction model

The deployed hybrid predictor uses six request-time inputs: sine/cosine of arrival hour, sine/cosine of weekday, declared remaining hours and requested energy. Training-set means and standard deviations scale these inputs into circuit angles:

$$
\theta_i=\frac{\pi}{3}\operatorname{clip}\left(\frac{x_i-\mu_i}{\sigma_i},-3,3\right).
$$

The fixed six-qubit circuit applies RY/RZ rotations, a CX chain and a second RY layer. Its 512 measured shots produce six Z and six ZZ features. Two histogram gradient-boosted regressors estimate the typical and 10th-percentile offset:

$$
y=t_{\mathrm{session\ end}}-t_{\mathrm{declared\ departure}}.
$$

The point estimator uses absolute-error loss and 15 leaf nodes; the early estimator uses quantile loss and 7 leaf nodes. Both use 150 iterations, L2 regularization 10 and seed 42. Circuit parameters are fixed rather than trained.

The model was fitted on NREL workplace requests, not commercial fleet operations. Session end is an unplugging proxy. Existing test data was reused during development, so no fresh-holdout or fleet-generalization claim is supported.

Bundled model artifacts support inference and scheduling. Raw records and full training preparation are not distributed. Only load the supplied trusted joblib files; untrusted serialized models can execute code.
