"""CPU/RAM safety guard UI — auto-stops AI work when the laptop is overloaded."""

from __future__ import annotations

from dataclasses import dataclass

import psutil
import streamlit as st

from src.productivity.devlog import console

# Import from system_info when available; keep a local fallback so a stale
# Streamlit module cache never crashes the app with ImportError.
try:
    from src.system_info import check_cpu_safety
except ImportError:  # pragma: no cover

    @dataclass
    class _CpuSafetyStatus:
        ok: bool
        level: str
        cpu_percent: float
        ram_percent: float
        message: str
        should_stop_work: bool = False

    def check_cpu_safety(  # type: ignore[misc]
        *,
        warn_cpu: float = 85.0,
        critical_cpu: float = 95.0,
        warn_ram: float = 90.0,
        critical_ram: float = 95.0,
        cpu_percent: float | None = None,
        ram_percent: float | None = None,
    ):
        try:
            cpu = float(
                cpu_percent
                if cpu_percent is not None
                else psutil.cpu_percent(interval=0.15)
            )
        except Exception:
            cpu = 0.0
        try:
            ram = float(
                ram_percent
                if ram_percent is not None
                else psutil.virtual_memory().percent
            )
        except Exception:
            ram = 0.0

        if cpu >= critical_cpu or ram >= critical_ram:
            return _CpuSafetyStatus(
                ok=False,
                level="critical",
                cpu_percent=cpu,
                ram_percent=ram,
                message=(
                    f"Safety stop: laptop overloaded (CPU {cpu:.0f}%, RAM {ram:.0f}%). "
                    "AI work stopped. Close apps, then Unlock."
                ),
                should_stop_work=True,
            )
        if cpu >= warn_cpu or ram >= warn_ram:
            return _CpuSafetyStatus(
                ok=True,
                level="warn",
                cpu_percent=cpu,
                ram_percent=ram,
                message=f"High load (CPU {cpu:.0f}%, RAM {ram:.0f}%).",
                should_stop_work=False,
            )
        return _CpuSafetyStatus(
            ok=True,
            level="ok",
            cpu_percent=cpu,
            ram_percent=ram,
            message=f"Load OK — CPU {cpu:.0f}%, RAM {ram:.0f}%.",
            should_stop_work=False,
        )


def enforce_cpu_safety(*, during_generation: bool = False) -> bool:
    """
    Check load and apply safety actions.

    Returns True if it is safe to continue heavy work.
    On critical load: sets stop_generation + cpu_safety_lock.
    """
    enabled = st.session_state.get("cpu_safety_enabled", True)
    if not enabled:
        return True

    # If already locked by a previous critical event, keep blocking until unlock
    if st.session_state.get("cpu_safety_lock"):
        return False

    status = check_cpu_safety()
    st.session_state.cpu_safety_status = {
        "level": status.level,
        "cpu_percent": status.cpu_percent,
        "ram_percent": status.ram_percent,
        "message": status.message,
    }

    if status.level == "warn":
        if not during_generation:
            st.sidebar.warning(status.message)
        return True

    if status.should_stop_work:
        st.session_state.stop_generation = True
        st.session_state.cpu_safety_lock = True
        st.session_state.pending_prompt = None
        console.add(
            "CPU safety stop triggered",
            level="error",
            source="cpu_safety",
            detail=status.message,
        )
        return False

    return True


def render_cpu_safety_panel() -> None:
    """Sidebar controls for the CPU safety feature."""
    st.markdown("---")
    st.subheader("CPU safety")
    enabled = st.toggle(
        "Auto-stop when CPU/RAM is too high",
        value=st.session_state.get("cpu_safety_enabled", True),
        key="cpu_safety_enabled_toggle",
        help=(
            "If CPU ≥ 95% or RAM ≥ 95%, the app stops AI generation and blocks "
            "new heavy work until you unlock. Protects your laptop from freezes."
        ),
    )
    st.session_state.cpu_safety_enabled = enabled

    status = check_cpu_safety()
    st.caption(f"Now — CPU {status.cpu_percent:.0f}% · RAM {status.ram_percent:.0f}%")

    if st.session_state.get("cpu_safety_lock"):
        st.error(
            st.session_state.get("cpu_safety_status", {}).get("message")
            or status.message
        )
        if st.button("Unlock AI work (load cooled down)", type="primary", key="cpu_unlock"):
            again = check_cpu_safety()
            if again.should_stop_work:
                st.warning(
                    f"Still too high (CPU {again.cpu_percent:.0f}%, "
                    f"RAM {again.ram_percent:.0f}%). Close apps and try again."
                )
            else:
                st.session_state.cpu_safety_lock = False
                st.session_state.stop_generation = False
                console.add("CPU safety unlocked", source="cpu_safety")
                st.success("Unlocked — you can generate again.")
                st.rerun()
        if st.button("Force quit Streamlit process", key="cpu_force_quit"):
            console.add("Force quit requested", level="warn", source="cpu_safety")
            st.warning("Stopping Streamlit for safety…")
            raise SystemExit("CPU safety force quit")
    elif status.level == "warn":
        st.warning(status.message)
    else:
        st.success("Load OK for AI work")
