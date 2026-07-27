"""Tests for safe CPU thread limits and CPU safety guard."""

from src.system_info import SystemResources, check_cpu_safety, clamp_threads


def test_clamp_threads_respects_safe_max() -> None:
    info = SystemResources(
        physical_cores=4,
        logical_cores=8,
        ram_total_gb=16.0,
        ram_used_gb=8.0,
        ram_available_gb=8.0,
        ram_percent=50.0,
        ollama_rss_gb=2.0,
        safe_min_threads=1,
        safe_max_threads=4,
        recommended_threads=3,
        cpu_percent=20.0,
    )
    assert clamp_threads(99, info) == 4
    assert clamp_threads(0, info) == 1
    assert clamp_threads(3, info) == 3


def test_cpu_safety_critical_stops_work() -> None:
    status = check_cpu_safety(cpu_percent=97.0, ram_percent=40.0)
    assert status.level == "critical"
    assert status.should_stop_work is True
    assert status.ok is False


def test_cpu_safety_warn() -> None:
    status = check_cpu_safety(cpu_percent=88.0, ram_percent=50.0)
    assert status.level == "warn"
    assert status.should_stop_work is False


def test_cpu_safety_ok() -> None:
    status = check_cpu_safety(cpu_percent=30.0, ram_percent=40.0)
    assert status.level == "ok"
    assert status.should_stop_work is False


def test_ram_critical_stops_work() -> None:
    status = check_cpu_safety(cpu_percent=20.0, ram_percent=96.0)
    assert status.level == "critical"
    assert status.should_stop_work is True
