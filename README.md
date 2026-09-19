# Urban Agent — Pi-native research workspace

Urban Agent supports reviewable, human-directed urban research. A coordinating
Planner can delegate bounded work to independent Worker/Reviewer sessions.
Research Tree nodes and cards retain research facts, artifacts and human decisions.
Pi owns dialogue history and compaction; Urban does not run a second history summarizer.

This `main` release replaces the previous Hermes application. Previous code remains
recoverable in Git history and in `archive/main-before-pi-20260919`.
Raw mobility records, private manuscripts, credentials, model weights and experimental
conversation logs are deliberately excluded.

## Interactive browser workspace

Requires Node.js 22+, Python 3.11+ and (on Windows) Git Bash for Pi terminal tools.

```powershell
python -m venv .venv-section4
.\.venv-section4\Scripts\python -m pip install -r requirements-gis.txt
Copy-Item .env.example .env
# Configure KIMI_CODE_API_KEY in .env, or in the process environment.
cd pi_urban_agent
npm ci
npm run web
```

Open http://127.0.0.1:8018. This is a live Pi session, not a demonstration transcript.
The browser shows human messages, assistant answers, tool execution events and actual
Research Tree cards. It does not expose private reasoning. Kimi Code is the initial
web provider (`kimi-for-coding`); the research/evaluation runners also support other
configured providers.

Each launch creates a fresh directory under `pi_urban_agent/.local-workspaces/`:
`data/` for user-supplied inputs, `work/` for scripts, `outputs/` for results,
`research/` for Tree state, and `sessions/` for the Pi transcript. No private dataset
is preloaded. The UI displays the exact directory. Place data there and tell the
Agent what it represents. Runtime files and keys are never served as static files.

Environment overrides: `URBAN_WEB_PORT`, `URBAN_WEB_WORKSPACE`, and
`URBAN_PI_PYTHON` (absolute interpreter path; on Linux explicitly set this).
Use a fresh workspace per launch; session-resume UI is not implemented yet.
The server listens only on loopback. Do not expose it publicly. Workspace conventions
are not an OS sandbox: the Agent has local terminal permissions. Review tasks accordingly.

## Architecture

- `src/four-condition-extension.ts`: coordinator and isolated delegation.
- `src/pi-extension.ts`, `src/core/research-store.ts`: shared Tree, cards and decisions.
- `src/tool-catalog-extension.ts`: progressive discovery of research tools.
- `src/shared-environment-extension.ts`: verified environment entry point.
- `scripts/workspace-web.ts`, `web/index.html`: local interactive interface.
- `scripts/long-workflow-session.ts`: reproducible research evaluation runner, **not**
  the web server. Its experiment turn/time/tool limits are not copied into the web launcher.
- `protocols/framework-four-v2/`: evaluation protocol. Private case data must be supplied separately.

## Validation

```powershell
npm run typecheck
npm test
```

`npm ci` applies version-checked compatibility patches to pinned Pi 0.84.2. These
patches handle request/summary budgeting and are shared by comparison conditions.
Tests using private saved traces skip when those traces are absent; synthetic/core
tests are self-contained. Historical analysis scripts may refer to local case paths;
they are research utilities, not required for the interactive application.

This release supplies the framework, not a guarantee of correct scientific results
or a claim that delegation always improves performance. Inspect source data, code
and outputs before accepting a scientific conclusion.
