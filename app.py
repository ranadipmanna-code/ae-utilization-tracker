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
        "bg": "#f5f5f7", "surface": "#ffffff", "surface_2": "#fafafa",
        "text": "#1d1d1f", "muted": "#6e6e73", "border": "#e5e5ea",
        "accent": "#0071e3", "accent_soft": "#eaf3fe",
        "avail_bg": "#fffdf5", "avail_border": "#f5c518", "avail_text": "#8a6100",
        "claim_bg": "#f2fbf5", "claim_border": "#30c85f", "claim_text": "#0b5f28",
        "done_bg": "#f3f7ff", "done_border": "#0071e3",
        "chip_bg": "#f5f5f7", "chip_text": "#4a4a4f",
        "shadow": "0 1px 2px rgba(0,0,0,.04), 0 8px 24px rgba(0,0,0,.06)",
    },
    "dark": {
        "bg": "#0b1626", "surface": "#14243a", "surface_2": "#1a2c46",
        "text": "#eef3f9", "muted": "#8ba0b8", "border": "#243c59",
        "accent": "#f7941d", "accent_soft": "#2e2312",
        "avail_bg": "#2b2210", "avail_border": "#f7941d", "avail_text": "#ffd79a",
        "claim_bg": "#0d2b23", "claim_border": "#2ec27e", "claim_text": "#7fe6b6",
        "done_bg": "#132a3f", "done_border": "#4da3ff",
        "chip_bg": "#1e3252", "chip_text": "#bccbdd",
        "shadow": "0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35)",
    },
}


def _css(t: dict) -> str:
    return f"""
    <style>
      html, body, [data-testid="stAppViewContainer"], .stApp {{
        background:{t['bg']} !important; color:{t['text']} !important;
        font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,sans-serif;
        -webkit-font-smoothing:antialiased;
      }}
      [data-testid="stHeader"] {{ background:transparent !important; }}
      .block-container {{ padding-top:1.6rem; padding-bottom:4rem; max-width:1180px; }}
      h1 {{ font-weight:700; letter-spacing:-.028em; font-size:2rem; margin-bottom:0; }}
      h2,h3 {{ font-weight:600; letter-spacing:-.015em; }}
      p,span,label,div,li {{ color:{t['text']}; }}
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{
        color:{t['muted']} !important;
      }}

      /* ---------- SIDEBAR ---------- */
      [data-testid="stSidebar"] {{
        background:{t['surface']} !important; border-right:1px solid {t['border']};
      }}
      [data-testid="stSidebar"] * {{ color:{t['text']}; }}
      /* quiet, secondary sign-out */
      [data-testid="stSidebar"] .stButton > button {{
        background:transparent !important; color:{t['muted']} !important;
        border:1px solid {t['border']} !important; font-weight:500; font-size:.85rem;
        padding:.4rem 1rem;
      }}
      [data-testid="stSidebar"] .stButton > button:hover {{
        background:{t['surface_2']} !important; color:{t['text']} !important;
        border-color:{t['muted']} !important;
      }}
      [data-testid="stSidebar"] .stButton > button * {{ color:inherit !important; }}

      /* ---------- ALL INPUT SHELLS ---------- */
      div[data-baseweb="select"] > div,
      .stTextInput input, .stTextArea textarea,
      .stDateInput input, div[data-testid="stDateInput"] > div > div,
      .stNumberInput input, div[data-testid="stNumberInput"] > div > div {{
        background:{t['surface']} !important;
        border:1px solid {t['border']} !important;
        border-radius:10px !important; color:{t['text']} !important;
        min-height:42px; box-shadow:none !important;
      }}
      .stDateInput *, div[data-testid="stDateInput"] * {{ color:{t['text']} !important; }}
      .stDateInput svg, .stNumberInput svg {{ fill:{t['muted']} !important; }}
      div[data-baseweb="select"] > div:focus-within,
      .stTextInput input:focus, .stTextArea textarea:focus {{
        border-color:{t['accent']} !important; box-shadow:0 0 0 3px {t['accent']}2b !important;
      }}
      div[data-baseweb="select"] div, div[data-baseweb="select"] span,
      div[data-baseweb="select"] input {{ color:{t['text']} !important; }}
      div[data-baseweb="select"] svg {{ fill:{t['muted']} !important; }}
      input::placeholder, textarea::placeholder {{ color:{t['muted']} !important; opacity:1; }}

      /* ---------- DISABLED / AUTOFILLED FIELDS ----------
         Streamlit fades disabled inputs to ~40% opacity, which made the
         auto-filled session details look empty. Show them clearly as
         read-only facts instead of ghost text. */
      .stTextInput input:disabled, .stTextArea textarea:disabled,
      input:disabled, textarea:disabled,
      div[data-testid="stTextInput"] input[disabled],
      [data-baseweb="input"] input:disabled {{
        -webkit-text-fill-color:{t['text']} !important;
        color:{t['text']} !important;
        opacity:1 !important;
        background:{t['surface_2']} !important;
        border:1px solid {t['border']} !important;
        font-weight:500;
        cursor:default;
      }}
      div[data-testid="stTextInput"]:has(input:disabled) label,
      div[data-testid="stTextInput"] input[disabled] + div {{
        opacity:1 !important;
      }}
      /* the wrapper baseweb dims too */
      div[data-baseweb="input"]:has(input:disabled),
      div[data-baseweb="base-input"]:has(input:disabled) {{
        opacity:1 !important; background:{t['surface_2']} !important;
      }}

      /* ---------- POPOVERS / MENUS / CALENDAR ---------- */
      div[data-baseweb="popover"], div[data-baseweb="popover"] > div,
      ul[data-baseweb="menu"], div[data-baseweb="menu"],
      div[data-baseweb="calendar"], div[data-baseweb="datepicker"] {{
        background:{t['surface']} !important; border:1px solid {t['border']} !important;
        border-radius:12px !important; box-shadow:{t['shadow']} !important;
      }}
      /* the scrollable list container itself (this was rendering black) */
      div[data-baseweb="popover"] ul, div[data-baseweb="popover"] div[role="listbox"],
      ul[role="listbox"], div[role="listbox"] {{
        background:{t['surface']} !important;
      }}
      li[role="option"], div[role="option"], div[data-baseweb="calendar"] * {{
        background:{t['surface']} !important; color:{t['text']} !important; font-size:.9rem;
      }}
      li[role="option"] div, li[role="option"] span {{
        background:transparent !important; color:{t['text']} !important;
      }}
      li[role="option"] {{ padding:9px 14px !important; }}
      li[role="option"]:hover, li[aria-selected="true"],
      div[aria-selected="true"] {{
        background:{t['accent_soft']} !important; color:{t['accent']} !important;
      }}
      li[aria-selected="true"] *, li[role="option"]:hover * {{ color:{t['accent']} !important; }}

      /* ---------- CALENDAR internals (kill the black empty cells) ---------- */
      div[data-baseweb="calendar"], div[data-baseweb="calendar"] > div,
      div[data-baseweb="calendar"] div[role="grid"],
      div[data-baseweb="calendar"] div[role="row"],
      div[data-baseweb="calendar"] div[role="gridcell"],
      div[data-baseweb="calendar"] [class*="Month"],
      div[data-baseweb="calendar"] [class*="Week"],
      div[data-baseweb="calendar"] [class*="Day"],
      div[data-baseweb="datepicker"] * {{
        background-color:{t['surface']} !important;
        color:{t['text']} !important;
        border-color:{t['border']} !important;
      }}
      /* selected / hovered day */
      div[data-baseweb="calendar"] div[aria-selected="true"],
      div[data-baseweb="calendar"] [class*="Day"][aria-selected="true"] {{
        background-color:{t['accent']} !important; color:#fff !important;
        border-radius:50% !important;
      }}
      div[data-baseweb="calendar"] [class*="Day"]:hover {{
        background-color:{t['accent_soft']} !important; color:{t['accent']} !important;
        border-radius:50% !important;
      }}
      div[data-baseweb="calendar"] [aria-disabled="true"],
      div[data-baseweb="calendar"] [class*="Day"][aria-disabled="true"] {{
        color:{t['muted']} !important; opacity:.35;
      }}

      /* ---------- NUMBER INPUT stepper (-/+ were rendering dark) ---------- */
      div[data-testid="stNumberInput"] button,
      [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {{
        background:{t['surface_2']} !important; color:{t['text']} !important;
        border:1px solid {t['border']} !important;
      }}
      div[data-testid="stNumberInput"] button:hover {{
        background:{t['accent_soft']} !important; color:{t['accent']} !important;
      }}
      div[data-testid="stNumberInput"] button svg {{ fill:{t['text']} !important; }}

      /* ---------- TABS ---------- */
      .stTabs [data-baseweb="tab-list"] {{
        gap:4px; background:{t['surface_2']}; padding:5px; border-radius:12px;
        border:1px solid {t['border']};
      }}
      .stTabs [data-baseweb="tab"] {{
        height:38px; border-radius:8px; padding:0 16px;
        color:{t['muted']} !important; font-weight:500; font-size:.9rem;
      }}
      .stTabs [aria-selected="true"] {{
        background:{t['surface']} !important; color:{t['text']} !important;
        font-weight:600; box-shadow:0 1px 3px rgba(0,0,0,.08);
      }}
      .stTabs [aria-selected="true"] * {{ color:{t['text']} !important; }}
      .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display:none; }}

      /* ---------- BUTTONS ---------- */
      .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
        background:{t['accent']}; color:#fff !important; border:none; border-radius:10px;
        padding:.5rem 1.15rem; font-weight:600; font-size:.9rem;
        transition:opacity .15s ease, transform .06s ease;
      }}
      .stButton > button:hover, .stFormSubmitButton > button:hover {{ opacity:.87; }}
      .stButton > button:active {{ transform:scale(.98); }}
      .stFormSubmitButton > button *, .stDownloadButton > button * {{ color:#fff !important; }}

      /* ---------- EXPANDER (evaluation form) ---------- */
      [data-testid="stExpander"] {{
        border:1px solid {t['border']} !important; border-radius:10px !important;
        background:{t['surface']} !important; margin-bottom:14px;
      }}
      [data-testid="stExpander"] summary {{ color:{t['text']} !important; font-size:.86rem; }}
      [data-testid="stExpander"] summary:hover {{ color:{t['accent']} !important; }}
      [data-testid="stExpander"] * {{ color:{t['text']}; }}

      /* ---------- METRICS ---------- */
      div[data-testid="stMetric"] {{
        background:{t['surface']}; border:1px solid {t['border']};
        border-radius:12px; padding:14px 16px;
      }}
      div[data-testid="stMetricValue"] {{ font-weight:600; letter-spacing:-.02em; font-size:1.5rem; }}
      div[data-testid="stMetricValue"] * {{ color:{t['text']} !important; }}
      div[data-testid="stMetricLabel"] * {{ color:{t['muted']} !important; font-size:.78rem; }}

      /* ---------- SESSION ROW ---------- */
      .sess-card {{
        border-radius:10px; padding:11px 14px; margin-bottom:7px;
        border:1px solid {t['border']}; background:{t['surface']};
        border-left:3px solid {t['border']};
        transition:background .12s ease;
      }}
      .sess-card:hover {{ background:{t['surface_2']}; }}
      .sess-available {{ background:{t['avail_bg']}; border-left-color:{t['avail_border']}; }}
      .sess-claimed {{ background:{t['claim_bg']}; border-left-color:{t['claim_border']}; }}
      .sess-done {{ background:{t['done_bg']}; border-left-color:{t['done_border']}; }}
      .sess-name {{ font-size:.94rem; font-weight:600; letter-spacing:-.01em; }}
      .sess-meta {{ font-size:.78rem; color:{t['muted']}; margin-top:3px; }}
      .chip {{
        display:inline-block; font-size:.68rem; font-weight:500;
        background:{t['chip_bg']}; color:{t['chip_text']};
        padding:2px 8px; border-radius:6px; margin-left:5px;
      }}
      .chip-prog {{ background:{t['accent_soft']}; color:{t['accent']}; font-weight:600; }}
      .badge {{
        display:inline-block; font-size:.67rem; font-weight:600;
        padding:1px 8px; border-radius:6px; margin-left:7px;
      }}
      .badge-available {{ background:{t['avail_border']}; color:{t['avail_text']}; }}
      .badge-selected, .badge-confirmed {{ background:{t['claim_border']}; color:#04301f; }}
      .badge-choosing {{ background:{t['accent']}; color:#fff; }}
      .badge-done {{ background:{t['done_border']}; color:#fff; }}

      /* ---------- EVALUATION: auto-filled facts panel ---------- */
      .eval-facts {{
        background:{t['surface_2']}; border:1px solid {t['border']};
        border-radius:10px; padding:14px 16px; margin-bottom:16px;
      }}
      .eval-facts-title {{
        font-size:.74rem; font-weight:700; text-transform:uppercase;
        letter-spacing:.05em; color:{t['muted']}; margin-bottom:10px;
      }}
      .eval-grid {{
        display:grid; grid-template-columns:repeat(3, 1fr); gap:10px 18px;
      }}
      .eval-grid > div {{ display:flex; flex-direction:column; }}
      .ef-k {{
        font-size:.7rem; font-weight:600; text-transform:uppercase;
        letter-spacing:.04em; color:{t['muted']}; margin-bottom:2px;
      }}
      .ef-v {{ font-size:.9rem; font-weight:600; color:{t['text']}; }}
      .ef-sid {{
        margin-top:12px; padding-top:10px; border-top:1px solid {t['border']};
        font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
        font-size:.72rem; color:{t['muted']}; word-break:break-all;
      }}
      .ef-sid .ef-k {{ display:block; margin-bottom:3px; }}

      /* day group heading */
      .day-head {{
        font-size:.76rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase;
        color:{t['muted']}; margin:18px 0 8px; padding-bottom:5px;
        border-bottom:1px solid {t['border']};
      }}

      /* ---------- LOGIN ---------- */
      .login-title {{ font-size:1.9rem; font-weight:700; letter-spacing:-.03em; margin-bottom:6px; }}
      .login-sub {{ color:{t['muted']}; font-size:.88rem; margin-bottom:24px; }}
      .dbdot {{ font-size:.75rem; color:{t['muted']}; margin-top:14px; }}

      hr, [data-testid="stDivider"] {{ border-color:{t['border']} !important; }}
      .stDataFrame {{ border:1px solid {t['border']}; border-radius:10px; overflow:hidden; }}
      [data-testid="stAlert"] {{ border-radius:10px; }}
      div[role="radiogroup"] label {{ font-size:.85rem; }}
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
        tabs.insert(3, "📊  Weekly Summary")
    made = st.tabs(tabs)

    with made[0]:
        _sessions_tab(user, role)
    with made[1]:
        _evaluations_tab(user, role)
    if role in ("core_ae", "admin"):
        with made[2]:
            _rollup_tab(user, role)
        with made[3]:
            _summary_tab(user, role)
        with made[4]:
            _mock_tab()
    else:
        with made[2]:
            _mock_tab()


def _summary_tab(user, role):
    st.markdown("### Weekly Summary")
    st.caption("Auto-maintained in `weekly_ae_summary` — updates whenever a session is claimed or evaluated.")

    scope = None if role == "admin" else user["email"]
    df = db.get_weekly_summary(scope)

    core_options = _core_options_for(role, user["email"])
    c1, c2 = st.columns([2, 1])
    with c1:
        pick = st.selectbox("Core AE", core_options, key="sum_core")
    with c2:
        st.write("")
        if st.button("↻  Rebuild this week", use_container_width=True):
            try:
                db.recompute_weekly_summary(pick, date.today())
                st.cache_data.clear()
                st.success("Summary rebuilt.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not rebuild: {e}")

    if df.empty:
        st.info(
            "No summary rows yet. They appear automatically once someone claims "
            "or evaluates a session — or hit **Rebuild this week** above."
        )
        return

    view = df.rename(columns={
        "core_ae_email": "Core AE", "week_start_date": "Week of",
        "total_sessions": "Available", "sessions_selected": "Selected",
        "sessions_observed": "Observed", "updated_on": "Updated",
    })
    st.dataframe(view, use_container_width=True, hide_index=True)


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

    c1, _ = st.columns([2, 3])
    with c1:
        core_ae_email = st.selectbox("Core AE Member", core_options)

    faculty = db.faculty_emails_for_core(core_ae_email)
    if not faculty:
        st.info(f"No faculty mapped to {core_ae_email} in core_ae_faculty_map.")
        return

    with st.spinner("Fetching sessions from CMIS…"):
        sessions = db.fetch_sessions_all_for_faculty(tuple(faculty))

    if sessions.empty:
        st.info("No CMIS sessions found for this Core AE's faculty.")
        return

    sessions = sessions.copy()
    sessions["_trainer"] = (sessions["f_name"].fillna("") + " " + sessions["l_name"].fillna("")).str.strip()
    sessions["_date"] = pd.to_datetime(sessions["s_date"]).dt.date
    lo_d, hi_d = sessions["_date"].min(), sessions["_date"].max()

    with st.expander(f"🔎  Filters · {len(sessions):,} sessions in CMIS ({lo_d} → {hi_d})", expanded=True):
        f1, f2 = st.columns(2)
        with f1:
            trainers = ["All trainers"] + sorted(sessions["_trainer"].dropna().unique().tolist())
            pick_trainer = st.selectbox("Trainer", trainers)
        with f2:
            pool = sessions if pick_trainer == "All trainers" else sessions[sessions["_trainer"] == pick_trainer]
            batches = ["All batches"] + sorted(pool["batch_code"].dropna().unique().tolist())
            pick_batch = st.selectbox("Batch code", batches)

        d1, d2, d3 = st.columns(3)
        default_from = max(lo_d, date.today())
        with d1:
            date_from = st.date_input("From", value=default_from, min_value=lo_d, max_value=hi_d)
        with d2:
            date_to = st.date_input(
                "To", value=min(hi_d, default_from + timedelta(days=13)),
                min_value=lo_d, max_value=hi_d,
            )
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
        st.info("No sessions match these filters. Try widening the date range.")
        return

    # NOTE: no row cap here — pagination in _sessions_table handles volume,
    # so the metrics and page count reflect the TRUE filtered total.
    _sessions_table(sessions, core_ae_email, date_from, date_to, role, user["email"])


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
    m1.metric("Sessions", f"{total:,}")
    m2.metric("Claimed", claimed_count)
    m3.metric("Available", total - claimed_count)
    m4.metric("Evaluated", done_count)

    # ---- pagination: keeps the page short and scannable ----
    PER_PAGE = 25
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    if pages > 1:
        pcol, icol = st.columns([1, 3])
        with pcol:
            page = st.number_input(
                "Page", min_value=1, max_value=pages, value=1, step=1, key="page_no"
            )
        with icol:
            st.markdown(
                f"<div style='padding-top:30px;font-size:.82rem;opacity:.6'>"
                f"Page {int(page)} of {pages} · {total:,} sessions</div>",
                unsafe_allow_html=True,
            )
    else:
        page = 1

    lo = (int(page) - 1) * PER_PAGE
    chunk = sessions.iloc[lo:lo + PER_PAGE]

    # ---- group by day so the list has structure ----
    for day, grp in chunk.groupby("_date", sort=True):
        st.markdown(
            f"<div class='day-head'>{pd.to_datetime(day).strftime('%A · %d %B %Y')} "
            f"&nbsp;·&nbsp; {len(grp)} session{'s' if len(grp) != 1 else ''}</div>",
            unsafe_allow_html=True,
        )
        for _, r in grp.iterrows():
            _session_row(r, sel_lookup, can_select, core_ae_email, role, user_email)


def _session_row(r, sel_lookup, can_select, core_ae_email, role, user_email):
    key = f"{r['_date']}|{r['slot_time']}|{r['batch_code'] or ''}"
    sid = r["_sid"]
    status = sel_lookup.get(key, "Not Selected")
    claimed = status in CLAIMED
    done = bool(r["_done"])

    if done:
        cls = "sess-done"
    elif claimed:
        cls = "sess-claimed"
    else:
        cls = "sess-available"

    name = f"{r['f_name']} {r['l_name']}".strip()
    done_badge = '<span class="badge badge-done">✓ Evaluated</span>' if done else ""

    c_info, c_act = st.columns([5, 1.4])
    with c_info:
        st.markdown(
            f"""<div class="sess-card {cls}">
                <div class="sess-name">{name}{_badge(status, claimed)}{done_badge}</div>
                <div class="sess-meta">{r['slot_time']}
                    <span class="chip chip-prog">{r['program_name']}</span>
                    <span class="chip">{r['batch_code']}</span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c_act:
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
                # keep weekly_ae_summary current
                try:
                    db.recompute_weekly_summary(core_ae_email, r["_date"])
                except Exception:
                    pass
                st.cache_data.clear()
                st.rerun()

    if can_select:
        label = "✅ Evaluated — view / edit" if done else "📝 Evaluate this session"
        with st.expander(label, expanded=False):
            _evaluation_form(r, sid, name, role, user_email, done, core_ae_email)


def _evaluation_form(r, sid, trainer_name, role, user_email, done, core_ae_email=None):
    """The post-session form. Writes to session_evaluation."""
    prev = {}
    if done:
        allrows = db.get_evaluations(user_email)
        match = allrows[allrows["session_id"] == sid]
        if not match.empty:
            prev = match.iloc[0].to_dict()

    # --- auto-filled session facts, shown as a readable panel (not ghosted
    #     disabled inputs). These are pulled straight from CMIS. ---
    day = pd.to_datetime(r["_date"]).strftime("%A, %d %B %Y")
    st.markdown(
        f"""<div class="eval-facts">
          <div class="eval-facts-title">Session details &nbsp;<span class="chip">auto-filled from CMIS</span></div>
          <div class="eval-grid">
            <div><span class="ef-k">Trainer</span><span class="ef-v">{trainer_name}</span></div>
            <div><span class="ef-k">Date</span><span class="ef-v">{day}</span></div>
            <div><span class="ef-k">Time</span><span class="ef-v">{r['slot_time']}</span></div>
            <div><span class="ef-k">Batch</span><span class="ef-v">{r['batch_code']}</span></div>
            <div><span class="ef-k">Module</span><span class="ef-v">{r['m_code']}</span></div>
            <div><span class="ef-k">Program</span><span class="ef-v">{r['program_name']}</span></div>
          </div>
          <div class="ef-sid"><span class="ef-k">Session ID</span>{sid}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    with st.form(f"eval_{sid}", border=False):
        st.markdown("**Your evaluation**")
        c1, c2 = st.columns(2)
        with c1:
            duration = st.number_input(
                "Duration observed (minutes)", min_value=0, max_value=600, step=5,
                value=int(prev.get("duration_minutes") or 30), key=f"dur_{sid}",
            )
        with c2:
            rating = st.select_slider(
                "Rating", options=[1, 2, 3, 4, 5],
                value=int(prev.get("rating") or 3), key=f"rt_{sid}",
            )

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
            try:
                if core_ae_email:
                    db.recompute_weekly_summary(core_ae_email, r["_date"])
            except Exception:
                pass
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
