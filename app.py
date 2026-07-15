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
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

      html, body, [data-testid="stAppViewContainer"], .stApp {{
        background: {t['bg']} !important;
        color: {t['text']} !important;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
                     "Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
      }}
      [data-testid="stHeader"] {{ background: transparent !important; }}
      [data-testid="stSidebar"] {{
        background: {t['surface']} !important;
        border-right: 1px solid {t['border']};
      }}
      [data-testid="stSidebar"] * {{ color: {t['text']}; }}
      .block-container {{ padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1120px; }}

      h1 {{ font-weight: 700; letter-spacing: -0.025em; font-size: 2.4rem; color:{t['text']}; }}
      h2, h3 {{ font-weight: 600; letter-spacing: -0.015em; color:{t['text']}; }}
      p, span, label, div {{ color: {t['text']}; }}
      .stCaption, [data-testid="stCaptionContainer"] {{ color:{t['muted']} !important; }}

      /* ---------- INPUTS: closed state ---------- */
      div[data-baseweb="select"] > div {{
        background: {t['surface']} !important;
        border: 1px solid {t['border']} !important;
        border-radius: 12px !important;
        color: {t['text']} !important;
        min-height: 44px;
        box-shadow: none !important;
        transition: border-color .15s ease, box-shadow .15s ease;
      }}
      div[data-baseweb="select"] > div:hover {{ border-color: {t['muted']} !important; }}
      div[data-baseweb="select"] > div:focus-within {{
        border-color: {t['accent']} !important;
        box-shadow: 0 0 0 3px {t['accent']}33 !important;
      }}
      div[data-baseweb="select"] div, div[data-baseweb="select"] span,
      div[data-baseweb="select"] input {{ color: {t['text']} !important; }}
      div[data-baseweb="select"] svg {{ fill: {t['muted']} !important; }}

      .stTextInput input {{
        background: {t['surface']} !important;
        border: 1px solid {t['border']} !important;
        border-radius: 12px !important;
        color: {t['text']} !important;
        min-height: 44px; padding: 0 14px;
      }}
      .stTextInput input:focus {{
        border-color: {t['accent']} !important;
        box-shadow: 0 0 0 3px {t['accent']}33 !important;
      }}
      .stTextInput input::placeholder {{ color: {t['muted']} !important; opacity:1; }}

      /* ---------- DROPDOWN POPOVER (renders in a detached portal) ---------- */
      div[data-baseweb="popover"], div[data-baseweb="popover"] > div,
      ul[data-baseweb="menu"], div[data-baseweb="menu"] {{
        background: {t['surface']} !important;
        border-radius: 12px !important;
        border: 1px solid {t['border']} !important;
        box-shadow: 0 12px 34px rgba(0,0,0,.16) !important;
      }}
      ul[data-baseweb="menu"] li, div[data-baseweb="menu"] li,
      li[role="option"], div[role="option"] {{
        background: {t['surface']} !important;
        color: {t['text']} !important;
        font-size: .92rem;
        padding: 9px 14px !important;
      }}
      li[role="option"] *, div[role="option"] * {{ color: {t['text']} !important; }}
      li[role="option"]:hover, div[role="option"]:hover,
      li[aria-selected="true"], div[aria-selected="true"] {{
        background: {t['accent_soft']} !important;
        color: {t['accent']} !important;
      }}
      li[aria-selected="true"] *, li[role="option"]:hover * {{ color: {t['accent']} !important; }}

      /* ---------- BUTTONS ---------- */
      .stButton > button, .stFormSubmitButton > button {{
        background: {t['accent']}; color: #ffffff !important; border: none;
        border-radius: 980px; padding: .55rem 1.3rem;
        font-weight: 600; font-size: .92rem; letter-spacing:-.01em;
        transition: opacity .15s ease, transform .06s ease;
      }}
      .stButton > button:hover, .stFormSubmitButton > button:hover {{ opacity:.86; }}
      .stButton > button:active {{ transform: scale(.985); }}
      .stButton > button *, .stFormSubmitButton > button * {{ color:#fff !important; }}

      /* ---------- RADIO (theme toggle) ---------- */
      div[role="radiogroup"] label {{ color:{t['text']} !important; font-size:.88rem; }}

      /* ---------- METRIC TILES ---------- */
      div[data-testid="stMetric"] {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: 16px; padding: 18px 20px;
      }}
      div[data-testid="stMetricValue"] {{
        color:{t['text']} !important; font-weight:600; letter-spacing:-.02em;
      }}
      div[data-testid="stMetricLabel"] * {{ color:{t['muted']} !important; font-size:.82rem; }}

      /* ---------- SESSION CARDS ---------- */
      .sess-card {{
        border-radius: 14px; padding: 15px 18px; margin-bottom: 10px;
        border: 1px solid {t['border']}; background: {t['surface']};
        transition: transform .12s ease, box-shadow .12s ease;
      }}
      .sess-card:hover {{ transform: translateY(-1px); box-shadow: 0 8px 24px rgba(0,0,0,.10); }}
      .sess-available {{ background:{t['avail_bg']}; border-color:{t['avail_border']}; }}
      .sess-claimed   {{ background:{t['claim_bg']};  border-color:{t['claim_border']}; }}
      .sess-name {{ font-size:1rem; font-weight:600; color:{t['text']}; letter-spacing:-.012em; }}
      .sess-meta {{ font-size:.82rem; color:{t['muted']}; margin-top:6px; }}
      .chip {{
        display:inline-block; font-size:.71rem; font-weight:500;
        background:{t['chip_bg']}; color:{t['chip_text']};
        padding: 3px 10px; border-radius:980px; margin-left:6px;
      }}
      .chip-prog {{ background:{t['accent_soft']}; color:{t['accent']}; font-weight:600; }}
      .badge {{
        display:inline-block; font-size:.71rem; font-weight:600;
        padding: 2px 10px; border-radius:980px; margin-left:8px;
      }}
      .badge-available {{ background:{t['avail_border']}; color:{t['avail_text']}; }}
      .badge-selected, .badge-confirmed {{ background:{t['claim_border']}; color:#04301f; }}
      .badge-choosing  {{ background:{t['accent']}; color:#fff; }}

      /* ---------- LOGIN ---------- */
      .login-title {{
        font-size:2rem; font-weight:700; letter-spacing:-.03em;
        margin-bottom:6px; color:{t['text']};
      }}
      .login-sub {{ color:{t['muted']}; font-size:.9rem; margin-bottom:26px; }}
      .dbdot {{ font-size:.76rem; color:{t['muted']}; margin-top:16px; }}

      /* ---------- MISC ---------- */
      hr, [data-testid="stDivider"] {{ border-color:{t['border']} !important; }}
      .stDataFrame {{ border:1px solid {t['border']}; border-radius:12px; overflow:hidden; }}
      [data-testid="stAlert"] {{ border-radius:12px; }}
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

    tabs = ["📋  Sessions", "✅  My Evaluations", "🎯  Mock Interviews"]
    if role in ("core_ae", "admin"):
        tabs.insert(2, "👥  My Extended AE Team")
    made = st.tabs(tabs)

    with made[0]:
        _sessions_tab(user, role)
    with made[1]:
        _evaluations_tab(user, role)
    if role in ("core_ae", "admin"):
        with made[2]:
            _rollup_tab(user, role)
        with made[3]:
            _mock_tab()
    else:
        with made[2]:
            _mock_tab()


def _week_bounds_now():
    ws, we = current_week_bounds(0)
    return ws, we


def _rollup_tab(user, role):
    core_options = _core_options_for(role, user["email"])
    if not core_options:
        st.info("No Core AE mapping found.")
        return
    core_ae_email = st.selectbox("Core AE", core_options, key="rollup_core")
    ws, we = _week_bounds_now()
    st.caption(f"Week of {ws} → {we}")
    _team_rollup(core_ae_email, ws, we)


def _mock_tab():
    ws, we = _week_bounds_now()
    st.caption(f"Week of {ws} → {we}")
    _mock_interview_section(ws, we)


def _sessions_tab(user, role):
    core_options = _core_options_for(role, user["email"])
    if not core_options:
        st.warning("No Core AE mapping found for your account in core_ae_faculty_map.")
        return

    core_ae_email = st.selectbox("Core AE Member", core_options)

    faculty = db.faculty_emails_for_core(core_ae_email)
    if not faculty:
        st.info(f"No faculty mapped to {core_ae_email} in core_ae_faculty_map.")
        return

    # --- Fetch the FULL CMIS horizon for these faculty (not just one week) ---
    with st.spinner("Fetching sessions from CMIS…"):
        sessions = db.fetch_sessions_all_for_faculty(tuple(faculty))

    if sessions.empty:
        st.info("No CMIS sessions found for this Core AE's faculty.")
        return

    sessions = sessions.copy()
    sessions["_trainer"] = (sessions["f_name"].fillna("") + " " + sessions["l_name"].fillna("")).str.strip()
    sessions["_date"] = pd.to_datetime(sessions["s_date"]).dt.date

    lo, hi = sessions["_date"].min(), sessions["_date"].max()
    st.caption(f"CMIS holds **{len(sessions):,}** sessions for these faculty · {lo} → {hi}")

    # --- Filters ---
    f1, f2 = st.columns(2)
    with f1:
        trainers = ["All trainers"] + sorted(sessions["_trainer"].dropna().unique().tolist())
        pick_trainer = st.selectbox("Trainer", trainers)
    with f2:
        pool = sessions if pick_trainer == "All trainers" else sessions[sessions["_trainer"] == pick_trainer]
        batches = ["All batches"] + sorted(pool["batch_code"].dropna().unique().tolist())
        pick_batch = st.selectbox("Batch code", batches)

    d1, d2, d3 = st.columns([1, 1, 1])
    with d1:
        date_from = st.date_input("From", value=max(lo, date.today()), min_value=lo, max_value=hi)
    with d2:
        date_to = st.date_input("To", value=min(hi, date.today() + timedelta(days=30)),
                                min_value=lo, max_value=hi)
    with d3:
        only_open = st.selectbox("Show", ["All sessions", "Not yet evaluated", "Evaluated only"])

    if pick_trainer != "All trainers":
        sessions = sessions[sessions["_trainer"] == pick_trainer]
    if pick_batch != "All batches":
        sessions = sessions[sessions["batch_code"] == pick_batch]
    sessions = sessions[(sessions["_date"] >= date_from) & (sessions["_date"] <= date_to)]

    done_ids = db.evaluated_session_ids(user["email"])
    sessions["_sid"] = sessions.apply(
        lambda r: db.make_session_id(r["email_id"], r["_date"], r["slot_time"], r["batch_code"]), axis=1
    )
    sessions["_done"] = sessions["_sid"].isin(done_ids)

    if only_open == "Not yet evaluated":
        sessions = sessions[~sessions["_done"]]
    elif only_open == "Evaluated only":
        sessions = sessions[sessions["_done"]]

    if sessions.empty:
        st.info("No sessions match these filters.")
        return

    # cap the render for sanity; filters narrow it down
    MAX_SHOW = 150
    shown = sessions.head(MAX_SHOW)
    if len(sessions) > MAX_SHOW:
        st.caption(f"Showing first {MAX_SHOW} of {len(sessions):,} — narrow the filters to see more.")

    _sessions_table(shown, core_ae_email, date_from, date_to, role, user["email"])


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


def _sessions_table(sessions, core_ae_email, date_from, date_to, role, user_email):
    st.write("")
    st.markdown("### Sessions")
    st.caption("Yellow = available to observe · Green = claimed · Blue tick = evaluated.")

    can_select = role in ("extended_ae", "core_ae", "admin")

    scope_email = user_email if role == "extended_ae" else None
    my_sel = db.get_selections(scope_email, date_from, date_to)
    sel_lookup = {}
    for _, s in my_sel.iterrows():
        sel_lookup[f"{s['session_date']}|{s['slot_time']}|{s['batch_code'] or ''}"] = s["status"]

    total = len(sessions)
    claimed_count = sum(
        1 for _, r in sessions.iterrows()
        if sel_lookup.get(f"{r['_date']}|{r['slot_time']}|{r['batch_code'] or ''}", "Not Selected") in CLAIMED
    )
    done_count = int(sessions["_done"].sum()) if "_done" in sessions else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sessions", total)
    m2.metric("Claimed", claimed_count)
    m3.metric("Available", total - claimed_count)
    m4.metric("Evaluated", done_count)
    st.write("")

    for _, r in sessions.iterrows():
        key = f"{r['_date']}|{r['slot_time']}|{r['batch_code'] or ''}"
        sid = r["_sid"]
        status = sel_lookup.get(key, "Not Selected")
        claimed = status in CLAIMED
        done = bool(r["_done"])
        card_cls = "sess-claimed" if (claimed or done) else "sess-available"

        d = pd.to_datetime(r["_date"]).strftime("%a %d %b %Y")
        name = f"{r['f_name']} {r['l_name']}".strip()
        done_badge = '<span class="badge badge-selected">✓ Evaluated</span>' if done else ""

        col_info, col_action = st.columns([5, 1.5])
        with col_info:
            st.markdown(
                f"""<div class="sess-card {card_cls}">
                    <div class="sess-name">{name}{_badge(status, claimed)}{done_badge}</div>
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
                    key=f"sel_{sid}", label_visibility="collapsed",
                )
                if new_status != status:
                    db.upsert_selection(
                        user_email, r["_date"], r["slot_time"], r["m_code"],
                        r["batch_code"], new_status,
                    )
                    db.set_highlight_flag(
                        r["_date"], r["slot_time"], r["batch_code"],
                        core_ae_email, user_email, new_status in CLAIMED,
                    )
                    st.cache_data.clear()
                    st.rerun()

        # --- post-observation evaluation form ---
        if can_select:
            label = "✅ Evaluation submitted — edit" if done else "📝 Evaluate this session"
            with st.expander(label, expanded=False):
                _evaluation_form(r, sid, name, role, user_email, done)


def _evaluation_form(r, sid, trainer_name, role, user_email, done):
    """The post-session form. Writes to session_evaluation."""
    prev = {}
    if done:
        allrows = db.get_evaluations(user_email)
        match = allrows[allrows["session_id"] == sid]
        if not match.empty:
            prev = match.iloc[0].to_dict()

    with st.form(f"eval_{sid}", border=False):
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Session ID", value=sid, disabled=True, key=f"sid_{sid}")
            st.text_input("Trainer", value=trainer_name, disabled=True, key=f"tn_{sid}")
            st.text_input("Date", value=str(r["_date"]), disabled=True, key=f"dt_{sid}")
        with c2:
            duration = st.number_input(
                "Duration observed (minutes)", min_value=0, max_value=600, step=5,
                value=int(prev.get("duration_minutes") or 30), key=f"dur_{sid}",
            )
            rating = st.select_slider(
                "Rating", options=[1, 2, 3, 4, 5],
                value=int(prev.get("rating") or 3), key=f"rt_{sid}",
            )
            st.text_input("Batch / Module", value=f"{r['batch_code']} · {r['m_code']}",
                          disabled=True, key=f"bm_{sid}")

        remarks = st.text_area(
            "Remarks / observations", value=prev.get("remarks") or "",
            placeholder="What went well, what to improve, follow-ups…",
            key=f"rm_{sid}", height=90,
        )
        submitted = st.form_submit_button("Submit evaluation" if not done else "Update evaluation")

    if submitted:
        try:
            db.save_evaluation(
                evaluator_email=user_email,
                evaluator_role=role,
                session_id=sid,
                trainer_name=trainer_name,
                trainer_email=r["email_id"],
                session_date=r["_date"],
                slot_time=r["slot_time"],
                batch_code=r["batch_code"],
                module=r["m_code"],
                program_name=r["program_name"],
                duration_minutes=int(duration),
                rating=int(rating),
                remarks=remarks.strip() or None,
            )
            st.cache_data.clear()
            st.success("Evaluation saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not save — has the session_evaluation table been created? ({e})")


def _evaluations_tab(user, role):
    st.markdown("### My Evaluations")
    st.caption("Everything you've submitted, stored in the `session_evaluation` table.")

    scope = None if role == "admin" else user["email"]
    df = db.get_evaluations(scope)

    if df.empty:
        st.info("No evaluations submitted yet. Fill one in from the Sessions tab.")
        return

    m1, m2, m3 = st.columns(3)
    m1.metric("Total evaluations", len(df))
    m2.metric("Avg rating", round(df["rating"].dropna().mean(), 2) if df["rating"].notna().any() else "—")
    m3.metric("Minutes observed", int(df["duration_minutes"].fillna(0).sum()))
    st.write("")

    view = df[["session_date", "trainer_name", "batch_code", "module",
               "duration_minutes", "rating", "remarks", "evaluator_email", "created_on"]]
    view = view.rename(columns={
        "session_date": "Date", "trainer_name": "Trainer", "batch_code": "Batch",
        "module": "Module", "duration_minutes": "Mins", "rating": "Rating",
        "remarks": "Remarks", "evaluator_email": "Evaluator", "created_on": "Submitted",
    })
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇  Download as CSV", view.to_csv(index=False).encode(),
        file_name="ae_evaluations.csv", mime="text/csv",
    )


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
