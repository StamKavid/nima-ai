# Bootstrap verification

Date: 2026-11-08. Verification applies to engineering infrastructure, not to
government-record ingestion or any fraud-detection model.

This historical report predates repository connection and attribution correction.
See `nima-foundation.md` for the subsequent private remote, source-normalization,
hosted CI, and identity verification results.

## Evidence

| Check | Result |
|---|---|
| Native skill metadata | 25 valid skill names and descriptions |
| Skill snapshot | 62 installed upstream files match SHA-256 hashes |
| Initial red test | Test collection failed because the verifier did not exist |
| Behavioral tests | 13 passed; no skipped tests |
| Tool coverage | 96.43% combined line/branch coverage; 90% enforced floor |
| Mutation experiment | Inverting the hash comparison produced 4 failing tests; original source restored byte-for-byte |
| Ruff formatting/lint | Passed |
| Strict mypy | Passed for 4 first-party Python files |
| Build | Wheel and source distribution built successfully |
| Bandit | No findings in first-party Python |
| Gitleaks 8.30.1 | No findings; scanner archive checksum verified and output redacted |
| Dependency audit | No known vulnerabilities found for exported, hash-pinned third-party requirements |
| actionlint 1.7.12 | GitHub Actions workflow validated |
| Workflow permissions | Contents read-only; checkout does not persist Git credentials |

The dependency audit exports the lockfile without the unpublished project. This
keeps its inputs auditable through the public advisory database while retaining
strict failure behavior for dependency collection and advisory-service errors.
The editable project itself is covered by first-party tests and static analysis.

## Review

Self-review covered correctness, readability, architecture, security, and
performance of the bootstrap. The integrity verifier rejects manifest paths
escaping the installation, including through symlinks. The upstream snapshot
is preserved verbatim, including existing Markdown whitespace. Third-party
formatting is outside first-party style checks.

## Remote status

The GitHub integration authenticates as `StamKavid`, but both GraphQL
`createRepository` and REST `POST /user/repos` rejected repository creation with
"Resource not accessible by integration". No private GitHub repository, hosted
Actions run, or branch rule has been verified. A private repository created by
the user and granted to the integration is required to complete remote setup.
