# Intelligent Planner

## Run a Demo
```bash
uv venv -p 3.11.15
source .venv/bin/activate
uv pip install -r requirements.txt

cp .env.example .env
# Set your own credentials in .env, then load them into this shell.
set -a
source .env
set +a

python agent.py
```

`OPENAI_API_KEY` authenticates the agent. `GOOGLE_MAPS_API_KEY` authenticates
Google Maps, Places, Geolocation, Time Zone, and Routes requests. Keep these
credentials on the backend; never put them in frontend `VITE_` variables.

## Local output

Agent runs create `agent_debug_trace.json`, `full_api_response.json`, and
`output.json`. These files can contain user messages, travel plans, precise
locations, and API metadata. They and manual Google API response files are
ignored by Git and should stay local. The tracked transport and POI datasets
are demo data.

Before committing, install [pre-commit](https://pre-commit.com/) and run
`pre-commit install` to enable the configured Gitleaks secret check. Run
`pre-commit run --all-files` to check the current files.
