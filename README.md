# TestSpecGeneration - Phase 2

A local, single-user Automotive V&V application that uses a FastAPI backend to orchestrate enterprise AI agents sequentially and a Streamlit frontend to submit requirements and review the generated specification.

## Phase 2 scope

- Existing Phase 1 health and YAML project APIs remain available.
- Gateway, Zonal and ADAS can each use four independently configured agent IDs.
- Agents execute in strict sequence: requirement analysis, feature analysis, test specification generation, and review.
- Each agent receives the original requirements and the required prior outputs.
- Mandatory-agent failure stops the remaining stages and returns the execution record.
- Execution IDs, per-agent status, timestamps, durations, outputs and errors are captured in memory.
- All tests mock enterprise invocation; no live AI call is required for the suite.

## Architecture

- `backend/app/integrations/enterprise_ai/` contains environment loading, the transport adapter, normalized responses and safe domain errors.
- `backend/app/orchestration/` contains declarative workflow steps, execution state and the sequential engine.
- `backend/app/api/routes/` contains agent status, connectivity-test and workflow endpoints.
- `frontend/app.py` communicates only with FastAPI and never calls the enterprise platform directly.

The orchestration engine does not know endpoint details. `EnterpriseAgentClient.invoke_agent(agent_id, input_data)` is the stable application boundary, backed by a replaceable transport protocol.

## Enterprise API assumption

The current repository's `Internal_AI/client.py` demonstrates an OpenAI-compatible call in which the enterprise agent ID is supplied as the `model` argument to `chat.completions.create`. Phase 2 preserves that established behavior in `OpenAICompatibleAgentTransport`:

```python
client.chat.completions.create(model=agent_id, messages=messages)
```

This is an integration assumption, not proof of every enterprise endpoint's contract. The invocation format is isolated in the transport adapter so it can be replaced when the platform contract is confirmed. No separate endpoint or KB retrieval client is invented, and the enterprise agents remain responsible for their own associated knowledge bases.

## Setup

Requirements:

- Python 3.11 or newer
- Access to install `requirements.txt`

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then set the endpoint and credential. Configure all four agent IDs for every project that should run workflows.

```env
ENTERPRISE_AI_BASE_URL=
ENTERPRISE_AI_API_KEY=
ENTERPRISE_AI_TIMEOUT_SECONDS=120
ENTERPRISE_AI_CONNECT_TIMEOUT_SECONDS=10
ENTERPRISE_AI_MAX_RETRIES=2
ENTERPRISE_AI_PROXY_URL=
ENTERPRISE_AI_VERIFY_SSL=true

GATEWAY_REQUIREMENT_ANALYZER_AGENT_ID=
GATEWAY_FEATURE_ANALYZER_AGENT_ID=
GATEWAY_TESTSPEC_GENERATOR_AGENT_ID=
GATEWAY_TESTSPEC_REVIEWER_AGENT_ID=
```

Repeat the four role-specific variables with `ZONAL_` and `ADAS_` prefixes for those projects. Empty or partially configured agent mappings are rejected before a workflow begins. The mapping derives from the normalized project ID and the role suffix, so additional projects can be configured without hardcoded Python agent IDs.

## Run

Start the backend from the repository root:

```powershell
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Start Streamlit in a second terminal:

```powershell
streamlit run frontend/app.py
```

The frontend uses `BACKEND_BASE_URL`, which defaults to `http://127.0.0.1:8000`.

## API

- `GET /api/v1/health`
- `GET /api/v1/projects`
- `GET /api/v1/agents/status`
- `POST /api/v1/agents/{agent_id}/test`
- `POST /api/v1/workflow/test-specification`
- OpenAPI documentation: `http://127.0.0.1:8000/docs`

Workflow request:

```json
{
  "project": "gateway",
  "requirements": "Complete requirement set goes here"
}
```

## Agent sequence

1. Requirement Analyzer checks completeness, ambiguities, testability, constraints, conflicts, clarification needs and safety gaps.
2. Feature Context Analyzer adds operating modes, interfaces, dependencies, scenarios and corner cases.
3. Test Specification Generator creates traceable test specifications and explicitly records assumptions and open questions.
4. Test Specification Reviewer checks coverage and quality and returns reviewed specifications plus findings.

The engine does not proceed after any failed mandatory agent.

## Tests

```powershell
python -m pytest -q
```

Tests cover sequence order, output handoff, fail-stop behavior at each early stage, configuration errors, authentication and timeout mapping, input validation, project validation, status, connection testing and workflow APIs. Enterprise network calls are mocked.

## Security

- Never commit `.env`, API keys or real requirement data.
- `.env.example` contains placeholders only.
- Requirement text and credentials are not logged by the application.
- API status responses report configuration presence, never secret values.
- `ENTERPRISE_AI_VERIFY_SSL` can be disabled only when explicitly required by the target environment; it should remain enabled for normal use.

## Current limitations

- Workflow state is held only in the response and is not persisted.
- The workflow endpoint is one blocking call, so the Streamlit UI reports the final stage statuses after the call returns rather than polling live agent progress.
- Excel export, human approval, conditional and parallel execution, quality scoring, and durable execution history are future phases.
- Live connectivity has not been claimed or tested because no enterprise credentials are included in this repository.
