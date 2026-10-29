"""Small depth-one QAOA using actual QCloud gates. No hardware/advantage claim."""

import contextlib
import io
import itertools
import json
import sys
import time

from qpiai_quantum import Circuit, QpiAIQuantumAuth

from ising_encoding import coefficients
from runtime_config import api_key


def execute(model):
    n = len(model["names"])
    if n > 12:
        raise ValueError("Circuit demo limited to 12 qubits")
    q = model["coefficients"]
    scale, constant, h, jj = coefficients(n, q, model["offset"])

    def energy(bits):
        return model["offset"] + sum(v * bits[i] * bits[j] for i, j, v in q)

    QpiAIQuantumAuth.login(api_key("QPIAI_QCLOUD_API_KEY"))
    # Empirically establish every logical-qubit -> returned-character position.
    positions = []
    for k in range(n):
        c = Circuit(n, n)
        c.x(k)
        c.measure_all()
        counts = c.run(shots=8, device_name="QpiAI-QSV-Local").counts
        key = max(counts, key=counts.get).replace(" ", "").zfill(n)
        if key.count("1") != 1:
            raise ValueError("Bit-order calibration failed")
        positions.append(key.index("1"))
    if len(set(positions)) != n:
        raise ValueError("Invalid measurement mapping")

    def run(gamma, beta, shots):
        c = Circuit(n, n)
        for i in range(n):
            c.h(i)
        for i, a in enumerate(h):
            c.rz(i, 2 * gamma * a)
        for i, j, a in jj:
            c.cx(i, j)
            c.rz(j, 2 * gamma * a)
            c.cx(i, j)
        for i in range(n):
            c.rx(i, 2 * beta)
        c.measure_all()
        counts = c.run(shots=shots, device_name="QpiAI-QSV-Local").counts
        if sum(counts.values()) != shots:
            raise ValueError("Shot count mismatch")
        samples = []
        for key, count in counts.items():
            key = key.replace(" ", "").zfill(n)
            bits = [int(key[p]) for p in positions]
            samples.append({"bits": bits, "count": count, "energy": energy(bits)})
        return sum(s["energy"] * s["count"] / shots for s in samples), samples

    trace = []
    started = time.perf_counter()
    for gamma, beta in itertools.product([0.3, 0.8, 1.5, 2.4], [0.2, 0.6, 1.0, 1.4]):
        avg, _ = run(gamma, beta, 128)
        trace.append({"gamma": gamma, "beta": beta, "mean_energy": avg})
    chosen = min(trace, key=lambda x: x["mean_energy"])
    avg, samples = run(chosen["gamma"], chosen["beta"], 1024)
    best = min(samples, key=lambda s: s["energy"])
    _, uniform = run(0, 0, 1024)
    return {
        "bits": best["bits"],
        "method": "depth-1 QAOA / QpiAI-QSV-Local",
        "termination": "sampled",
        "execution_mode": "local simulator",
        "hardware": False,
        "qubits": n,
        "shots_search": 2048,
        "shots_final": 1024,
        "shots_uniform_control": 1024,
        "calibration_shots": 8 * n,
        "circuits": 18 + n,
        "depth_p": 1,
        "scale": scale,
        "qubit_to_character": positions,
        "angles": chosen,
        "search_trace": trace,
        "samples": samples,
        "uniform_samples": uniform,
        "seconds": time.perf_counter() - started,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            answer = execute(data)
        print(json.dumps(answer))
    except Exception:
        print(
            json.dumps(
                {
                    "error": "QCloud QAOA execution failed; check SDK and authentication. No fallback used."
                }
            )
        )
        sys.exit(1)
