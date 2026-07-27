"""Read laptop CPU/RAM and compute safe Ollama thread limits.

Ollama uses CPU threads during inference (especially when the model does not
fully fit in GPU VRAM). Using every logical thread can freeze the UI — so we
leave headroom for Windows and Streamlit.

Also provides a CPU-load safety guard: when the machine is overloaded, stop
generation / block heavy work so the laptop stays responsive.
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil

# Defaults tuned for a laptop (e.g. i5 + 16GB). Override via check_cpu_safety(...).
DEFAULT_WARN_CPU_PERCENT = 85.0
DEFAULT_CRITICAL_CPU_PERCENT = 95.0
DEFAULT_WARN_RAM_PERCENT = 90.0
DEFAULT_CRITICAL_RAM_PERCENT = 95.0


@dataclass
class SystemResources:
    physical_cores: int
    logical_cores: int
    ram_total_gb: float
    ram_used_gb: float
    ram_available_gb: float
    ram_percent: float
    ollama_rss_gb: float | None
    safe_min_threads: int
    safe_max_threads: int
    recommended_threads: int
    cpu_percent: float = 0.0


@dataclass
class CpuSafetyStatus:
    """Result of a CPU/RAM safety check."""

    ok: bool
    level: str  # ok | warn | critical
    cpu_percent: float
    ram_percent: float
    message: str
    should_stop_work: bool = False


def _ollama_memory_gb() -> float | None:
    """Sum resident memory of Ollama processes, if any are running."""
    total = 0.0
    found = False
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "ollama" not in name:
                continue
            mem = proc.info.get("memory_info")
            if mem is None:
                continue
            total += float(mem.rss)
            found = True
        except (psutil.Error, TypeError, ValueError):
            continue
    if not found:
        return None
    return round(total / (1024**3), 2)


def sample_cpu_percent(interval: float = 0.15) -> float:
    """Measure current CPU load (%). Short interval keeps UI snappy."""
    try:
        return round(float(psutil.cpu_percent(interval=interval)), 1)
    except Exception:
        return 0.0


def get_system_resources(*, sample_cpu: bool = True) -> SystemResources:
    """Snapshot CPU/RAM and safe thread bounds for this machine."""
    physical = psutil.cpu_count(logical=False) or 1
    logical = psutil.cpu_count(logical=True) or physical
    vm = psutil.virtual_memory()
    cpu_percent = sample_cpu_percent(0.1) if sample_cpu else 0.0

    # Leave at least 1 logical thread for OS + Streamlit UI.
    # Cap at physical cores when possible — hyperthreads help less for LLM math.
    safe_max = max(1, min(logical - 1, physical))
    # On tiny CPUs (2 cores), still allow at least 1 thread.
    if logical <= 2:
        safe_max = 1
    safe_min = 1
    # Balanced default: ~75% of safe max, at least 1
    recommended = max(safe_min, max(1, round(safe_max * 0.75)))

    return SystemResources(
        physical_cores=int(physical),
        logical_cores=int(logical),
        ram_total_gb=round(vm.total / (1024**3), 1),
        ram_used_gb=round(vm.used / (1024**3), 1),
        ram_available_gb=round(vm.available / (1024**3), 1),
        ram_percent=round(float(vm.percent), 1),
        ollama_rss_gb=_ollama_memory_gb(),
        safe_min_threads=safe_min,
        safe_max_threads=int(safe_max),
        recommended_threads=int(recommended),
        cpu_percent=cpu_percent,
    )


def check_cpu_safety(
    *,
    warn_cpu: float = DEFAULT_WARN_CPU_PERCENT,
    critical_cpu: float = DEFAULT_CRITICAL_CPU_PERCENT,
    warn_ram: float = DEFAULT_WARN_RAM_PERCENT,
    critical_ram: float = DEFAULT_CRITICAL_RAM_PERCENT,
    cpu_percent: float | None = None,
    ram_percent: float | None = None,
) -> CpuSafetyStatus:
    """
    Decide whether the machine is safe for more AI work.

    - warn: show a warning, allow work
    - critical: stop generation / block new heavy jobs
    """
    cpu = float(cpu_percent if cpu_percent is not None else sample_cpu_percent(0.15))
    if ram_percent is None:
        ram = float(psutil.virtual_memory().percent)
    else:
        ram = float(ram_percent)

    if cpu >= critical_cpu or ram >= critical_ram:
        parts = []
        if cpu >= critical_cpu:
            parts.append(f"CPU {cpu:.0f}% (limit {critical_cpu:.0f}%)")
        if ram >= critical_ram:
            parts.append(f"RAM {ram:.0f}% (limit {critical_ram:.0f}%)")
        return CpuSafetyStatus(
            ok=False,
            level="critical",
            cpu_percent=cpu,
            ram_percent=ram,
            message=(
                "Safety stop: laptop is overloaded — "
                + ", ".join(parts)
                + ". AI work was stopped so Windows stays responsive. "
                "Close other apps, wait a few seconds, then click Unlock."
            ),
            should_stop_work=True,
        )

    if cpu >= warn_cpu or ram >= warn_ram:
        parts = []
        if cpu >= warn_cpu:
            parts.append(f"CPU {cpu:.0f}%")
        if ram >= warn_ram:
            parts.append(f"RAM {ram:.0f}%")
        return CpuSafetyStatus(
            ok=True,
            level="warn",
            cpu_percent=cpu,
            ram_percent=ram,
            message=(
                "High load ("
                + ", ".join(parts)
                + "). Consider lowering CPU threads or pausing generation."
            ),
            should_stop_work=False,
        )

    return CpuSafetyStatus(
        ok=True,
        level="ok",
        cpu_percent=cpu,
        ram_percent=ram,
        message=f"Load OK — CPU {cpu:.0f}%, RAM {ram:.0f}%.",
        should_stop_work=False,
    )


def clamp_threads(requested: int, resources: SystemResources | None = None) -> int:
    """Force a thread count into the safe UI range."""
    info = resources or get_system_resources(sample_cpu=False)
    return max(info.safe_min_threads, min(int(requested), info.safe_max_threads))
