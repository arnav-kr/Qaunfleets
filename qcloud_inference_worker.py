"""Isolated Quantum SDK process. JSON only on stdout; credentials never returned."""

import contextlib
import io
import json
import sys

import numpy as np
from qpiai_quantum import Circuit, QpiAIQuantumAuth

from runtime_config import api_key


def run(angles):
    features = []
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        QpiAIQuantumAuth.login(api_key("QPIAI_QCLOUD_API_KEY"))
        for row in angles:
            circuit = Circuit(6, 6)
            for i, angle in enumerate(row):
                circuit.ry(i, angle)
                circuit.rz(i, angle * 0.5)
            for i in range(5):
                circuit.cx(i, i + 1)
            for i, angle in enumerate(row):
                circuit.ry(i, angle * 0.7)
            circuit.measure_all()
            counts = circuit.run(shots=512, device_name="QpiAI-QSV-Local").counts
            if sum(counts.values()) != 512:
                raise ValueError("Shot count mismatch")
            observables = np.zeros(12)
            for bits, count in counts.items():
                spin_values = np.array([1 - 2 * int(b) for b in bits.replace(" ", "").zfill(6)])
                observables[:6] += count * spin_values / 512
                observables[6:] += count * spin_values * np.roll(spin_values, 1) / 512
            features.append(observables.tolist())
    return {
        "features": features,
        "backend": "QpiAI-QSV-Local",
        "shots": 512,
        "qubits": 6,
        "circuits": len(features),
        "hardware": False,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin)["angles"])))
    except Exception:
        print(
            json.dumps(
                {
                    "error": "QCloud local circuit execution failed; check local authentication and SDK installation."
                }
            )
        )
        sys.exit(1)
