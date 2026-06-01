# Intelligent Planner

## Dev Output Inspection:
- full_api_response.json: contains the complete API response from the agent, including all metadata and the final output text.
- output.json: contains only the final output text from the agent, which should be the raw JSON plan options as specified in the instructions.

## Run a Demo
```bash
uv venv -p 3.11.15
source .venv/bin/activate
uv pip install -r requirements.txt

python agent.py
```