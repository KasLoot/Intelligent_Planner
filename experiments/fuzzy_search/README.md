# Fuzzy Search Design

This experiment is intentionally non-invasive: it does not modify `agent.py`, `tools.py`, `configs/*`, or frontend source files.

It implements the fuzzy alignment layer described in `README1.md`:

1. Parse a fuzzy user phrase into bounded candidates.
2. Search local structured data instead of inventing facts.
3. Use context only when there is enough evidence to correct an apparently exact user mention.
4. Return machine-readable observations that an Agent can use in later timeline planning.

## Search Targets

The prototype indexes:

- Cities and airports from `database/transport/iata_codes.json`
- POIs from `frontend/frontend/src/data/poi_database.json`

## Matching Strategy

Each candidate has:

- `kind`: `city`, `airport`, or `poi`
- `id`: stable id, such as `city:Paris`, `airport:CDG`, or `poi:RB004`
- `label`: display name
- `aliases`: alternate strings, including IATA code, city name, Chinese city aliases, POI tags, and category words
- `metadata`: source fields used by later tools

The score combines:

- Exact alias match
- Substring match
- `difflib.SequenceMatcher` similarity
- Character bigram overlap
- Context boosts for recent destinations, itinerary cities, preferred district, and preferred categories

## Correction Policy

The prototype distinguishes three outcomes:

- `matched`: a clear best candidate.
- `ambiguous`: several candidates are too close; the Agent should ask a clarifying question or show options.
- `context_override`: the literal user mention points to one place, but strong context points to another.
- `no_match`: no bounded candidate is good enough.

For strong correction, the context candidate must have at least two independent evidence hits and must beat the literal candidate by a configurable margin.

This is the guardrail behind the README1 example: correcting "巴黎" to another city should not happen just because another city exists. It needs strong, explicit context.

## Debug

Run from the repo root:

```powershell
python experiments\fuzzy_search\fuzzy_search.py --debug
```

The script writes:

```text
experiments/fuzzy_search/debug_output.json
```

