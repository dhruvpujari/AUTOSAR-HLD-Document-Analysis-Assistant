"""Streamlit front end. Run:  streamlit run ui/streamlit_app.py"""
import os
import pandas as pd
import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")
TOKEN = os.environ.get("APP_TOKEN", "")

st.set_page_config(page_title="AUTOSAR HLD Assistant", layout="wide")


def call(method, url, **kw):
    headers = {"x-user": st.session_state.get("user", "engineer")}
    if TOKEN:
        headers["x-token"] = TOKEN
    r = requests.request(method, API + url, headers=headers, timeout=900, **kw)
    if r.status_code >= 400:
        st.error(f"{r.status_code}: {r.text[:300]}")
        return None
    return r


with st.sidebar:
    st.title("HLD Assistant")
    st.session_state["user"] = st.text_input("Your name", st.session_state.get("user", "engineer"))
    project = st.text_input("Project", "demo")
    st.caption("All processing is local. Answers are drafts until a reviewer accepts them.")

tab_up, tab_ask, tab_inv, tab_cmp, tab_rev = st.tabs(
    ["Upload", "Ask", "Inventory and checks", "Compare revisions", "Review queue"])

# ---------------------------------------------------------------- upload
with tab_up:
    f = st.file_uploader("HLD PDF", type=["pdf"])
    ver = st.text_input("Version label", "1.0")
    if f and st.button("Ingest"):
        with st.spinner("Parsing, chunking and embedding..."):
            r = call("POST", "/ingest", data={"project": project, "version": ver},
                     files={"file": (f.name, f.getvalue(), "application/pdf")})
        if r:
            st.success("Ingested")
            st.json(r.json()["eda"])
    r = call("GET", "/documents", params={"project": project})
    if r and r.json():
        st.dataframe(pd.DataFrame(r.json()), use_container_width=True)

# ------------------------------------------------------------------- ask
with tab_ask:
    q = st.text_input("Question about the uploaded HLDs")
    if q and st.button("Ask"):
        with st.spinner("Searching and generating..."):
            r = call("POST", "/query", json={"project": project, "question": q})
        if r:
            a = r.json()
            st.markdown(a["answer"])
            st.caption(f"Confidence: **{a['confidence']}**  |  {a['latency_s']} s  |  answer id {a['log_id']}")
            for s in a["sources"]:
                with st.expander(f"{s.get('tag', '')} {s['doc']} v{s['version']}, p.{s['page']}, {s['section']}"):
                    st.text(s["text"])

# ------------------------------------------------------------- inventory
with tab_inv:
    docs = (call("GET", "/documents", params={"project": project}) or None)
    docs = docs.json() if docs else []
    if docs:
        pick = st.selectbox("Document", docs, format_func=lambda d: f"#{d['id']} {d['name']} v{d['version']}")
        if st.button("Extract inventory and run checks (slow)"):
            with st.spinner("One LLM call per chunk, this takes a few minutes..."):
                r = call("POST", f"/extract/{pick['id']}")
            if r:
                st.write(r.json())
        inv = call("GET", f"/entities/{pick['id']}")
        if inv:
            inv = inv.json()
            st.subheader("Components")
            st.dataframe(pd.DataFrame([{"component": n, "ports": len(c["ports"]),
                                        "depends_on": ", ".join(c["depends_on"]), "page": c.get("page")}
                                       for n, c in inv["components"].items()]), use_container_width=True)
            st.subheader("Interfaces")
            st.dataframe(pd.DataFrame([{"interface": n, "elements": ", ".join(i["elements"]), "page": i.get("page")}
                                       for n, i in inv["interfaces"].items()]), use_container_width=True)
            st.subheader("Signals")
            st.dataframe(pd.DataFrame([{"signal": n, "producer": s["producer"], "consumers": ", ".join(s["consumers"]),
                                        "page": s.get("page")} for n, s in inv["signals"].items()]), use_container_width=True)
            st.subheader("Potential inconsistencies")
            fnd = call("GET", f"/findings/{pick['id']}")
            if fnd:
                st.dataframe(pd.DataFrame(fnd.json()), use_container_width=True)
            for fmt in ("csv", "json"):
                e = call("GET", f"/export/{pick['id']}", params={"fmt": fmt})
                if e:
                    st.download_button(f"Download {fmt.upper()}", e.content, f"inventory_{pick['id']}.{fmt}")

# --------------------------------------------------------------- compare
with tab_cmp:
    if docs:
        c1, c2 = st.columns(2)
        old = c1.selectbox("Old revision", docs, key="o", format_func=lambda d: f"#{d['id']} {d['name']} v{d['version']}")
        new = c2.selectbox("New revision", docs, key="n", format_func=lambda d: f"#{d['id']} {d['name']} v{d['version']}")
        if st.button("Compare"):
            r = call("POST", "/compare", params={"old_id": old["id"], "new_id": new["id"]})
            if r:
                st.dataframe(pd.DataFrame(r.json()), use_container_width=True)

# ---------------------------------------------------------------- review
with tab_rev:
    r = call("GET", "/review/pending")
    if r:
        data = r.json()
        for table, key in (("findings", "findings"), ("qa_log", "answers")):
            st.subheader(key.capitalize())
            for row in data[key][:25]:
                label = row.get("message") or row.get("question")
                with st.expander(f"#{row['id']}  {label[:100]}"):
                    st.write(row.get("answer", ""))
                    note = st.text_input("Note", key=f"n{table}{row['id']}")
                    b1, b2, b3 = st.columns(3)
                    for col, status in zip((b1, b2, b3), ("accepted", "edited", "rejected")):
                        if col.button(status.capitalize(), key=f"{table}{row['id']}{status}"):
                            call("POST", "/review", json={"table": table, "id": row["id"], "status": status, "note": note})
                            st.rerun()
