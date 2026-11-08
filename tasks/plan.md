# Delivery plan

## Current increment: engineering-foundation

The user requested the Agent Skills collection, a software engineering delivery
workflow, and a private Git repository. Complete the local foundation while
GitHub authentication is pending. Preserve upstream skills and their license;
use a pinned snapshot and repeatable verification. Keep all data-source
implementation work in a subsequent reviewed increment.

## Ordered increments

1. Install the complete skill snapshot and record provenance.
2. Establish locked Python tooling and behavioral tests for snapshot integrity.
3. Add CI, security checks, review conventions, and architectural context.
4. Create and verify the private GitHub remote, push the reviewed bootstrap, and
   enable host-supported branch controls.
5. Save the initial ingestion spec for review before implementation planning.

The task state is in `tasks/todo.md`. Remote controls and hosted CI cannot be
marked complete from local evidence alone.

## Risks

| Risk | Handling |
|---|---|
| GitHub credential fails | Continue local work; use the authorized GitHub integration once connected |
| A skill update changes operating rules | Pin the source revision, preserve full references, and review updates separately |
| Bootstrap checks look like product validation | State exactly which behavior is tested; ingestion has its own acceptance criteria |
| Private repository plan lacks branch rules | Verify support and report limitations; never claim protection from configuration alone |

## Next feature

Review `SPEC-source-ingestion.md`, then create its implementation plan and small
tasks. The roadmap is KIMDIS metadata → document evidence → Diavgeia linking →
GEMI enrichment. Do not introduce model dependencies into the collection path.
