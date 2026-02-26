# refua-studio

`refua-studio` is the Refua web control plane for planning and running discovery campaigns.

It provides:

- Mission control UI for planning (`plan`), execution (`run`), and autonomous loops (`run-autonomous` behavior)
- JSON plan editor with validation and direct execution
- Portfolio ranking UI for disease program prioritization
- Clinical trial management UI (trial CRUD, human/simulated enrollment, outcome capture, simulation refresh)
- Animated telemetry widgets for running jobs, managed trials, patient counts, promising leads, and tools online
- Built-in objective/plan/portfolio templates loaded from workspace examples
- Ecosystem health panel with cross-product discovery metadata
- ClawCures-native handoff artifact generation and executable command suggestions
- Promising cures section with full ADMET property maps, assessments, and detailed therapeutic review cards
- Persistent background job history (SQLite)
- Job lifecycle operations (filter, cancel queued jobs, clear finished jobs)
- Runtime/tool introspection with graceful fallback when heavy ML deps are unavailable

This project is designed to reuse existing workspace components:

- `ClawCures` for planning, policy checks, orchestration, and portfolio ranking
- `refua-mcp` for tool execution when runtime dependencies are installed

## Install

```bash
cd path/to/refua-studio
pip install -e .
```

## Run

```bash
refua-studio --host 127.0.0.1 --port 8787 --open-browser
```

Or from source without install:

```bash
cd path/to/refua-studio
PYTHONPATH=src python -m refua_studio --host 127.0.0.1 --port 8787
```

## Podman

Build image:

```bash
cd path/to/refua-studio
podman build -t refua-studio:local -f Containerfile .
```

Run container:

```bash
podman run --rm -p 8787:8787 \
  -e REFUA_CAMPAIGN_OPENCLAW_BASE_URL=http://host.containers.internal:18789 \
  -v "$(pwd)/.refua-studio-data:/data" \
  -v "$(pwd)/..:/workspace:ro" \
  refua-studio:local
```

Notes:

- The container starts `refua-studio` on `0.0.0.0:8787`.
- Mount the monorepo root at `/workspace` so Studio can integrate with `ClawCures`, `refua-mcp`, and other sibling projects.
- Persistent job database lives in `.refua-studio-data/`.

## Podman Compose

From `refua-studio/`:

```bash
podman compose -f docker-compose.yml up --build
```

Then open `http://127.0.0.1:8787`.

## Configuration

Studio uses the same OpenClaw-related environment variables as `ClawCures`:

- `REFUA_CAMPAIGN_OPENCLAW_BASE_URL` (default: `http://127.0.0.1:18789`)
- `REFUA_CAMPAIGN_OPENCLAW_MODEL` (default: `openclaw:main`)
- `REFUA_CAMPAIGN_TIMEOUT_SECONDS` (default: `180`)
- `OPENCLAW_GATEWAY_TOKEN` or `REFUA_CAMPAIGN_OPENCLAW_TOKEN`

CLI flags:

- `--host`
- `--port`
- `--data-dir` (default: `.refua-studio`)
- `--workspace-root` (defaults to parent workspace)
- `--max-workers` (background job concurrency)

## API Endpoints

- `GET /api/health`
- `GET /api/config`
- `GET /api/tools`
- `GET /api/examples`
- `GET /api/ecosystem`
- `GET /api/drug-portfolio?min_score=50&limit=60`
- `GET /api/promising-cures?min_score=50&limit=60`
- `GET /api/clinical/trials`
- `GET /api/clinical/trials/{trial_id}`
- `GET /api/jobs?limit=80&status=running,failed`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `POST /api/jobs/clear`
- `POST /api/plan`
- `POST /api/run`
- `POST /api/plan/validate`
- `POST /api/plan/execute`
- `POST /api/portfolio/rank`
- `POST /api/clawcures/handoff`
- `POST /api/clinical/trials/add`
- `POST /api/clinical/trials/update`
- `POST /api/clinical/trials/remove`
- `POST /api/clinical/trials/enroll`
- `POST /api/clinical/trials/enroll-simulated`
- `POST /api/clinical/trials/result`
- `POST /api/clinical/trials/simulate`

### `POST /api/run` payload

```json
{
  "objective": "Design an initial campaign against KRAS G12D",
  "system_prompt": null,
  "dry_run": false,
  "async_mode": true,
  "autonomous": false,
  "max_rounds": 3,
  "max_calls": 10,
  "allow_skip_validate_first": false,
  "plan": null
}
```

### `POST /api/clawcures/handoff` payload

```json
{
  "objective": "Design an initial campaign against KRAS G12D",
  "system_prompt": null,
  "plan": {"calls": []},
  "autonomous": false,
  "dry_run": true,
  "max_calls": 10,
  "allow_skip_validate_first": false,
  "write_file": true,
  "artifact_name": "kras_handoff.json"
}
```

Returns a normalized handoff artifact plus ready-to-run `ClawCures` CLI commands.

### `POST /api/clinical/trials/add` payload

```json
{
  "trial_id": "studio-clinical-demo",
  "status": "planned",
  "config": null
}
```

### `POST /api/clinical/trials/enroll` payload

```json
{
  "trial_id": "studio-clinical-demo",
  "patient_id": "human-001",
  "source": "human",
  "arm_id": "control",
  "demographics": {"age": 62, "weight": 76},
  "baseline": {"endpoint_value": 48.1},
  "metadata": {"site_id": "site-01"}
}
```

### `POST /api/clinical/trials/simulate` payload

```json
{
  "trial_id": "studio-clinical-demo",
  "replicates": 8,
  "seed": 7,
  "async_mode": true
}
```

## Background Jobs

Jobs are persisted in SQLite at:

- `<data-dir>/studio.db`

Each job records request payload, status transitions (`queued` -> `running` -> `completed`/`failed`), result JSON, and error text.
`cancelled` is also tracked when queued jobs are cancelled before execution.

## Runtime Behavior

- If `refua-mcp` runtime dependencies are available, Studio executes plans through `RefuaMcpAdapter`.
- If unavailable, Studio falls back to a static tool list for planning/validation and emits warnings.
- Dry-run workflows and policy validation remain usable even without heavy runtime dependencies.
- Clinical trial endpoints require the scientific stack shipped in package dependencies (`numpy`, `pandas`, `scipy`, `pyyaml`) and workspace access to sibling repos for bridge integrations.

## Tests

```bash
cd path/to/refua-studio
python -m unittest discover -s tests -v
```

## Build

```bash
cd path/to/refua-studio
python -m build
```

Build artifacts are written to `dist/` (`.tar.gz` and `.whl`).

## Project Layout

```text
refua-studio/
  Containerfile
  docker-compose.yml
  src/refua_studio/
    app.py
    bridge.py
    cli.py
    config.py
    runner.py
    storage.py
    static/
      index.html
      app.js
      styles.css
  tests/
```

## Notes

- The Studio UI is a static single-page app served by the Python server.
- No third-party web framework is required.
- Studio now includes scientific dependencies to support embedded clinical operations alongside campaign orchestration.
