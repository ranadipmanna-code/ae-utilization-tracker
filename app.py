"""
Extended AE Utilization Tracker — Streamlit edition.

Reads faculty sessions from the CMIS view (read-only) and reads/writes app
state to the Anudip_AE_Team database (the 5 hakathon tables).

Workflow (per the spec):
  Step 1  Pick week + Core AE.
  Step 2  Fetch that Core AE's faculty sessions from CMIS.
  Step 3  Highlight sessions available for Extended AE observation (yellow).
  Step 4  Extended AE claims sessions (status dropdown). Claimed -> GREEN.
  Step 5  Mock-interview auto-allocation from remaining capacity.

RBAC via user_roles.role:
  admin        -> any Core AE, full visibility
  core_ae      -> own faculty, can view + see team selections
  extended_ae  -> own paired Core AE's faculty, can claim
"""
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import db

st.set_page_config(page_title="AE Utilization Tracker", layout="wide")

STATUS_OPTIONS = ["Not Selected", "Choosing", "Selected", "Confirmed"]
CLAIMED = {"Selected", "Confirmed"}
WEEKLY_CAPACITY = 8


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def login_view():
    st.title("AE Utilization Tracker")
    st.caption("Sign in with your Anudip email. Demo password for all accounts is set in secrets.")
    with st.form("login"):
        email = st.text_input("Email").strip().lower()
        pwd = st.text_input("Password", type="password")
        ok = st.form_submit_button("Sign in")
    if ok:
        roles = db.get_user_roles()
        match = roles[roles["email"].str.lower() == email]
        if match.empty:
            st.error("Email not found in user_roles.")
            return
        if pwd != st.secrets["auth"]["shared_password"]:
            st.error("Incorrect password.")
            return
        row = match.iloc[0]
        st.session_state.user = {"email": row["email"], "name": row["name"], "role": row["role"]}
        st.rerun()


def current_week_bounds(offset_weeks: int = 0) -> tuple[date, date]:
    today = date.today() + timedelta(weeks=offset_weeks)
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------
def dashboard():
    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown(f"**{user['name']}**")
        st.caption(f"{user['email']} · {role}")
        if st.button("Sign out"):
            del st.session_state.user
            st.rerun()
        st.divider()
        cmis_ok, app_ok = db.ping()
        st.caption(f"CMIS DB: {'🟢' if cmis_ok else '🔴'}  ·  App DB: {'🟢' if app_ok else '🔴'}")

    st.title("Extended AE Utilization Tracker")

    # --- Step 1: week + Core AE selection ---
    c1, c2 = st.columns(2)
    with c1:
        week_labels = {}
        for off in range(-2, 5):
            ws, we = current_week_bounds(off)
            week_labels[f"{ws.strftime('%b %d')} – {we.strftime('%b %d, %Y')}" + (" (this week)" if off == 0 else "")] = ws
        default_idx = list(week_labels.values()).index(current_week_bounds(0)[0])
        wk_label = st.selectbox("Week", list(week_labels.keys()), index=default_idx)
        week_start = week_labels[wk_label]
        week_end = week_start + timedelta(days=6)

    with c2:
        core_options = _core_options_for(role, user["email"])
        if not core_options:
            st.warning("No Core AE mapping found for your account in core_ae_faculty_map.")
            return
        core_ae_email = st.selectbox("Core AE Member", core_options)

    faculty = db.faculty_emails_for_core(core_ae_email)
    if not faculty:
        st.info(f"No faculty mapped to {core_ae_email} in core_ae_faculty_map.")
        return

    # --- Step 2: fetch CMIS sessions for those faculty ---
    with st.spinner("Fetching faculty sessions from CMIS…"):
        sessions = db.fetch_sessions_for_faculty(tuple(faculty), week_start, week_end)

    if sessions.empty:
        st.info("No CMIS sessions for this Core AE's faculty in the selected week.")
        _mock_interview_section(week_start, week_end)
        return

    # --- Steps 3 & 4: highlight + claim ---
    _sessions_table(sessions, core_ae_email, week_start, week_end, role, user["email"])

    # Core AE / admin: team roll-up of what Extended AEs selected
    if role in ("core_ae", "admin"):
        _team_rollup(core_ae_email, week_start, week_end)

    # --- Step 5: mock interviews ---
    _mock_interview_section(week_start, week_end)


def _core_options_for(role: str, email: str) -> list[str]:
    all_cores = db.list_core_ae_emails()
    if role == "admin":
        return all_cores
    if role == "core_ae":
        return [c for c in all_cores if c.lower() == email.lower()] or all_cores
    # extended_ae -> the Core AE(s) whose faculty they observe. Without an
    # explicit pairing table we let them pick any; typically one.
    return all_cores


def _session_key(r) -> str:
    return f"{r['s_date']}|{r['slot_time']}|{r.get('batch_code','')}"


def _sessions_table(sessions, core_ae_email, week_start, week_end, role, user_email):
    st.subheader("Aligned Sessions — Faculty × Core AE × Extended AE")
    st.caption("Yellow = available for observation · Green = claimed (Selected/Confirmed)")

    is_extended = role == "extended_ae"

    # existing selections for this extended AE (to know green + current status)
    my_sel = db.get_selections(user_email if is_extended else None, week_start, week_end)
    sel_lookup = {}
    for _, s in my_sel.iterrows():
        sel_lookup[f"{s['session_date']}|{s['slot_time']}|{s['batch_code'] or ''}"] = s["status"]

    st.write(f"**{len(sessions)} sessions**")

    for _, r in sessions.iterrows():
        key = f"{r['s_date']}|{r['slot_time']}|{r['batch_code'] or ''}"
        status = sel_lookup.get(key, "Not Selected")
        claimed = status in CLAIMED

        # colour: green if claimed, else yellow (available for observation)
        bg = "#dcfce7" if claimed else "#fef9c3"
        border = "#16a34a" if claimed else "#eab308"

        col_info, col_action = st.columns([4, 1])
        with col_info:
            st.markdown(
                f"""<div style="background:{bg};border-left:4px solid {border};
                     padding:8px 12px;border-radius:6px;margin-bottom:4px;">
                     <b>{r['f_name']} {r['l_name']}</b> &nbsp;·&nbsp; {r['s_date']} {r['slot_time']}
                     &nbsp;·&nbsp; {r['program_name']} &nbsp;·&nbsp;
                     <span style="color:#555">batch {r['batch_code']}</span>
                     &nbsp; {'🟢 ' + status if claimed else '🟡 Available for Observation'}
                     </div>""",
                unsafe_allow_html=True,
            )
        with col_action:
            if is_extended:
                new_status = st.selectbox(
                    "status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0,
                    key=f"sel_{key}", label_visibility="collapsed",
                )
                if new_status != status:
                    db.upsert_selection(
                        user_email, pd.to_datetime(r["s_date"]).date(), r["slot_time"],
                        r["m_code"], r["batch_code"], new_status,
                    )
                    db.set_highlight_flag(
                        pd.to_datetime(r["s_date"]).date(), r["slot_time"], r["batch_code"],
                        core_ae_email, user_email, new_status in CLAIMED,
                    )
                    st.cache_data.clear()
                    st.rerun()


def _team_rollup(core_ae_email, week_start, week_end):
    st.subheader("My Extended AE Team — Selected Sessions")
    sel = db.get_selections(None, week_start, week_end)
    claimed = sel[sel["status"].isin(list(CLAIMED) + ["Choosing"])]
    if claimed.empty:
        st.caption("No Extended AE selections yet for this week.")
        return
    view = claimed[["extended_ae_email", "session_date", "slot_time", "module", "batch_code", "status"]]
    st.dataframe(view, use_container_width=True, hide_index=True)


def _mock_interview_section(week_start, week_end):
    st.subheader("Automated Mock Interview Allocations")
    st.caption("Auto-filled from each Extended AE's remaining capacity after claimed observations.")

    roles = db.get_user_roles()
    ext = roles[roles["role"] == "extended_ae"]
    sel = db.get_selections(None, week_start, week_end)
    claimed = sel[sel["status"].isin(list(CLAIMED))]
    claimed_counts = claimed.groupby("extended_ae_email").size().to_dict()

    # capacity table
    cap_rows = []
    for _, e in ext.iterrows():
        c = claimed_counts.get(e["email"], 0)
        cap_rows.append({
            "Extended AE": e["name"] or e["email"],
            "Email": e["email"],
            "Claimed": c,
            "Remaining": max(0, WEEKLY_CAPACITY - c),
        })
    cap_df = pd.DataFrame(cap_rows).sort_values("Remaining", ascending=False) if cap_rows else pd.DataFrame()

    # generate 6 mock slots Wed/Thu and round-robin assign by remaining capacity
    base = week_start + timedelta(days=2)
    slots = []
    ref = 4021
    remaining = {r["Email"]: r["Remaining"] for r in cap_rows}
    order = sorted(remaining, key=lambda k: remaining[k], reverse=True)
    idx = 0
    for day in (base, base + timedelta(days=1)):
        for hour in (9, 11, 14):
            assigned = None
            for _ in range(len(order) or 1):
                if not order:
                    break
                cand = order[idx % len(order)]; idx += 1
                if remaining.get(cand, 0) > 0:
                    assigned = cand; remaining[cand] -= 1; break
            name = ext[ext["email"] == assigned]["name"].iloc[0] if assigned is not None and not ext[ext["email"] == assigned].empty else assigned
            slots.append({
                "Slot": datetime.combine(day, datetime.min.time()).replace(hour=hour).strftime("%a %d %b, %I:%M %p"),
                "Candidate": f"#MOCK-{ref}",
                "Assigned Extended AE": name or "— (no capacity)",
            })
            ref += 1

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Mock Interview Slots**")
        st.dataframe(pd.DataFrame(slots), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Extended AE Capacity**")
        st.dataframe(cap_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
def main():
    if "user" not in st.session_state:
        login_view()
    else:
        dashboard()


if __name__ == "__main__":
    main()
