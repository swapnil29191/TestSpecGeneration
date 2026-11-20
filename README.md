# TestSpecGeneration — Phase 1 Foundation

A single-user Automotive V&V test-specification application foundation.

## Phase 1 scope

- Streamlit frontend, running independently from the API.
- FastAPI backend with health and project-list endpoints.
- YAML-based project configuration for Gateway, Zonal and ADAS.
- Environment-based application settings.
- Basic CORS configuration for the local Streamlit frontend.
- Unit tests for the backend.
- No CAPL workflow, local LLM, local vector database, or enterprise AI calls in this phase.

## Requirements

- Python 3.11+
- Access to install the packages in `requirements.txt`

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and adjust values if needed.

## Start the backend

From the repository root:

```bash
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend endpoints:

- Health: http://127.0.0.1:8000/health
- API health: http://127.0.0.1:8000/api/v1/health
- Projects: http://127.0.0.1:8000/api/v1/projects
- OpenAPI docs: http://127.0.0.1:8000/docs

## Start the frontend

In a second terminal, from the repository root:

```bash
streamlit run frontend/app.py
```

The frontend defaults to `http://127.0.0.1:8000` for the backend. Override with
`BACKEND_BASE_URL` in `.env` if required.

## Run tests

```bash
pytest -q
```

## Configuration

Project configuration is stored under `config/projects/*.yaml`. The backend
loads YAML files at request time, validates their basic structure, and returns
a safe project summary to the frontend. Agent IDs and enterprise KB IDs are
intentionally not populated in Phase 1; they will be added after the enterprise
platform API contract is confirmed in Phase 2.

## Security notes

- Never commit `.env` or real API credentials.
- `.env.example` contains placeholders only.
- Do not log requirement contents, prompts, access tokens, or secrets.
- This initial version is intended for local single-user development.
