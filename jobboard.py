import streamlit as st
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import date
import re
import pandas as pd

# ── Database ──────────────────────────────────────────────────────────────────

DB_PATH = "job_tracker.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            job_title    TEXT,
            url          TEXT,
            applied_date TEXT,
            salary       TEXT,
            status       TEXT DEFAULT "Applied",
            notes        TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_job(company_name, job_title, url, applied_date, salary, status, notes):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        '''INSERT INTO jobs (company_name, job_title, url, applied_date, salary, status, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (company_name, job_title, url, str(applied_date), salary, status, notes)
    )
    conn.commit()
    conn.close()

def get_jobs():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM jobs ORDER BY applied_date DESC", conn)
    conn.close()
    return df

def update_status(job_id, new_status):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
    conn.commit()
    conn.close()

def delete_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

# ── Scraper ───────────────────────────────────────────────────────────────────

def fetch_job_details(url: str):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")

        # ── Company name ──────────────────────────────────────────────────────
        company = ""
        # 1. og:site_name
        og_site = soup.find("meta", property="og:site_name")
        if og_site:
            company = og_site.get("content", "").strip()

        # 2. Page <title> heuristics  e.g. "Job Title at Kindred | LinkedIn"
        if not company:
            title_tag = soup.find("title")
            if title_tag:
                t = title_tag.text
                if " at " in t:
                    company = t.split(" at ")[-1].split("|")[0].split("-")[0].strip()
                elif " - " in t:
                    parts = [p.strip() for p in t.split(" - ")]
                    company = parts[-1] if len(parts) > 1 else ""

        # 3. Common class / data attributes
        if not company:
            for attr in ["data-company-name", "data-employer", "data-org"]:
                tag = soup.find(attrs={attr: True})
                if tag:
                    company = tag[attr].strip()
                    break

        # ── Job title ─────────────────────────────────────────────────────────
        job_title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title:
            job_title = og_title.get("content", "").strip()
        if not job_title:
            h1 = soup.find("h1")
            if h1:
                job_title = h1.get_text(separator=" ").strip()

        # ── Salary ────────────────────────────────────────────────────────────
        salary = ""
        text = soup.get_text(" ")
        salary_patterns = [
            r"\$[\d,]+\s*[–\-]\s*\$[\d,]+(?:\s*(?:per year|\/yr|annually|\/year|a year))?",
            r"\$[\d,]+(?:\+)?(?:\s*(?:per year|\/yr|annually|per hour|\/hr|\/hour))",
            r"[\d,]+\s*[–\-]\s*[\d,]+\s*(?:USD|CAD)\b",
            r"(?:Salary|Compensation|Base Pay|Pay Range)[:\s]+\$[\d,\s\-–]+",
        ]
        for pat in salary_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                salary = m.group(0).strip()
                break

        return company, job_title, salary, None

    except Exception as exc:
        return "", "", "", str(exc)

# ── UI ────────────────────────────────────────────────────────────────────────

STATUS_OPTIONS = ["Applied", "Phone Screen", "Interview", "Final Round", "Offer", "Rejected", "Withdrawn"]

STATUS_COLORS = {
    "Applied":      "#4A90D9",
    "Phone Screen": "#F5A623",
    "Interview":    "#7B68EE",
    "Final Round":  "#9B59B6",
    "Offer":        "#27AE60",
    "Rejected":     "#E74C3C",
    "Withdrawn":    "#95A5A6",
}

def badge(status):
    color = STATUS_COLORS.get(status, "#888")
    return f'<span style="background:{color};color:#fff;padding:2px 10px;border-radius:12px;font-size:0.8rem;font-weight:600">{status}</span>'

init_db()

st.set_page_config(page_title="Job Tracker", page_icon="💼", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 2rem; }
        .metric-card {
            background: #1e1e2e;
            border-radius: 12px;
            padding: 1rem 1.5rem;
            text-align: center;
        }
    </style>
""", unsafe_allow_html=True)

st.title("💼 Job Application Tracker")
st.caption("Paste a job URL and let the tracker do the rest.")

tab1, tab2 = st.tabs(["➕  Add Application", "📋  My Applications"])

# ── TAB 1 : Add ───────────────────────────────────────────────────────────────
with tab1:
    st.subheader("New Job Application")

    url_col, btn_col = st.columns([4, 1])
    with url_col:
        url_input = st.text_input("Job Posting URL", placeholder="https://jobs.example.com/senior-engineer-123", label_visibility="collapsed")
    with btn_col:
        fetch_clicked = st.button("🔍 Fetch Details", use_container_width=True, disabled=not url_input)

    if fetch_clicked and url_input:
        with st.spinner("Fetching job details from the URL…"):
            company, title, salary, err = fetch_job_details(url_input)
            st.session_state["fetched"] = {
                "company": company, "title": title,
                "salary": salary, "url": url_input, "error": err
            }

    fetched = st.session_state.get("fetched", {})

    if fetched:
        if fetched.get("error"):
            st.warning(f"⚠️ Auto-fetch failed ({fetched['error']}). Fill in the fields manually below.")
        elif fetched.get("company") or fetched.get("title"):
            st.success("✅ Details fetched! Review and save below.")

    with st.form("add_job_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            company_name = st.text_input("Company Name *", value=fetched.get("company", ""))
            job_title    = st.text_input("Job Title",      value=fetched.get("title",   ""))
            applied_date = st.date_input("Date Applied",   value=date.today())
        with c2:
            salary  = st.text_input("Salary / Compensation", value=fetched.get("salary", ""),
                                    placeholder="e.g. $130,000 – $160,000")
            status  = st.selectbox("Application Status", STATUS_OPTIONS)
            notes   = st.text_area("Notes", placeholder="Recruiter name, referral, job req ID…", height=105)

        saved_url = fetched.get("url", url_input or "")
        submitted = st.form_submit_button("✅ Save Application", use_container_width=True)

        if submitted:
            if not company_name.strip():
                st.error("Company name is required.")
            else:
                add_job(company_name.strip(), job_title.strip(), saved_url,
                        applied_date, salary.strip(), status, notes.strip())
                st.success(f"🎉 Application to **{company_name}** saved!")
                st.session_state["fetched"] = {}

# ── TAB 2 : View ──────────────────────────────────────────────────────────────
with tab2:
    df = get_jobs()

    if df.empty:
        st.info("No applications yet — head to **Add Application** to track your first one!")
    else:
        # Metrics row
        total     = len(df)
        interviews = len(df[df["status"].isin(["Interview", "Final Round"])])
        offers    = len(df[df["status"] == "Offer"])
        rejected  = len(df[df["status"] == "Rejected"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("📨 Total Applied",  total)
        m2.metric("🗣️ Interviews",     interviews)
        m3.metric("🏆 Offers",         offers)
        m4.metric("❌ Rejected",        rejected)

        st.divider()

        # Filters
        f1, f2 = st.columns([2, 2])
        with f1:
            status_filter = st.multiselect(
                "Filter by Status", options=STATUS_OPTIONS,
                default=STATUS_OPTIONS
            )
        with f2:
            search = st.text_input("Search company / title", placeholder="e.g. Kindred")

        filtered = df[df["status"].isin(status_filter)]
        if search:
            mask = (
                filtered["company_name"].str.contains(search, case=False, na=False) |
                filtered["job_title"].str.contains(search, case=False, na=False)
            )
            filtered = filtered[mask]

        st.markdown(f"**{len(filtered)} application(s) found**")

        # Render table with clickable URLs and colored badges
        for _, row in filtered.iterrows():
            with st.expander(f"🏢 {row['company_name']}  —  {row['job_title'] or 'N/A'}"):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**🔗 URL:** [{row['url']}]({row['url']})" if row["url"] else "**URL:** —")
                    st.markdown(f"**📅 Applied:** {row['applied_date']}")
                    st.markdown(f"**💰 Salary:** {row['salary'] or 'Not listed'}")
                    st.markdown(f"**📝 Notes:** {row['notes'] or '—'}")
                    st.markdown(f"**Status:** {badge(row['status'])}", unsafe_allow_html=True)
                with col_b:
                    new_status = st.selectbox(
                        "Update status", STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index(row["status"]) if row["status"] in STATUS_OPTIONS else 0,
                        key=f"status_{row['id']}"
                    )
                    if st.button("Update", key=f"upd_{row['id']}"):
                        update_status(row["id"], new_status)
                        st.rerun()
                    if st.button("🗑️ Delete", key=f"del_{row['id']}"):
                        delete_job(row["id"])
                        st.rerun()