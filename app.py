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

st.set_page_config(page_title="AE Utilization Tracker", layout="wide", page_icon="📊")


# ---------------------------------------------------------------------------
# Theming — two skins:
#   "light"  : Apple-inspired. Airy, lots of whitespace, SF-ish system stack,
#              near-white canvas, soft grey rules, restrained accent blue.
#   "dark"   : Anudip-inspired. Deep navy canvas with the foundation's
#              orange/amber accent, higher-contrast cards.
# ---------------------------------------------------------------------------
THEMES = {
    "light": {
        "bg": "#fbfbfd",           # apple's off-white
        "surface": "#ffffff",
        "text": "#1d1d1f",         # apple near-black
        "muted": "#6e6e73",
        "border": "#d2d2d7",
        "accent": "#0071e3",       # apple blue
        "accent_soft": "#e8f2fd",
        "avail_bg": "#fff8e6",
        "avail_border": "#f0c14b",
        "avail_text": "#7a5b00",
        "claim_bg": "#e9f9ef",
        "claim_border": "#34c759",  # apple green
        "claim_text": "#0f5132",
        "chip_bg": "#f5f5f7",
        "chip_text": "#424245",
    },
    "dark": {
        "bg": "#0e1a2b",           # anudip deep navy
        "surface": "#152740",
        "text": "#f2f5f9",
        "muted": "#9fb0c4",
        "border": "#25405f",
        "accent": "#f7941d",       # anudip orange
        "accent_soft": "#2a2013",
        "avail_bg": "#33280f",
        "avail_border": "#f7941d",
        "avail_text": "#ffd79a",
        "claim_bg": "#10322a",
        "claim_border": "#28c76f",
        "claim_text": "#8ff0c0",
        "chip_bg": "#1d3554",
        "chip_text": "#c8d6e6",
    },
}


def _css(t: dict) -> str:
    return f"""
    <style>
      html, body, [data-testid="stAppViewContainer"], .stApp {{
        background: {t['bg']} !important;
        color: {t['text']} !important;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI",
                     Roboto, Helvetica, Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
      }}
      [data-testid="stSidebar"] {{
        background: {t['surface']} !important;
        border-right: 1px solid {t['border']};
      }}
      .block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1180px; }}

      h1, h2, h3, h4, p, span, label, div {{ color: {t['text']}; }}
      h1 {{ font-weight: 700; letter-spacing: -0.02em; }}
      h3 {{ font-weight: 600; letter-spacing: -0.01em; }}

      /* inputs */
      div[data-baseweb="select"] > div, .stTextInput input {{
        background: {t['surface']} !important;
        border: 1px solid {t['border']} !important;
        border-radius: 10px !important;
        color: {t['text']} !important;
      }}
      .stTextInput input::placeholder {{ color: {t['muted']} !important; }}

      /* buttons */
      .stButton > button {{
        background: {t['accent']}; color: #fff; border: none;
        border-radius: 980px; padding: .48rem 1.15rem;
        font-weight: 600; font-size: .9rem; transition: opacity .15s ease;
      }}
      .stButton > button:hover {{ opacity: .85; color:#fff; }}

      /* metric tiles */
      div[data-testid="stMetric"] {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: 16px; padding: 16px 18px;
      }}
      div[data-testid="stMetricValue"] {{ color: {t['text']}; font-weight: 600; }}
      div[data-testid="stMetricLabel"] {{ color: {t['muted']}; }}

      /* session cards */
      .sess-card {{
        border-radius: 14px; padding: 14px 18px; margin-bottom: 10px;
        border: 1px solid {t['border']}; background: {t['surface']};
        transition: transform .1s ease, box-shadow .1s ease;
      }}
      .sess-card:hover {{ transform: translateY(-1px); box-shadow: 0 6px 20px rgba(0,0,0,.10); }}
      .sess-available {{ background: {t['avail_bg']}; border-color: {t['avail_border']}; }}
      .sess-claimed   {{ background: {t['claim_bg']};  border-color: {t['claim_border']}; }}

      .sess-name {{ font-size: 1rem; font-weight: 650; color: {t['text']}; letter-spacing:-.01em; }}
      .sess-meta {{ font-size: .82rem; color: {t['muted']}; margin-top: 5px; }}
      .chip {{
        display:inline-block; font-size:.71rem; font-weight:600;
        background:{t['chip_bg']}; color:{t['chip_text']};
        padding: 2px 9px; border-radius: 980px; margin-left:6px;
      }}
      .chip-prog {{ background:{t['accent_soft']}; color:{t['accent']}; }}
      .badge {{
        display:inline-block; font-size:.72rem; font-weight:700;
        padding: 2px 10px; border-radius: 980px; margin-left:8px;
      }}
      .badge-available {{ background:{t['avail_border']}; color:{t['avail_text']}; }}
      .badge-selected  {{ background:{t['claim_border']}; color:#04301f; }}
      .badge-confirmed {{ background:{t['claim_border']}; color:#04301f; }}
      .badge-choosing  {{ background:{t['accent']}; color:#fff; }}

      /* login card */
      .login-wrap {{ max-width: 380px; margin: 8vh auto 0; text-align:center; }}
      .login-card {{
        background:{t['surface']}; border:1px solid {t['border']};
        border-radius: 18px; padding: 34px 30px;
        box-shadow: 0 10px 40px rgba(0,0,0,.06);
      }}
      .login-title {{ font-size:1.7rem; font-weight:700; letter-spacing:-.02em; margin-bottom:4px; }}
      .login-sub {{ color:{t['muted']}; font-size:.87rem; margin-bottom:20px; }}
      .dbdot {{ font-size:.78rem; color:{t['muted']}; }}
      hr {{ border-color:{t['border']}; }}
    </style>
    """


def apply_theme():
    if "theme" not in st.session_state:
        st.session_state.theme = "light"
    st.markdown(_css(THEMES[st.session_state.theme]), unsafe_allow_html=True)


STATUS_OPTIONS = ["Not Selected", "Choosing", "Selected", "Confirmed"]
CLAIMED = {"Selected", "Confirmed"}
WEEKLY_CAPACITY = 8


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _theme_toggle(key: str):
    """Small segmented control to switch skins."""
    cur = st.session_state.get("theme", "light")
    choice = st.radio(
        "Appearance",
        ["light", "dark"],
        index=0 if cur == "light" else 1,
        horizontal=True,
        key=key,
        format_func=lambda v: "☀️  Light" if v == "light" else "🌙  Dark",
    )
    if choice != cur:
        st.session_state.theme = choice
        st.rerun()


def login_view():
    apply_theme()
    left, mid, right = st.columns([1, 1.1, 1])
    with mid:
        st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-title">AE Utilization Tracker</div>'
            '<div class="login-sub">Academic Excellence · Anudip Foundation</div>',
            unsafe_allow_html=True,
        )
        with st.form("login", border=False):
            email = st.text_input("Email", placeholder="you@anudip.org").strip().lower()
            pwd = st.text_input("Password", type="password", placeholder="••••••••")
            ok = st.form_submit_button("Sign in", use_container_width=True)
        _theme_toggle("theme_login")
        cmis_ok, app_ok = db.ping()
        st.markdown(
            f'<div class="dbdot">CMIS {"🟢" if cmis_ok else "🔴"} &nbsp;·&nbsp; App DB {"🟢" if app_ok else "🔴"}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    if ok:
        roles = db.get_user_roles()
        match = roles[roles["email"].str.lower() == email]
        if match.empty:
            st.error("Email not found.")
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
    apply_theme()
    user = st.session_state.user
    role = user["role"]

    with st.sidebar:
        st.markdown(f"### {user['name']}")
        st.caption(f"{user['email']} · {role}")
        if st.button("Sign out", use_container_width=True):
            del st.session_state.user
            st.rerun()
        st.divider()
        _theme_toggle("theme_app")
        st.divider()
        cmis_ok, app_ok = db.ping()
        st.markdown(
            f'<div class="dbdot">CMIS {"🟢" if cmis_ok else "🔴"} &nbsp;·&nbsp; App DB {"🟢" if app_ok else "🔴"}</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        "<h1 style='margin-bottom:2px'>Extended AE Utilization Tracker</h1>"
        "<p style='opacity:.6;margin-top:0;font-size:.92rem'>"
        "Faculty observation scheduling · live from CMIS + Anudip AE Team DB</p>",
        unsafe_allow_html=True,
    )
    st.write("")

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

    # --- Filters: trainer + batch, to keep the list readable ---
    sessions = sessions.copy()
    sessions["_trainer"] = (sessions["f_name"].fillna("") + " " + sessions["l_name"].fillna("")).str.strip()

    f1, f2, f3 = st.columns([1.2, 1.2, 1])
    with f1:
        trainers = ["All trainers"] + sorted(sessions["_trainer"].dropna().unique().tolist())
        pick_trainer = st.selectbox("Trainer", trainers)
    with f2:
        batch_pool = sessions if pick_trainer == "All trainers" else sessions[sessions["_trainer"] == pick_trainer]
        batches = ["All batches"] + sorted(batch_pool["batch_code"].dropna().unique().tolist())
        pick_batch = st.selectbox("Batch code", batches)
    with f3:
        day_opts = ["All days"] + sorted(sessions["s_date"].astype(str).unique().tolist())
        pick_day = st.selectbox("Day", day_opts)

    if pick_trainer != "All trainers":
        sessions = sessions[sessions["_trainer"] == pick_trainer]
    if pick_batch != "All batches":
        sessions = sessions[sessions["batch_code"] == pick_batch]
    if pick_day != "All days":
        sessions = sessions[sessions["s_date"].astype(str) == pick_day]

    if sessions.empty:
        st.info("No sessions match these filters.")
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


def _badge(status: str, claimed: bool) -> str:
    if status == "Confirmed":
        return '<span class="badge badge-confirmed">✓ Confirmed</span>'
    if status == "Selected":
        return '<span class="badge badge-selected">✓ Selected</span>'
    if status == "Choosing":
        return '<span class="badge badge-choosing">⏳ Choosing</span>'
    return '<span class="badge badge-available">◷ Available</span>'


def _sessions_table(sessions, core_ae_email, week_start, week_end, role, user_email):
    st.write("")
    st.markdown("### Aligned Sessions")
    st.caption("Yellow = available to observe · Green = claimed. Set a status to claim a session.")

    # Core AE and admin can now claim/select too (not just extended_ae).
    can_select = role in ("extended_ae", "core_ae", "admin")

    # For extended_ae we scope to their own rows; core_ae/admin see all rows for
    # the week so they can act on the team's behalf.
    scope_email = user_email if role == "extended_ae" else None
    my_sel = db.get_selections(scope_email, week_start, week_end)
    sel_lookup = {}
    for _, s in my_sel.iterrows():
        sel_lookup[f"{s['session_date']}|{s['slot_time']}|{s['batch_code'] or ''}"] = s["status"]

    total = len(sessions)
    claimed_count = sum(
        1 for _, r in sessions.iterrows()
        if sel_lookup.get(f"{r['s_date']}|{r['slot_time']}|{r['batch_code'] or ''}", "Not Selected") in CLAIMED
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Total sessions", total)
    m2.metric("Claimed", claimed_count)
    m3.metric("Available", total - claimed_count)
    st.write("")

    for _, r in sessions.iterrows():
        key = f"{r['s_date']}|{r['slot_time']}|{r['batch_code'] or ''}"
        status = sel_lookup.get(key, "Not Selected")
        claimed = status in CLAIMED
        card_cls = "sess-claimed" if claimed else "sess-available"

        try:
            d = pd.to_datetime(r["s_date"]).strftime("%a %d %b")
        except Exception:
            d = str(r["s_date"])

        name = f"{r['f_name']} {r['l_name']}".strip()

        col_info, col_action = st.columns([5, 1.5])
        with col_info:
            st.markdown(
                f"""<div class="sess-card {card_cls}">
                    <div class="sess-name">{name}{_badge(status, claimed)}</div>
                    <div class="sess-meta">
                        {d} · {r['slot_time']}
                        <span class="chip chip-prog">{r['program_name']}</span>
                        <span class="chip">{r['batch_code']}</span>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
        with col_action:
            if can_select:
                new_status = st.selectbox(
                    "status", STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0,
                    key=f"sel_{key}", label_visibility="collapsed",
                )
                if new_status != status:
                    # who the claim belongs to: extended_ae claims for self;
                    # core_ae / admin claim on behalf of their own account.
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
