"""Authenticated local QpiAI Opt adapter; never silently falls back or submits cloud work."""

import contextlib
import io
from types import SimpleNamespace

import numpy as np

from runtime_config import api_key


def solve_qubo(model, seed=7):
    from qpiai_opt.opt_solvers import Client, solve
    from qpiai_opt.opt_solvers.qubo import QUBOProblem

    key = api_key("QPIAI_OPT_API_KEY")
    problem = QUBOProblem(
        num_variables=len(model["names"]),
        qubo_dict=model["q"],
        matrix_format="upper",
        offset=model["offset"],
        variable_names=tuple(model["names"]),
    )
    # Bound annealing work conservatively within the SDK free-local contract.
    terms = len(model["q"])
    sweeps = max(1, min(1500, int((9000000 / 8 - 2 * terms) / (len(model["names"]) + 2 * terms))))
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            solver_result = solve(
                problem,
                client=Client(api_key=key),
                mode="local",
                allow_platform=False,
                num_reads=8,
                num_sweeps=sweeps,
                seed=seed,
            )
    except Exception as e:
        raise ValueError(
            f"Opt QUBO failed: {str(e).replace(key, '[REDACTED]')[:400]}. No cloud job or fallback used."
        ) from None
    info = solver_result.info()
    return SimpleNamespace(
        x=None
        if solver_result.solution is None
        else np.asarray(solver_result.solution, dtype=float),
        evidence={
            "method": info.method,
            "termination": info.termination,
            "execution_mode": solver_result.execution_mode,
            "solver_seconds": solver_result.solver_time_s,
            "compute_seconds": solver_result.compute_time_s,
            "seed": seed,
            "requested_reads": 8,
            "requested_sweeps": sweeps,
        },
    )


def solve_matrix(c, A, lower, upper, lo, hi, integrality=None):
    from qpiai_opt.opt_solvers import Client, solve

    key = api_key("QPIAI_OPT_API_KEY")
    names = [f"x{i}" for i in range(len(c))]
    domains = (
        np.r_[np.ones(len(c) - 1, dtype=np.int32), np.int32(0)]
        if integrality is None
        else np.asarray(integrality, dtype=np.int32)
    )
    problem = {
        "problem_type": "MILP" if np.any(domains) else "LP",
        "objective": np.asarray(c, dtype=float),
        "constraint_matrix": A.tocsr(),
        "row_lower": lower,
        "row_upper": upper,
        "lower_bounds": lo,
        "upper_bounds": hi,
        "integrality": domains,
        "variable_names": names,
    }
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            options = {"mip_rel_gap": 1e-7} if np.any(domains) else {}
            solver_result = solve(
                problem,
                client=Client(api_key=key),
                mode="local",
                allow_platform=False,
                time_limit=20,
                **options,
            )
    except Exception as e:
        detail = str(e).replace(key, "[REDACTED]")[:500]
        raise ValueError(
            f"QpiAI Opt local solve failed ({type(e).__name__}): {detail}. No fallback or cloud job was used."
        ) from None
    info = solver_result.info()
    termination = info.termination
    x = (
        None
        if solver_result.solution is None
        else np.array([solver_result.solution[n] for n in names])
    )
    return SimpleNamespace(
        x=x,
        status=0 if termination == "optimal" else 2 if termination == "infeasible" else 1,
        mip_gap=getattr(solver_result, "mip_gap", None),
        evidence={
            "provider": "QpiAI Opt",
            "execution_mode": solver_result.execution_mode,
            "problem_class": solver_result.problem_class,
            "method": info.method,
            "termination": termination,
            "solver_seconds": solver_result.solver_time_s,
            "compute_seconds": solver_result.compute_time_s,
        },
    )
