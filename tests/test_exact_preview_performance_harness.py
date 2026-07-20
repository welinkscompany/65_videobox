from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


def _harness():
    path = Path(__file__).parents[1] / "scripts" / "measure_exact_preview_performance.py"
    spec = importlib.util.spec_from_file_location("exact_preview_performance_harness", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_exact_preview_performance_harness_reports_the_declared_manual_gates() -> None:
    harness = _harness()

    assert harness.COLD_RENDER_LIMIT_SECONDS == 20.0
    assert harness.WARM_CACHE_LIMIT_SECONDS == 0.5
    assert harness.assess_performance(cold_seconds=19.9, warm_seconds=0.49) == {"cold_pass": True, "warm_pass": True}
    assert harness.assess_performance(cold_seconds=20.1, warm_seconds=0.49)["cold_pass"] is False
    assert harness.assess_performance(cold_seconds=19.9, warm_seconds=0.51)["warm_pass"] is False


def test_local_exact_preview_performance_harness_can_start_from_the_repository_root() -> None:
    root = Path(__file__).parents[1]

    result = subprocess.run([sys.executable, "scripts/measure_exact_preview_performance.py", "--help"], cwd=root, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "--enforce" in result.stdout
