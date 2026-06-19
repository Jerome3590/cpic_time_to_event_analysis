"""
Environment and OS-aware configuration helpers for PGx pipelines.

This module centralizes:
- OS detection (Linux vs Windows)
- CPU/RAM detection
- Sensible defaults for parallelism in feature engineering and model training
- OS-specific output root paths (NVMe on EC2, user directory on Windows)

Scripts can either:
- Call `configure_pgx_environment()` once at startup to populate os.environ, or
- Use the individual helper functions (e.g., `get_sklearn_n_jobs()`,
  `get_data_root()`, `ensure_output_dir(...)`).
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

# EC2 Jupyter env Python (docs/CrossStep_Development/README_ec2_runtime.md)
EC2_PYTHON_PATH = Path("/home/pgx3874/jupyter-env/bin/python3.11")


def get_workflow_python_bin() -> Path:
    """Return Python executable for workflow subprocess calls (notebooks, scripts).

    Prefer PGX_PYTHON env, then EC2 path if it exists, else sys.executable.
    Use this when invoking Python scripts from notebooks or other scripts so the
    same environment (e.g. Jupyter kernel env on EC2) is used.
    """
    env_bin = os.environ.get("PGX_PYTHON")
    if env_bin and Path(env_bin).exists():
        return Path(env_bin)
    if EC2_PYTHON_PATH.exists():
        return EC2_PYTHON_PATH
    return Path(sys.executable)


@dataclass
class SystemResources:
    os_type: str
    cpu_cores: int
    total_ram_gb: int


def _detect_total_ram_gb() -> int:
    """Best-effort detection of total system RAM in GB."""
    # Prefer psutil if available
    try:
        import psutil  # type: ignore

        return max(1, int(psutil.virtual_memory().total / (1024**3)))
    except Exception:
        pass

    # Fallback for Linux using /proc/meminfo
    if os.name == "posix":
        try:
            mem_kb = 0
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.lower().startswith("memtotal:"):
                        parts = line.split()
                        mem_kb = int(parts[1])
                        break
            if mem_kb > 0:
                return max(1, mem_kb // 1024 // 1024)
        except Exception:
            pass

    # Conservative default if detection fails
    return 16


def detect_system_resources() -> SystemResources:
    """Detect OS type, CPU cores, and total RAM (GB)."""
    os_type = platform.system() or "unknown"
    cpu_cores = os.cpu_count() or 1
    total_ram_gb = _detect_total_ram_gb()
    return SystemResources(os_type=os_type, cpu_cores=cpu_cores, total_ram_gb=total_ram_gb)


def recommend_parallelism(resources: SystemResources) -> Dict[str, int | str]:
    """
    Recommend parallelism settings based on system resources.

    Mirrors thresholds used in `utility_scripts/sync_pgx_to_nvme.sh` so
    EC2 and Windows behave consistently.
    """
    ram = resources.total_ram_gb

    # Medical workers and DuckDB per-worker memory
    if ram >= 512:
        workers_medical = 28
    elif ram >= 128:
        workers_medical = 18
    elif ram >= 64:
        workers_medical = 12
    else:
        workers_medical = 8

    if ram >= 256:
        duckdb_mem = "3GB"
    elif ram >= 64:
        duckdb_mem = "2GB"
    else:
        duckdb_mem = "1GB"

    # Feature engineering / model training
    if ram >= 256:
        sklearn_n_jobs = 8
        mc_cv_workers = 8
    elif ram >= 64:
        sklearn_n_jobs = 4
        mc_cv_workers = 4
    else:
        sklearn_n_jobs = 2
        mc_cv_workers = 2

    xgb_cpu_nthread = sklearn_n_jobs

    return {
        "PGX_WORKERS_MEDICAL": workers_medical,
        "PGX_DUCKDB_MEMORY_LIMIT": duckdb_mem,
        "PGX_THREADS_PER_WORKER": 1,
        "PGX_SKLEARN_N_JOBS": sklearn_n_jobs,
        "PGX_XGB_CPU_NTHREAD": xgb_cpu_nthread,
        "PGX_MC_CV_WORKERS": mc_cv_workers,
    }


def configure_pgx_environment(overwrite: bool = False) -> SystemResources:
    """
    Detect system resources and populate PGX_* environment variables.

    - On Linux/EC2, this works well with NVMe layouts (see sync_pgx_to_nvme.sh).
    - On Windows, it chooses conservative defaults so scripts do not over-commit.

    Args:
        overwrite: If True, always overwrite any existing PGX_* env values.

    Returns:
        SystemResources with detected OS, cores, and RAM.
    """
    resources = detect_system_resources()
    os.environ.setdefault("PGX_OS_TYPE", resources.os_type)
    os.environ.setdefault("PGX_CPU_CORES", str(resources.cpu_cores))
    os.environ.setdefault("PGX_TOTAL_RAM_GB", str(resources.total_ram_gb))

    rec = recommend_parallelism(resources)
    for key, value in rec.items():
        if overwrite or key not in os.environ:
            os.environ[key] = str(value)

    return resources


def is_windows() -> bool:
    return os.name == "nt"


def is_linux() -> bool:
    return os.name == "posix" and platform.system() == "Linux"


def get_data_root() -> Path:
    """
    Get the root directory for shared large input data files.

    Precedence:
    1. PGX_DATA_ROOT env var (if set)
    2. On Linux: /mnt/nvme (shared gold medical/pharmacy/cohort inputs)
    3. On Windows: %USERPROFILE%/pgx_data
    4. Fallback: project_root / "data"
    """
    env_root = os.getenv("PGX_DATA_ROOT")
    if env_root:
        return Path(env_root)

    if is_linux():
        return Path("/mnt/nvme")

    if is_windows():
        return Path(os.path.expanduser("~")) / "pgx_data"

    # Fallback: project root / data
    project_root = get_repo_root()
    return project_root / "data"


def get_project_slug() -> str:
    """Return the project slug used to namespace generated artifacts."""
    return os.environ.get("CPIC_PROJECT_SLUG", "cpic_time_to_event")


def get_project_data_root() -> Path:
    """
    Get the root directory for generated project artifacts.

    Shared inputs may still live under get_data_root()/gold/{medical,pharmacy}.
    Generated EC2 artifacts should use this project-scoped root so cleanup can
    safely target only this repository's outputs.

    Precedence:
    1. CPIC_PROJECT_DATA_ROOT or CPIC_PROJECT_NVME_ROOT env var
    2. On Linux: CPIC_NVME_ROOT/<project_slug>, default /mnt/nvme/cpic_time_to_event
    3. On Windows/other: project_root
    """
    env_root = os.getenv("CPIC_PROJECT_DATA_ROOT") or os.getenv("CPIC_PROJECT_NVME_ROOT")
    if env_root:
        return Path(env_root)

    project_root = get_repo_root()
    if is_linux():
        nvme_root = Path(os.getenv("CPIC_NVME_ROOT", "/mnt/nvme"))
        return nvme_root / get_project_slug()

    return project_root


def get_repo_root(anchor: Path | None = None) -> Path:
    """
    Return the project (cpic_time_to_event_analysis) root by walking up from anchor until a directory
    containing 'py_helpers' is found. Use this so logs and paths resolve to the project
    even when scripts are run from 9_dashboard_visuals or another subfolder (e.g. logs
    go to project/9_dashboard_visuals/logs/ not home/9_dashboard_visuals/logs/).
    """
    if anchor is None:
        anchor = Path(__file__).resolve().parent
    if anchor.is_file():
        anchor = anchor.parent
    current = anchor
    for _ in range(20):
        if (current / "py_helpers").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return anchor


def get_model_data_root() -> Path:
    """
    Single canonical root for model data (model_events.parquet per cohort/age_band).

    Use this one project-scoped location for efficiency; do not use
    gold/model_training_data or other duplicate paths. S3 mirror:
    gold/{PROJECT_SLUG}/cohorts_model_data/.

    - Linux/EC2: get_project_data_root() / "4_model_data"
      (e.g. /mnt/nvme/cpic_time_to_event/4_model_data)
    - Windows: PROJECT_ROOT / "4_model_data"
    """
    project_root = get_repo_root()
    if is_linux():
        return get_project_data_root() / "4_model_data"
    return project_root / "4_model_data"


def get_feature_importance_root() -> Path:
    """
    Canonical root for generated feature-importance artifacts.

    Feature importance is target-dependent, so EC2/NVMe outputs are kept under
    the project-scoped artifact root by default. S3 mirror:
    gold/{PROJECT_SLUG}/feature_importance/.
    """
    env_root = os.getenv("CPIC_FEATURE_IMPORTANCE_ROOT") or os.getenv("PGX_FEATURE_IMPORTANCE_OUTPUTS")
    if env_root:
        return Path(env_root)

    project_root = get_repo_root()
    if is_linux():
        return get_project_data_root() / "3a_feature_importance" / "outputs"
    return project_root / "3a_feature_importance" / "outputs"


def get_refined_feature_importance_root() -> Path:
    """
    Canonical root for Step 3b refined feature-importance artifacts.

    Refined feature lists are also target-dependent, so EC2/NVMe outputs use
    the project-scoped artifact root by default. S3 mirror:
    gold/{PROJECT_SLUG}/feature_importance/.
    """
    env_root = os.getenv("CPIC_REFINED_FEATURE_IMPORTANCE_ROOT") or os.getenv("PGX_REFINED_FEATURE_IMPORTANCE_OUTPUTS")
    if env_root:
        return Path(env_root)

    project_root = get_repo_root()
    if is_linux():
        return get_project_data_root() / "3b_feature_importance_eda" / "outputs"
    return project_root / "3b_feature_importance_eda" / "outputs"


def ensure_output_dir(*parts: str, use_data_root: bool = True) -> Path:
    """
    Build and create an output directory, with OS-aware root selection.

    Example usages:
        out_dir = ensure_output_dir("cohorts", cohort_name, age_band)
        model_dir = ensure_output_dir("model_data", cohort_name, age_band)

    Args:
        *parts: Path components under the chosen root.
        use_data_root: If True, root is get_data_root(); otherwise project root.
    """
    if use_data_root:
        root = get_project_data_root()
    else:
        root = Path(__file__).resolve().parents[1]

    path = root.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_mc_cv_n_splits(default: int | None = None) -> int:
    """
    Get recommended number of MC-CV splits based on environment.

    - On EC2 (Linux with >= 256GB RAM): 50 splits (faster, still robust)
    - On Windows or smaller systems: 200 splits (default for thoroughness)

    Args:
        default: Override value if provided.

    Returns:
        Recommended n_splits for StratifiedShuffleSplit.
    """
    if default is not None:
        return default

    env_val = os.getenv("PGX_MC_CV_N_SPLITS")
    if env_val and env_val.isdigit():
        return int(env_val)

    # Auto-detect: EC2 gets 50, Windows gets 200
    resources = detect_system_resources()
    if is_linux() and resources.total_ram_gb >= 256:
        return 50
    return 200


def get_mc_cv_n_runs(default: int | None = None) -> int:
    """
    Get recommended number of MC-CV runs (outer loop) based on environment.

    - On EC2 (Linux with >= 256GB RAM): 25 runs (matches feature importance step)
    - On Windows or smaller systems: 1 run (default)

    Args:
        default: Override value if provided.

    Returns:
        Recommended n_runs for Monte-Carlo outer loop.
    """
    if default is not None:
        return default

    env_val = os.getenv("PGX_MC_CV_N_RUNS")
    if env_val and env_val.isdigit():
        return int(env_val)

    # Auto-detect: EC2 gets 25 (matches feature importance step), Windows gets 1
    resources = detect_system_resources()
    if is_linux() and resources.total_ram_gb >= 256:
        return 25
    return 1


def get_sklearn_n_jobs(default: int | None = None) -> int:
    """
    Resolve sklearn n_jobs from env or recommended defaults.

    If PGX_SKLEARN_N_JOBS is not set, this will run configure_pgx_environment()
    once to derive a safe value.
    """
    env_val = os.getenv("PGX_SKLEARN_N_JOBS")
    if env_val and env_val.isdigit():
        return int(env_val)

    resources = configure_pgx_environment(overwrite=False)
    rec = recommend_parallelism(resources)
    return int(rec["PGX_SKLEARN_N_JOBS"])


def get_cpu_cores() -> int:
    """Return the number of CPU cores (for n_jobs = number of cores)."""
    return os.cpu_count() or 1


def get_xgb_cpu_nthread(default: int | None = None) -> int:
    """
    Resolve XGBoost CPU nthread from env or recommended defaults.

    Maps to PGX_XGB_CPU_NTHREAD with the same detection logic as
    get_sklearn_n_jobs().
    """
    env_val = os.getenv("PGX_XGB_CPU_NTHREAD")
    if env_val and env_val.isdigit():
        return int(env_val)

    resources = configure_pgx_environment(overwrite=False)
    rec = recommend_parallelism(resources)
    return int(rec["PGX_XGB_CPU_NTHREAD"])


def get_mc_cv_workers(default: int | None = None) -> int:
    """
    Resolve Monte Carlo CV worker count from env or recommended defaults.
    """
    env_val = os.getenv("PGX_MC_CV_WORKERS")
    if env_val and env_val.isdigit():
        return int(env_val)

    resources = configure_pgx_environment(overwrite=False)
    rec = recommend_parallelism(resources)
    return int(rec["PGX_MC_CV_WORKERS"])

