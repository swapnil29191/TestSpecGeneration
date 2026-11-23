"""Streamlit frontend entry point."""

import os

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
WORKFLOW_LABELS = (
    "Requirement Analyzer",
    "Feature Context Analyzer",
    "Test Specification Generator",
    "Test Specification Reviewer",
)


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
if features:
    selected_feature = st.selectbox("Select feature", features)
    st.session_state["selected_project_id"] = project_id
    st.session_state["selected_feature_id"] = selected_feature
else:
    st.warning("This project currently has no enabled features.")

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

requirements = st.text_area(
    "Complete requirement set",
    height=260,
    placeholder="Enter one or more related automotive requirements, including their IDs where available.",
)
execute_disabled = not project_agents or not agent_status["invocation_configuration_available"]

if st.button(
    "Execute test specification workflow",
    type="primary",
    disabled=execute_disabled,
    use_container_width=True,
):
    if not requirements.strip():
        st.error("Enter at least one requirement before starting the workflow.")
    else:
        progress = st.progress(0, text="Starting sequential workflow...")
        stage_status = st.empty()
        stage_status.info(f"Current stage: {WORKFLOW_LABELS[0]}")
        with st.spinner("Executing enterprise agents in sequence..."):
            response = requests.post(
                f"{BACKEND_BASE_URL}/api/v1/workflow/test-specification",
                json={"project": project_id, "requirements": requirements},
                timeout=int(os.getenv("WORKFLOW_REQUEST_TIMEOUT_SECONDS", "600")),
            )
        try:
            execution = response.json()
        except ValueError:
            execution = {}
        st.session_state["workflow_execution"] = execution
        if response.ok and execution.get("status") == "completed":
            progress.progress(100, text="Workflow completed.")
            stage_status.success("All four agents completed successfully.")
        elif execution.get("execution_id"):
            failed_record = next(
                (
                    record
                    for record in execution.get("agent_executions", [])
                    if record.get("status") == "failed"
                ),
                None,
            )
            failed_stage = failed_record["label"] if failed_record else "Unknown stage"
            completed = execution.get("summary", {}).get("completed_agents", 0)
            progress.progress(int(completed / 4 * 100), text=f"Stopped at {failed_stage}")
            stage_status.error(
                f"Workflow failed at {failed_stage}: "
                f"{(failed_record or {}).get('error', {}).get('message', error_message(response))}"
            )
        else:
            progress.empty()
            stage_status.error(f"Workflow request failed: {error_message(response)}")

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
