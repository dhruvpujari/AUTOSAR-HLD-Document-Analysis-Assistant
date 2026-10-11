"""Streamlit front end. Run: streamlit run ui/streamlit_app.py"""
import json
import os
from pathlib import Path

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
    response = requests.request(
        method, API + url, headers=headers, timeout=900, **kw
    )
    if response.status_code >= 400:
        st.error(f"{response.status_code}: {response.text[:300]}")
        return None
    return response


with st.sidebar:
    st.title("HLD Assistant")
    st.session_state["user"] = st.text_input(
        "Your name", st.session_state.get("user", "engineer")
    )
    project = st.text_input("Project", "demo")
    st.caption(
        "All processing is local. Answers are drafts until a reviewer accepts them."
    )

tab_up, tab_ask, tab_inv, tab_cmp, tab_rev, tab_eval = st.tabs(
    [
        "Upload",
        "Ask",
        "Inventory and checks",
        "Compare revisions",
        "Review queue",
        "Evaluation Dashboard",
    ]
)

# ---------------------------------------------------------------- upload
with tab_up:
    uploaded_file = st.file_uploader("HLD PDF", type=["pdf"])
    version = st.text_input("Version label", "1.0")

    if uploaded_file and st.button("Ingest"):
        with st.spinner("Parsing, chunking and embedding..."):
            response = call(
                "POST",
                "/ingest",
                data={"project": project, "version": version},
                files={
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        "application/pdf",
                    )
                },
            )
        if response:
            st.success("Ingested")
            st.json(response.json().get("eda", {}))

    response = call("GET", "/documents", params={"project": project})
    if response and response.json():
        st.dataframe(pd.DataFrame(response.json()), use_container_width=True)

# ------------------------------------------------------------------- ask
with tab_ask:
    question = st.text_input("Question about the uploaded HLDs")
    if question and st.button("Ask"):
        with st.spinner("Searching and generating..."):
            response = call(
                "POST",
                "/query",
                json={"project": project, "question": question},
            )
        if response:
            answer_data = response.json()
            st.markdown(answer_data.get("answer", "No answer returned."))
            st.caption(
                f"Confidence: **{answer_data.get('confidence', 'N/A')}** | "
                f"{answer_data.get('latency_s', 'N/A')} s | "
                f"answer id {answer_data.get('log_id', 'N/A')}"
            )
            for source in answer_data.get("sources", []):
                with st.expander(
                    f"{source.get('tag', '')} {source.get('doc', '')} "
                    f"v{source.get('version', '')}, p.{source.get('page', '?')}, "
                    f"{source.get('section', '')}"
                ):
                    st.text(source.get("text", ""))

# ------------------------------------------------------------- inventory
with tab_inv:
    documents_response = call(
        "GET", "/documents", params={"project": project}
    )
    docs = documents_response.json() if documents_response else []

    if docs:
        selected_doc = st.selectbox(
            "Document",
            docs,
            format_func=lambda doc: (
                f"#{doc['id']} {doc['name']} v{doc['version']}"
            ),
        )

        if st.button("Extract inventory and run checks (slow)"):
            with st.spinner(
                "Extracting inventory and running checks; this may take a few minutes..."
            ):
                response = call("POST", f"/extract/{selected_doc['id']}")
            if response:
                st.write(response.json())

        inventory_response = call(
            "GET", f"/entities/{selected_doc['id']}"
        )
        if inventory_response:
            inventory = inventory_response.json()

            st.subheader("Components")
            components = inventory.get("components", {})
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "component": name,
                            "ports": len(component.get("ports", [])),
                            "depends_on": ", ".join(
                                component.get("depends_on", [])
                            ),
                            "page": component.get("page"),
                        }
                        for name, component in components.items()
                    ]
                ),
                use_container_width=True,
            )

            st.subheader("Interfaces")
            interfaces = inventory.get("interfaces", {})
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "interface": name,
                            "elements": ", ".join(
                                interface.get("elements", [])
                            ),
                            "page": interface.get("page"),
                        }
                        for name, interface in interfaces.items()
                    ]
                ),
                use_container_width=True,
            )

            st.subheader("Signals")
            signals = inventory.get("signals", {})
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "signal": name,
                            "producer": signal.get("producer", ""),
                            "consumers": ", ".join(
                                signal.get("consumers", [])
                            ),
                            "page": signal.get("page"),
                        }
                        for name, signal in signals.items()
                    ]
                ),
                use_container_width=True,
            )

            st.subheader("Potential inconsistencies")
            findings_response = call(
                "GET", f"/findings/{selected_doc['id']}"
            )
            if findings_response:
                st.dataframe(
                    pd.DataFrame(findings_response.json()),
                    use_container_width=True,
                )

            for file_format in ("csv", "json"):
                export_response = call(
                    "GET",
                    f"/export/{selected_doc['id']}",
                    params={"fmt": file_format},
                )
                if export_response:
                    st.download_button(
                        label=f"Download {file_format.upper()}",
                        data=export_response.content,
                        file_name=(
                            f"inventory_{selected_doc['id']}.{file_format}"
                        ),
                    )
    else:
        st.info("No documents found for this project. Upload an HLD PDF first.")

# --------------------------------------------------------------- compare
with tab_cmp:
    compare_response = call(
        "GET", "/documents", params={"project": project}
    )
    compare_docs = compare_response.json() if compare_response else []

    if compare_docs:
        column_old, column_new = st.columns(2)
        old_doc = column_old.selectbox(
            "Old revision",
            compare_docs,
            key="compare_old",
            format_func=lambda doc: (
                f"#{doc['id']} {doc['name']} v{doc['version']}"
            ),
        )
        new_doc = column_new.selectbox(
            "New revision",
            compare_docs,
            key="compare_new",
            format_func=lambda doc: (
                f"#{doc['id']} {doc['name']} v{doc['version']}"
            ),
        )

        if st.button("Compare revisions"):
            if old_doc["id"] == new_doc["id"]:
                st.warning("Select two different document revisions to compare.")
            else:
                response = call(
                    "POST",
                    "/compare",
                    params={
                        "old_id": old_doc["id"],
                        "new_id": new_doc["id"],
                    },
                )
                if response:
                    diff_data = response.json()
                    if diff_data:
                        st.dataframe(
                            pd.DataFrame(diff_data),
                            use_container_width=True,
                        )
                    else:
                        st.info("No differences were returned.")
    else:
        st.info("Upload at least one document before comparing revisions.")

# ---------------------------------------------------------------- review
with tab_rev:
    review_response = call("GET", "/review/pending")
    if review_response:
        review_data = review_response.json()

        for table_name, data_key in (
            ("findings", "findings"),
            ("qa_log", "answers"),
        ):
            st.subheader(data_key.capitalize())
            rows = review_data.get(data_key, [])
            if not rows:
                st.caption("Nothing pending in this section.")

            for row in rows[:25]:
                label = (
                    row.get("message")
                    or row.get("question")
                    or "(No label)"
                )
                with st.expander(f"#{row.get('id', '?')} {label[:100]}"):
                    st.write(row.get("answer", row.get("message", "")))
                    note = st.text_input(
                        "Review note",
                        key=f"note_{table_name}_{row.get('id')}",
                    )
                    col_accept, col_edit, col_reject = st.columns(3)

                    for column, status in zip(
                        (col_accept, col_edit, col_reject),
                        ("accepted", "edited", "rejected"),
                    ):
                        if column.button(
                            status.capitalize(),
                            key=f"{table_name}_{row.get('id')}_{status}",
                        ):
                            review_result = call(
                                "POST",
                                "/review",
                                json={
                                    "table": table_name,
                                    "id": row["id"],
                                    "status": status,
                                    "note": note,
                                },
                            )
                            if review_result:
                                st.rerun()

# ------------------------------------------------------ Evaluation Dashboard
with tab_eval:
    st.header("Evaluation Dashboard")
    st.caption("Metrics loaded from your saved evaluation results.")

    # Project root: project_root/Code/ui/streamlit_app.py
    results_dir = Path(__file__).resolve().parents[2] / "Evaluation_Results"

    if results_dir.exists():
        evaluation_runs = sorted(
            [
                run_dir
                for run_dir in results_dir.glob("run_*")
                if run_dir.is_dir()
                and (run_dir / "summary.json").is_file()
            ],
            key=lambda run_dir: run_dir.stat().st_mtime,
            reverse=True,
        )
    else:
        evaluation_runs = []

    if not evaluation_runs:
        st.warning(
            f"No summary.json evaluation results were found in {results_dir}. "
            "Check that the evaluation script has been run successfully."
        )
    else:
        selected_run = st.selectbox(
            "Select evaluation run",
            evaluation_runs,
            format_func=lambda run_dir: run_dir.name,
        )

        try:
            with (selected_run / "summary.json").open(
                "r", encoding="utf-8"
            ) as summary_file:
                summary = json.load(summary_file)
        except (OSError, json.JSONDecodeError) as error:
            st.error(f"Could not read the evaluation summary: {error}")
            summary = {}

        if summary:
            qa_metrics = summary.get("qa", {})

            def format_metric(value, suffix="%"):
                if isinstance(value, (int, float)):
                    return f"{value:.1f}{suffix}"
                return "N/A"

            st.subheader("Question-answering performance")
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            metric_col1.metric(
                "Questions tested", qa_metrics.get("questions", "N/A")
            )
            metric_col2.metric(
                "Answer correctness",
                format_metric(qa_metrics.get("answer_correct_pct")),
            )
            metric_col3.metric(
                "Citation accuracy",
                format_metric(qa_metrics.get("citation_accuracy_pct")),
            )

            metric_col4, metric_col5, metric_col6 = st.columns(3)
            metric_col4.metric(
                "Retrieval Hit@K",
                format_metric(qa_metrics.get("retrieval_hit_at_k_pct")),
            )
            metric_col5.metric(
                "Not-found accuracy",
                format_metric(qa_metrics.get("not_found_correct_pct")),
            )
            metric_col6.metric(
                "Median response time",
                format_metric(qa_metrics.get("latency_median_s"), " sec"),
            )

            st.subheader("Question category performance")
            category_metrics = {
                "Direct facts": qa_metrics.get("answer_correct_pct_fact"),
                "Table lookup": qa_metrics.get("answer_correct_pct_table"),
                "Multi-item": qa_metrics.get("answer_correct_pct_multi"),
            }
            category_df = pd.DataFrame(
                [
                    {"Category": category, "Correctness (%)": value}
                    for category, value in category_metrics.items()
                    if isinstance(value, (int, float))
                ]
            )

            if not category_df.empty:
                st.bar_chart(
                    category_df.set_index("Category"),
                    y="Correctness (%)",
                )
            else:
                st.info(
                    "Category-level correctness metrics are not available "
                    "in this evaluation run."
                )

            st.subheader("Evaluation configuration")
            st.json(
                {
                    "Tag": summary.get("tag"),
                    "LLM": summary.get("llm"),
                    "Embedding model": summary.get("embedding"),
                    "Chunk size (tokens)": summary.get("chunk_tokens"),
                    "Top K": summary.get("top_k"),
                    "Minimum retrieval score": summary.get("min_score"),
                    "Prompt version": summary.get("prompt_version"),
                }
            )

            st.subheader("Revision comparison performance")
            revision_metrics = summary.get("revision_diff", {})
            if revision_metrics:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Precision": revision_metrics.get("precision"),
                                "Recall": revision_metrics.get("recall"),
                                "F1 Score": revision_metrics.get("f1"),
                            }
                        ]
                    ),
                    use_container_width=True,
                )
            else:
                st.info(
                    "Revision comparison metrics are not available "
                    "in this evaluation run."
                )

            st.subheader("Entity extraction performance")
            extraction_metrics = summary.get("extraction", [])
            if extraction_metrics:
                extraction_rows = [
                    {
                        "Document": item.get("doc"),
                        "Component F1": item.get("components_f1"),
                        "Interface F1": item.get("interfaces_f1"),
                        "Signal F1": item.get("signals_f1"),
                        "Port-link F1": item.get("port_links_f1"),
                        "Defect recall": item.get("defect_recall"),
                        "False alarms": item.get("defect_false_alarms"),
                    }
                    for item in extraction_metrics
                ]
                st.dataframe(
                    pd.DataFrame(extraction_rows),
                    use_container_width=True,
                )
            else:
                st.info(
                    "Entity extraction metrics are not available "
                    "in this evaluation run."
                )

            st.info(
                "These metrics are from the selected saved run on the current "
                "synthetic test set. They do not establish performance on "
                "real production AUTOSAR documents."
            )
