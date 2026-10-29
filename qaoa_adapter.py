import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from runtime_config import quantum_python


def solve_qaoa(model):
    root = Path(__file__).parent
    if len(model["names"]) > 12:
        raise ValueError("QCloud QAOA demo is limited to 12 qubits; use Opt for larger instances")
    public = {k: v for k, v in model.items() if k != "q"}
    public["coefficients"] = [[i, j, v] for (i, j), v in model["q"].items()]
    r = subprocess.run(
        [quantum_python(), str(root / "qaoa_worker.py")],
        input=json.dumps(public),
        text=True,
        capture_output=True,
        timeout=180,
        cwd=root,
    )
    if r.returncode:
        raise ValueError("QCloud QAOA failed; no classical fallback used")
    evidence = json.loads(r.stdout)
    return SimpleNamespace(x=np.asarray(evidence.pop("bits"), float), evidence=evidence)
