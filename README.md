# Nima AI

Nima helps journalists, investigators, and researchers trace Greek company
relationships and public spending, then develop evidence-backed investigative
leads. Its mission is to make relationships, spending patterns, and changes over
time inspectable and reproducible.

The product combines a temporal relationship graph, sector comparisons,
explainable statistical/ML detectors, and AI-assisted research with citations.
Current code implements the engineering foundation and KIMDIS contract
normalization. Collection, durable storage, entity resolution, graph projection,
trained models, and the investigation workspace are subsequent milestones.
An investigative signal is not a finding of wrongdoing.

## Investigator questions

- Which buyers repeatedly award work to this company, and how does it compare
  with similar suppliers in the same sector, region, and period?
- Which source-supported directors, shareholders, or corporate changes connect
  companies during the period being investigated?
- Which repeated awards, amendments, prices, or bidding patterns deserve review,
  given the data actually available?
- Which documents support a lead, what changed, and what evidence is missing?

The practical deliverable is a reviewable case with an evidence trail. Read the
[architecture and model strategy](docs/architecture.md) for the stages and gates.

## Development

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
make setup
make check
make audit
```

`make check` verifies the installed skills, formatting, lint, types, behavioral
tests, package build, and source security. `make audit` checks locked third-party Python dependencies against
the Python Packaging Advisory Database. The unpublished project is checked
by first-party tests and static analysis rather than a public package database.
These checks cover bootstrap tooling and contract normalization; they do not
prove complete collection, crash recovery, or model quality.

## First data-contract slice

`nima.sources.kimdis.normalize_contract` accepts original JSON response bytes and
a record index. It preserves exact Decimal amounts, reported supplier
participation, missing data, cancellation state, and raw source timestamps. It
returns a SHA-256 response reference and a record JSON pointer. Currency remains
unknown when reported line-item currencies are missing or mixed.

The function performs no network call, database write, graph inference, or ML
prediction. It does not allocate a joint contract's full value to each supplier.
The next collection milestone is specified in
[SPEC-source-ingestion.md](SPEC-source-ingestion.md).

## Delivery workflow

Specification → small tasks → failing behavioral tests → implementation → local
checks → pull request → review → merge → staged release.

Read [AGENTS.md](AGENTS.md), [CONSTRAINTS.md](CONSTRAINTS.md), and
[CONTRIBUTING.md](CONTRIBUTING.md). The capability map is in
[CAPABILITIES.md](CAPABILITIES.md); task state lives in [tasks/todo.md](tasks/todo.md).

The remote is [StamKavid/nima-ai](https://github.com/StamKavid/nima-ai).
Preserve private visibility. A draft PR is a review checkpoint, not authorization
to merge or deploy.

## Installed skills

All 25 skills from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
are installed project-locally in `.agents/skills/`. Shared references, supporting
documents, and the MIT license are preserved. `.agents/skills.lock.json` records
the upstream revision and file hashes. `make skills-check` detects local drift;
it is an integrity check against the recorded snapshot, not signature verification.

Codex discovers project-local skills when a session starts in this repository.
In an existing session, read the relevant `SKILL.md` directly. Installation does
not add slash commands or register a global plugin.

## Data and privacy

Keep original JSON, PDFs, databases, credentials, and investigation workspaces
outside Git. `data/`, `work/`, and local environment files are ignored. Repository
privacy must be confirmed at the remote host; a local Git repository has no
public/private hosting setting.
