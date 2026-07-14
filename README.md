# AE Utilization Tracker — Streamlit

Reads faculty sessions from the CMIS database (read-only) and reads/writes app
state to the Anudip_AE_Team database (the 5 hakathon tables).

## Setup

1. Install deps:

       pip install -r requirements.txt

2. Create secrets:

       cp .streamlit/secrets.toml.example .streamlit/secrets.toml
       # then edit .streamlit/secrets.toml and fill in the two DB passwords

3. Test the connections:

       python test_connection.py

4. Seed the roster (writes user_roles + core_ae_faculty_map, one time):

       python seed_appdb.py

5. Run:

       streamlit run app.py

## Databases

- **CMIS** (read-only): `upcoming_trainer_utilization_view` — faculty sessions.
- **App DB** (read/write): `core_ae_faculty_map`, `extended_ae_session_selection`,
  `session_highlight_flags`, `user_roles`, `weekly_ae_summary`.

Yellow = available for observation. Green = claimed (Selected/Confirmed).

## Deploy to Streamlit Cloud

Push this folder to GitHub (secrets.toml is gitignored). In Streamlit Cloud,
paste the contents of your secrets.toml into the app's **Secrets** box. The two
Anudip DBs must allow inbound connections from Streamlit Cloud's IPs.
