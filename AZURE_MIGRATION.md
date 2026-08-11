# Azure Migration Checklist

This is a checklist, not a completed migration. Nothing in this repo talks to Azure yet - there
are no Azure credentials available in the environment this was prepared in, so no resources have
been created. See CLAUDE.md section 7 for the reasoning behind each item.

## What's already done (code/config prep)

- [x] Output/cache storage goes through `src/storage.py`'s `AnalysisStorage` interface instead of
      scattered hardcoded paths - a future `AzureBlobStorage` class implementing the same methods
      (`paths_for`, `write_json`, `read_json`, `cache_get`, `cache_set`, ...) can replace it with
      no changes to `main.py`/`server.py`.
- [x] `Dockerfile` + `.dockerignore` - runs the existing Flask app in a container.
- [x] `.github/workflows/azure-webapp.yml` - manual-trigger deploy workflow, needs secrets (below).
- [x] Removed the dead `openai` dependency/`OPENAI_API_KEY` (the AI Overview never called it -
      see CLAUDE.md section 1, finding 4) - one less secret to provision.
- [x] `Procfile`/`render.yaml` pinned to `gunicorn --workers 1 --threads 8 --timeout 120` -
      `analysis_status`/`active_analyses` in `server.py` are in-memory and process-local, so this
      constraint has to travel with the app wherever it runs next, including Azure.
- [x] Python version reconciled to 3.11 across `netlify.toml`/`render.yaml`/`runtime.txt`.

## Not yet solved - real blockers if you scale beyond one instance

These are documented, not fixed, because fixing them means picking specific Azure services and
provisioning them, which needs your subscription/credentials:

1. **Local disk output.** `AnalysisStorage` still writes to local disk
   (`fantasy_analysis_output/leagues/<league_id>/<season>/...`). On Azure App Service this
   *works* on a single always-on instance, but is not guaranteed to survive a restart, a deploy
   swap, or scaling to >1 instance. Fix: implement an `AzureBlobStorage` class with the same
   method signatures as `AnalysisStorage` (Azure Blob Storage, one container, blobs keyed by
   `leagues/<league_id>/<season>/...` - same layout, different backend), and swap it in via a
   config flag/env var.
2. **In-memory analysis status/locks.** `server.py`'s `analysis_status`, `active_analyses`, and
   `src/storage.py`'s per-(league,season) locks are process-local Python dicts. Fine on one
   gunicorn worker/one instance; breaks (spurious 404s on `/api/status`, duplicate analysis runs)
   the moment there's more than one instance or worker. Fix: move this state to Azure Table
   Storage, Cosmos DB, or Azure Cache for Redis if you need horizontal scaling.
3. **Long-running background work in a request-handling process.** `/api/analyze` spawns a
   `threading.Thread` that runs the whole analysis pipeline in-process. On App Service (always-on
   instance) this is fine. On Azure Functions or anything that can scale to zero / recycle
   instances between requests, a thread started in one invocation won't survive to be polled by
   a later one. Fix: only move to Functions/Container Apps jobs if you also move to a real queue
   (Azure Queue Storage + a worker, or Durable Functions).

If you're deploying to a single always-on App Service instance (the simplest path), none of the
three above block you - they only matter once you scale out.

## App Service setup (once you have a subscription)

1. Create a Linux App Service (Python 3.11 stack) - Basic or Standard tier if you want it to stay
   warm (Free/Shared tiers sleep, which is a bad fit for something users wait on synchronously).
2. Startup command (Configuration > General settings > Startup Command):
   ```
   gunicorn server:app --workers 1 --threads 8 --timeout 120
   ```
   (Do not raise `--workers` past 1 - see blocker #2 above.)
3. Application settings (Configuration > Application settings) - move these from wherever they
   live today (local `.env`, Render dashboard) into App Service's settings:
   - `FLASK_ENV=production`
   - `PORT` - Azure sets this for you; don't hardcode it (server.py already reads it from env).
4. Deploy via the GitHub Actions workflow (`.github/workflows/azure-webapp.yml`) once you've:
   - Created the App Service and downloaded its publish profile.
   - Added `AZURE_WEBAPP_NAME` and `AZURE_WEBAPP_PUBLISH_PROFILE` as repo secrets.
   - Manually triggered the workflow (Actions tab > "Deploy to Azure App Service" > Run workflow).
5. Restrict CORS (`server.py`'s `CORS(app)` is currently wide-open) to your actual frontend
   origin once you know it - either in `server.py` (`CORS(app, origins=[...])`) or via Azure
   Front Door/APIM if you put one in front of App Service.
6. Add auth/rate limiting in front of `/api/analyze` before exposing this publicly - it's an
   unauthenticated endpoint that triggers real outbound API calls and background work per
   request; Azure API Management or App Service Authentication (Easy Auth) are the standard ways
   to add this without changing application code.

## Data/secrets decisions to make before deploying

- **Storage**: local disk (single instance, simplest) vs. Azure Blob Storage (needed for
  multi-instance or if you want output to survive instance recycling). Pick before writing
  `AzureBlobStorage`.
- **`league_config.json`**: currently committed to this repo with a real Sleeper
  username/league_id (`.gitignore`'s rule for it is commented out). Decide whether to scrub it
  from git history before making the repo/CI pipeline more broadly accessible (e.g. connecting
  GitHub Actions) - it's not a secret Sleeper itself protects, but it is your personal league
  data sitting in a public commit history if this repo is public.
- **Secrets**: there are none required right now (OpenAI was removed as dead weight). If you
  ever add the pluggable LLM narration layer mentioned in CLAUDE.md section 8, that API key
  should go in Azure Key Vault (referenced from App Settings), not a plain App Setting.

## Testing before cutting over from Render/Netlify

1. `docker build -t fantasyfootball . && docker run -p 8000:8000 fantasyfootball`, then run
   through the full flow (pick a season/league, analyze, view results) against `localhost:8000`.
2. Confirm `/api/results` and `/results/<file>` work with `league_id`/`season` query params (the
   season-isolation fix - see CLAUDE.md section 3.2) before assuming parity with Render.
3. Only then point a real domain/DNS at the Azure App Service and retire the Render service.
