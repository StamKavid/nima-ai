# Hellenic Integrity

An investigation platform for Greek company relationships and public spending,
intended for journalists, independent investigators, and researchers.

The repository currently contains the engineering foundation and delivery
workflow. Source ingestion, entity resolution, graph analytics, and the user
interface are planned capabilities. An investigative signal is not a finding of
wrongdoing.

## Development

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
make setup
make check
make audit
```

`make check` verifies the installed skills, formatting, lint, types, tests, and
package build. `make audit` checks locked third-party Python dependencies against
the Python Packaging Advisory Database. The unpublished project is checked
by first-party tests and static analysis rather than a public package database.
These are bootstrap checks; they do not yet
validate government-source ingestion.

## Delivery workflow

Specification → small tasks → failing behavioral tests → implementation → local
checks → pull request → review → merge → staged release.

Read [AGENTS.md](AGENTS.md), [CONSTRAINTS.md](CONSTRAINTS.md), and
[CONTRIBUTING.md](CONTRIBUTING.md). The capability map is in
[CAPABILITIES.md](CAPABILITIES.md); task state lives in [tasks/todo.md](tasks/todo.md).

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
