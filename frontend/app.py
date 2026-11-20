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


st.title("TestSpecGeneration")
st.caption("Automotive Verification & Validation — Phase 1 application foundation")

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

st.subheader("Project selection")
try:
    projects = get_projects()
except requests.RequestException as exc:
    st.error(f"Unable to load project configuration: {exc}")
    st.stop()

if not projects:
    st.warning("No project configurations were found.")
    st.stop()

project_by_name = {item["name"]: item for item in projects}
selected_name = st.selectbox("Select project", list(project_by_name))
selected_project = project_by_name[selected_name]

left, right = st.columns(2)
with left:
    st.metric("Project ID", selected_project["id"])
with right:
    st.metric("Enabled features", len(selected_project["features"]))

st.write(selected_project.get("description", ""))
features = selected_project.get("features", [])
if features:
    selected_feature = st.selectbox("Select feature", features)
    st.session_state["selected_project_id"] = selected_project["id"]
    st.session_state["selected_feature_id"] = selected_feature
    st.info(
        "Project configuration is loaded successfully. Requirement upload and "
        "AI workflow execution will be introduced in later phases."
    )
else:
    st.warning("This project currently has no enabled features.")
