"""Streamlit frontend entry point."""

import json
import os
import time

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


st.set_page_config(
    page_title="TestSpecGeneration",
    page_icon="🧪",
    layout="wide",
)

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
_TERMINAL_STATUSES = {"completed", "failed", "awaiting_clarification"}


@st.cache_data(ttl=15)
def get_backend_health() -> tuple[bool, str]:
    try:
        response = requests.get(f"{BACKEND_BASE_URL}/api/v1/health", timeout=3)
        response.raise_for_status()
        payload = response.json()
        return payload.get("status") == "ok", "Backend is reachable."
    except requests.RequestException as exc:
        return False, f"Cannot reach backend: {exc}"


@st.cache_data(ttl=15)
def get_projects() -> list[dict]:
    response = requests.get(f"{BACKEND_BASE_URL}/api/v1/projects", timeout=5)
    response.raise_for_status()
    return response.json().get("items", [])


@st.cache_data(ttl=15)
def get_agent_status() -> dict:
    response = requests.get(f"{BACKEND_BASE_URL}/api/v1/agents/status", timeout=5)
    response.raise_for_status()
    return response.json()


def error_message(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail)


def poll_workflow(execution_id: str, progress, stage_status) -> dict:
    """Poll the backend for real agent-by-agent progress until a terminal state."""
    poll_interval = float(os.getenv("WORKFLOW_POLL_INTERVAL_SECONDS", "1.5"))
    max_polls = int(os.getenv("WORKFLOW_MAX_POLL_ATTEMPTS", "400"))
    execution: dict = {}
    for _ in range(max_polls):
        response = requests.get(
            f"{BACKEND_BASE_URL}/api/v1/workflow/executions/{execution_id}",
            timeout=10,
        )
        if not response.ok:
            stage_status.error(f"Could not retrieve workflow status: {error_message(response)}")
            return execution
        execution = response.json()
        records = execution.get("agent_executions", [])
        total = len(records) or 1
        finished = sum(1 for record in records if record["status"] in {"completed", "failed", "skipped"})
        running_record = next((record for record in records if record["status"] == "running"), None)
        progress.progress(
            min(int(finished / total * 100), 100),
            text=f"Running: {running_record['label']}" if running_record else "Processing...",
        )
        if execution.get("status") in _TERMINAL_STATUSES:
            return execution
        time.sleep(poll_interval)
    stage_status.warning("Stopped polling after the maximum number of attempts.")
    return execution


st.title("TestSpecGeneration")
st.caption("Automotive Verification & Validation — Phase 2 agent orchestration")

health_ok, health_message = get_backend_health()
if health_ok:
    st.success(health_message)
else:
    st.error(health_message)
    st.info(
        "Start the FastAPI backend in a separate terminal using: "
        "`uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000`"
    )
    st.stop()

try:
    projects = get_projects()
    agent_status = get_agent_status()
except requests.RequestException as exc:
    st.error(f"Unable to load backend configuration: {exc}")
    st.stop()

st.subheader("Enterprise AI connection status")
endpoint_col, credential_col, invocation_col = st.columns(3)
endpoint_col.metric("Endpoint configured", "Yes" if agent_status["endpoint_configured"] else "No")
credential_col.metric(
    "Credentials configured", "Yes" if agent_status["credentials_configured"] else "No"
)
invocation_col.metric(
    "Workflow ready", "Yes" if agent_status["invocation_configuration_available"] else "No"
)
st.caption(f"Invocation mode: `{agent_status['invocation_mode']}`")
for note in agent_status["integration_status"]:
    st.info(note)

if not projects:
    st.warning("No project configurations were found.")
    st.stop()

st.subheader("Project and requirements")
project_by_name = {item["name"]: item for item in projects}
selected_name = st.selectbox("Select project", list(project_by_name))
selected_project = project_by_name[selected_name]
project_id = selected_project["id"]

st.write(selected_project.get("description", ""))
features = selected_project.get("features", [])
ADD_NEW_FEATURE_OPTION = "+ Add a new feature..."
feature_choice = st.selectbox("Select feature", features + [ADD_NEW_FEATURE_OPTION])

custom_feature_description = ""
if feature_choice == ADD_NEW_FEATURE_OPTION:
    selected_feature = st.text_input(
        "New feature name", placeholder="e.g. trailer_detection"
    ).strip()
    custom_feature_description = st.text_area(
        "Feature description",
        placeholder=(
            "Describe what this feature does, its interfaces/operating modes and any "
            "constraints — this is included as context when generating the test specification."
        ),
    ).strip()
    if not selected_feature:
        st.warning("Enter a name for the new feature before continuing.")
else:
    selected_feature = feature_choice

st.session_state["selected_project_id"] = project_id
st.session_state["selected_feature_id"] = selected_feature

project_agents = agent_status.get("configured_agents", {}).get(project_id, {})
if project_agents:
    test_role = st.selectbox(
        "Agent connection test",
        options=list(project_agents),
        format_func=lambda role: role.replace("_", " ").title(),
    )
    if st.button("Test selected agent", use_container_width=True):
        with st.spinner(f"Testing {test_role.replace('_', ' ').title()}..."):
            response = requests.post(
                f"{BACKEND_BASE_URL}/api/v1/agents/{project_agents[test_role]}/test",
                timeout=150,
            )
        if response.ok:
            st.success(f"Agent connected: {response.json()['response']}")
        else:
            st.error(f"Agent connection test failed: {error_message(response)}")
else:
    st.warning("Configure all four agent IDs for this project to enable connection testing and execution.")

st.subheader("Requirements")
st.caption(
    "Upload one or more DNG Excel requirement exports (System / Software / Supporting-Interface), "
    "or enter requirements manually below. Uploaded files take precedence when both are provided."
)

uploaded_files = st.file_uploader(
    "DNG Excel requirement exports",
    type=["xlsx", "xlsm"],
    accept_multiple_files=True,
)

category_by_file: dict[str, str] = {}
if uploaded_files:
    st.caption("Optionally override the auto-detected category for any file.")
    for uploaded_file in uploaded_files:
        category_by_file[uploaded_file.name] = st.selectbox(
            f"Category — {uploaded_file.name}",
            options=["auto-detect", "system", "software", "supporting_interface"],
            key=f"category_{uploaded_file.name}",
        )

    if st.button("Parse uploaded requirement files", use_container_width=True):
        multipart_files = [
            ("files", (f.name, f.getvalue(), f.type or "application/octet-stream"))
            for f in uploaded_files
        ]
        categories = [
            "" if category_by_file[f.name] == "auto-detect" else category_by_file[f.name]
            for f in uploaded_files
        ]
        with st.spinner("Parsing and consolidating requirement files..."):
            ingest_response = requests.post(
                f"{BACKEND_BASE_URL}/api/v1/requirements/ingest",
                files=multipart_files,
                data={"categories": categories, "feature": selected_feature},
                timeout=60,
            )
        if not ingest_response.ok:
            st.error(f"Could not parse uploaded files: {error_message(ingest_response)}")
        else:
            st.session_state["ingestion_result"] = ingest_response.json()

ingestion_result = st.session_state.get("ingestion_result")
consolidated_requirements_json = None
if ingestion_result:
    meta = ingestion_result["meta"]
    errors = [f for f in ingestion_result["findings"] if f["severity"] == "ERROR"]
    warnings = [f for f in ingestion_result["findings"] if f["severity"] == "WARNING"]

    st.markdown(
        f"**Parsed {meta['total_requirements']} requirement(s) from {len(meta['source_files'])} file(s).**"
    )
    st.dataframe(
        [
            {
                "file": source["file_name"],
                "category": source["category"],
                "sheets": ", ".join(source["sheets_read"]),
                "requirements": source["requirement_count"],
            }
            for source in meta["source_files"]
        ],
        use_container_width=True,
        hide_index=True,
    )

    if errors:
        with st.expander(f"⚠️ {len(errors)} error(s) found", expanded=True):
            for finding in errors:
                st.error(f"[{finding.get('source_file', '-')}] {finding['message']}")
    if warnings:
        with st.expander(f"{len(warnings)} warning(s) found"):
            for finding in warnings:
                st.warning(f"[{finding.get('source_file', '-')}] {finding['message']}")

    with st.expander("View consolidated requirements JSON"):
        st.json(ingestion_result)

    if ingestion_result["requirements"]:
        consolidated_requirements_json = json.dumps(ingestion_result, indent=2)

requirements = st.text_area(
    "Complete requirement set",
    value=consolidated_requirements_json or "",
    height=260,
    placeholder="Enter one or more related automotive requirements, including their IDs where available.",
)
execute_disabled = (
    not project_agents
    or not agent_status["invocation_configuration_available"]
    or not selected_feature
)

if st.button(
    "Execute test specification workflow",
    type="primary",
    disabled=execute_disabled,
    use_container_width=True,
):
    if not requirements.strip():
        st.error("Enter at least one requirement before starting the workflow, or parse an uploaded file set.")
    else:
        effective_requirements = requirements
        if custom_feature_description:
            effective_requirements = (
                f"Feature: {selected_feature}\n"
                f"Feature description: {custom_feature_description}\n\n"
                f"{requirements}"
            )
        start_response = requests.post(
            f"{BACKEND_BASE_URL}/api/v1/workflow/test-specification",
            json={"project": project_id, "requirements": effective_requirements},
            timeout=30,
        )
        if not start_response.ok:
            st.error(f"Could not start workflow: {error_message(start_response)}")
        else:
            progress = st.progress(0, text="Starting sequential workflow...")
            stage_status = st.empty()
            execution_id = start_response.json()["execution_id"]
            execution = poll_workflow(execution_id, progress, stage_status)
            st.session_state["workflow_execution"] = execution
            if execution.get("status") == "completed":
                progress.progress(100, text="Workflow completed.")
                stage_status.success("All agents completed successfully.")
            elif execution.get("status") == "awaiting_clarification":
                stage_status.warning(
                    "The requirement clarifier needs more information before continuing."
                )
            elif execution.get("status") == "failed":
                failed_record = next(
                    (
                        record
                        for record in execution.get("agent_executions", [])
                        if record.get("status") == "failed"
                    ),
                    None,
                )
                failed_stage = failed_record["label"] if failed_record else "Unknown stage"
                stage_status.error(
                    f"Workflow failed at {failed_stage}: "
                    f"{(failed_record or {}).get('error', {}).get('message', 'Unknown error')}"
                )

execution = st.session_state.get("workflow_execution")
if execution and execution.get("status") == "awaiting_clarification":
    st.subheader("Requirement clarification needed")
    if execution.get("resolved_from_history"):
        st.info(
            "Resolved from prior project knowledge:\n"
            + "\n".join(f"- {item}" for item in execution["resolved_from_history"])
        )
    open_questions = execution.get("open_questions", [])
    answers: dict[str, str] = {}
    for index, question in enumerate(open_questions):
        answers[question] = st.text_area(
            question, key=f"clarification_{execution['execution_id']}_{index}"
        )
    if st.button("Submit answers and continue", use_container_width=True):
        if not all(value.strip() for value in answers.values()):
            st.error("Answer every open question before continuing.")
        else:
            resume_response = requests.post(
                f"{BACKEND_BASE_URL}/api/v1/workflow/executions/{execution['execution_id']}/clarifications",
                json={"answers": answers},
                timeout=30,
            )
            if not resume_response.ok:
                st.error(f"Could not submit answers: {error_message(resume_response)}")
            else:
                progress = st.progress(0, text="Resuming workflow...")
                stage_status = st.empty()
                execution = poll_workflow(execution["execution_id"], progress, stage_status)
                st.session_state["workflow_execution"] = execution
                if execution.get("status") == "completed":
                    progress.progress(100, text="Workflow completed.")
                    stage_status.success("All agents completed successfully.")
                st.rerun()

execution = st.session_state.get("workflow_execution")
if execution and execution.get("execution_id"):
    st.subheader("Workflow execution")
    st.caption(f"Execution ID: `{execution['execution_id']}`")
    for record in execution.get("agent_executions", []):
        label = f"{record['label']}: {record['status']}"
        if record["status"] == "completed":
            st.success(label)
        elif record["status"] == "failed":
            st.error(f"{label} - {record.get('error', {}).get('message', '')}")
        elif record["status"] == "skipped":
            st.warning(f"{label} - not executed")
        else:
            st.info(label)
        if record.get("output"):
            with st.expander(f"View {record['label']} output"):
                st.markdown(record["output"])

    if execution.get("final_reviewed_output"):
        st.subheader("Reviewed test specification")
        st.markdown(execution["final_reviewed_output"])
