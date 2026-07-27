"""CPU/RAM safety guard UI — auto-stops AI work when the laptop is overloaded."""

from __future__ import annotations

import streamlit as st

from src.productivity.devlog import console
from src.system_info import check_cpu_safety


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
        # Soft warning only (avoid spamming during every stream chunk)
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
            # Re-check before unlocking
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
            # st.stop() ends this run; raising SystemExit ends the server worker.
            raise SystemExit("CPU safety force quit")
    elif status.level == "warn":
        st.warning(status.message)
    else:
        st.success("Load OK for AI work")
