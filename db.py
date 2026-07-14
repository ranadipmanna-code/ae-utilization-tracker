"""
Database access layer.

Two connections:
  * CMIS  (read-only)  -> faculty sessions, from `upcoming_trainer_utilization_view`
  * appdb (read/write) -> the 5 Anudip_AE_Team tables:
        core_ae_faculty_map, extended_ae_session_selection,
        session_highlight_flags, user_roles, weekly_ae_summary

Uses SQLAlchemy engines with pooling. Credentials come from st.secrets.
All CMIS access is strictly SELECT — we never write there.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _make_engine(section: str) -> Engine:
    cfg = st.secrets[section]
    url = (
        f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}?charset=utf8mb4"
    )
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, future=True)


@st.cache_resource
def cmis_engine() -> Engine:
    return _make_engine("cmis")


@st.cache_resource
def app_engine() -> Engine:
    return _make_engine("appdb")


# ---------------------------------------------------------------------------
# CMIS reads (faculty sessions)
# ---------------------------------------------------------------------------
CMIS_VIEW = "upcoming_trainer_utilization_view"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_sessions_for_faculty(faculty_emails: tuple[str, ...], week_start: date, week_end: date) -> pd.DataFrame:
    """All CMIS sessions for the given faculty emails within [week_start, week_end]."""
    if not faculty_emails:
        return pd.DataFrame()
    placeholders = ", ".join(f":e{i}" for i in range(len(faculty_emails)))
    params: dict[str, Any] = {f"e{i}": e for i, e in enumerate(faculty_emails)}
    params["ws"] = week_start
    params["we"] = week_end
    sql = text(
        f"""
        SELECT s_date, m_code, f_name, l_name, time_duration, day_name,
               c_alias, slot_name, slot_time, batch_code, email_id,
               class_link, program_name
        FROM {CMIS_VIEW}
        WHERE email_id IN ({placeholders})
          AND s_date BETWEEN :ws AND :we
        ORDER BY s_date, slot_time
        """
    )
    with cmis_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=params)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_sessions_all(week_start: date, week_end: date, limit: int = 5000) -> pd.DataFrame:
    """All CMIS sessions in the window (admin overview)."""
    sql = text(
        f"""
        SELECT s_date, m_code, f_name, l_name, day_name, c_alias,
               slot_time, batch_code, email_id, program_name
        FROM {CMIS_VIEW}
        WHERE s_date BETWEEN :ws AND :we
        ORDER BY s_date, slot_time
        LIMIT :lim
        """
    )
    with cmis_engine().connect() as conn:
        return pd.read_sql(sql, conn, params={"ws": week_start, "we": week_end, "lim": limit})


# ---------------------------------------------------------------------------
# App DB reads
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def get_user_roles() -> pd.DataFrame:
    with app_engine().connect() as conn:
        return pd.read_sql(text("SELECT email, name, role FROM user_roles"), conn)


@st.cache_data(ttl=60, show_spinner=False)
def get_core_ae_faculty_map() -> pd.DataFrame:
    with app_engine().connect() as conn:
        return pd.read_sql(
            text(
                "SELECT core_ae_email, faculty_1, faculty_2, faculty_3, faculty_4, faculty_5 "
                "FROM core_ae_faculty_map"
            ),
            conn,
        )


def faculty_emails_for_core(core_ae_email: str) -> list[str]:
    df = get_core_ae_faculty_map()
    rows = df[df["core_ae_email"] == core_ae_email]
    out: list[str] = []
    for _, r in rows.iterrows():
        for c in ("faculty_1", "faculty_2", "faculty_3", "faculty_4", "faculty_5"):
            v = r[c]
            if v and str(v).strip():
                out.append(str(v).strip())
    return sorted(set(out))


def list_core_ae_emails() -> list[str]:
    df = get_core_ae_faculty_map()
    return sorted(df["core_ae_email"].dropna().unique().tolist())


def get_selections(extended_ae_email: str | None, week_start: date, week_end: date) -> pd.DataFrame:
    where = "session_date BETWEEN :ws AND :we"
    params: dict[str, Any] = {"ws": week_start, "we": week_end}
    if extended_ae_email:
        where += " AND extended_ae_email = :eae"
        params["eae"] = extended_ae_email
    sql = text(
        f"""
        SELECT id, extended_ae_email, session_date, slot_time, module, batch_code, status
        FROM extended_ae_session_selection
        WHERE {where}
        """
    )
    with app_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=params)


# ---------------------------------------------------------------------------
# App DB writes
# ---------------------------------------------------------------------------
def upsert_selection(
    extended_ae_email: str,
    session_date: date,
    slot_time: str,
    module: str | None,
    batch_code: str | None,
    status: str,
) -> None:
    """
    One selection row per (extended_ae, date, slot, batch). Update status if it
    exists, else insert. `status` in: Not Selected / Choosing / Selected / Confirmed.
    """
    with app_engine().begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT id FROM extended_ae_session_selection
                WHERE extended_ae_email = :eae AND session_date = :d
                  AND slot_time = :st AND (batch_code <=> :bc)
                LIMIT 1
                """
            ),
            {"eae": extended_ae_email, "d": session_date, "st": slot_time, "bc": batch_code},
        ).fetchone()
        if existing:
            conn.execute(
                text("UPDATE extended_ae_session_selection SET status = :s, updated_on = NOW() WHERE id = :id"),
                {"s": status, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO extended_ae_session_selection
                        (extended_ae_email, session_date, slot_time, module, batch_code, status)
                    VALUES (:eae, :d, :st, :mod, :bc, :s)
                    """
                ),
                {"eae": extended_ae_email, "d": session_date, "st": slot_time,
                 "mod": module, "bc": batch_code, "s": status},
            )


def set_highlight_flag(
    session_date: date,
    slot_time: str,
    batch_code: str | None,
    core_ae_email: str,
    extended_ae_email: str | None,
    is_highlighted: bool,
) -> None:
    with app_engine().begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT id FROM session_highlight_flags
                WHERE session_date = :d AND slot_time = :st
                  AND (batch_code <=> :bc) AND core_ae_email = :cae
                LIMIT 1
                """
            ),
            {"d": session_date, "st": slot_time, "bc": batch_code, "cae": core_ae_email},
        ).fetchone()
        if existing:
            conn.execute(
                text(
                    "UPDATE session_highlight_flags "
                    "SET is_highlighted = :h, extended_ae_email = :eae, updated_on = NOW() WHERE id = :id"
                ),
                {"h": 1 if is_highlighted else 0, "eae": extended_ae_email, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO session_highlight_flags
                        (session_date, slot_time, batch_code, core_ae_email, extended_ae_email, is_highlighted)
                    VALUES (:d, :st, :bc, :cae, :eae, :h)
                    """
                ),
                {"d": session_date, "st": slot_time, "bc": batch_code,
                 "cae": core_ae_email, "eae": extended_ae_email, "h": 1 if is_highlighted else 0},
            )


def upsert_weekly_summary(
    core_ae_email: str, week_start: date, total: int, selected: int, observed: int
) -> None:
    with app_engine().begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM weekly_ae_summary WHERE core_ae_email = :c AND week_start_date = :w LIMIT 1"),
            {"c": core_ae_email, "w": week_start},
        ).fetchone()
        if existing:
            conn.execute(
                text(
                    "UPDATE weekly_ae_summary SET total_sessions=:t, sessions_selected=:s, "
                    "sessions_observed=:o, updated_on=NOW() WHERE id=:id"
                ),
                {"t": total, "s": selected, "o": observed, "id": existing[0]},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO weekly_ae_summary "
                    "(core_ae_email, week_start_date, total_sessions, sessions_selected, sessions_observed) "
                    "VALUES (:c, :w, :t, :s, :o)"
                ),
                {"c": core_ae_email, "w": week_start, "t": total, "s": selected, "o": observed},
            )


def ping() -> tuple[bool, bool]:
    """Return (cmis_ok, appdb_ok) for the connection self-test."""
    cmis_ok = appdb_ok = False
    try:
        with cmis_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        cmis_ok = True
    except Exception:
        pass
    try:
        with app_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        appdb_ok = True
    except Exception:
        pass
    return cmis_ok, appdb_ok
