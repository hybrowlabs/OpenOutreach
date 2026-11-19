# Running the fork for a pilot (find-only)

This is what the Growth squad needs to run a pilot (GROW-310). It finds and qualifies leads and
**sends nothing**: no mailbox is asked for or contacted.

## 1. Install

The fork depends on the Hybrowlabs OpenOutFind, pinned in `pyproject.toml`.

    uv tool install "git+https://github.com/hybrowlabs/OpenOutreach@ops-636-lead-ocean-dataset"

(or `uv pip install -e ".[dev]"` inside a checkout).

## 2. Configure — environment only

Put these in the environment (or a unit file). Do not commit them.

| Variable | Needed | Meaning |
|:--|:--|:--|
| `OPENOUTFIND_AI_MODEL` | yes | `provider:model` that judges leads, e.g. `anthropic:claude-sonnet-4-5-20250929` |
| `OPENOUTFIND_LLM_API_KEY` | yes | key for that model |
| `OPENOUTFIND_PRODUCT_DOCS` / `OPENOUTFIND_CAMPAIGN_TARGET` | yes | what you sell, and to whom (or `openoutreach init --product-docs F --target F`) |
| `OPENOUTFIND_DATASET_PATH` | one source | path to the dataset file (below) |
| `OPENOUTFIND_LEADOCEAN_API_KEY` + `OPENOUTFIND_LEADOCEAN_BASE_URL` | one source | Lead Ocean key (sent as `x-api-key`) and API base URL, e.g. `https://api.leadocean.io` |
| `OPENOUTFIND_BETTERCONTACT_API_KEY` | one source | BetterContact key: Lead Finder discovery is free |
| `OPENOUTFIND_DISCOVERY_PROVIDER` | no | sources joined with `+`: `dataset`, `leadocean`, `leadfinder`. Default `dataset+leadocean+leadfinder` |
| `OPENOUTREACH_ALLOW_SEND` | no — **leave unset** | sending is off unless this is `1` |

Any one source is enough on its own. With several, the dataset is read first, then Lead Ocean,
then Lead Finder, as one stream: a later source supplies the pages the earlier ones cannot fill.

**Lead Ocean costs records.** Each person a search page returns counts as one record against the
account's monthly allowance. Counting is free. There is no spend cap in this fork, so size the
search first (the walk does this itself before it buys a page) and keep the first pilot small.
A search Lead Ocean cannot answer faithfully (a filter it would drop, a seniority or country it has
no value for) buys nobody and is logged as a warning.

The upstream contacts hub is not used unless `bettercontact` is the only source selected.

## 3. The dataset file

One row per person, UTF-8, `.csv` (header row) or `.jsonl`.

- Required: `linkedin_url` (the person's unique id), `full_name`, `job_title`, `company_name`
- Optional: `headline`, `seniority`, `industry`, `company_domain`, `company_keywords`
  (`;`-separated in CSV, a list in JSONL), `company_industry`, `city`, `state`, `country`,
  `employees_min`, `employees_max`

A missing `headline` is written as `"<job_title> at <company_name>"`. A row without a
`linkedin_url` is skipped; a repeated one keeps its first row. The file is checked before the first
round, and a missing file or column stops the run with `bad_config` naming it.

## 4. Run (dry run — the only mode the pilot needs)

    openoutreach find 10 > leads.csv      # ten qualified leads as CSV; nothing is sent
    openoutreach run 10                   # same, with onboarding; nothing is sent
    openoutreach status                   # what is configured, blocked and counted

**Do not use the `emails` unit in the pilot** unless Growth accepts the cost: `find N emails` sends each lead's LinkedIn URL (Lead Ocean and dataset people alike) to BetterContact to resolve a work email. It needs BetterContact's key, spends credits, and still sends no email.

## 5. Sending (not for the pilot)

Two deliberate acts are needed: `OPENOUTREACH_ALLOW_SEND=1` in the environment, and `--send` on
`run` (the `send` verb needs the environment variable). Sending also asks for a mailbox.
