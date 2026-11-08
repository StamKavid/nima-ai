# Contributing

## Local setup

```bash
make setup
make check
make audit
git switch -c feature/short-description
```

The bundled secret-scanner installer supports Linux x86_64. On another platform,
install Gitleaks 8.30.1 through its official distribution and run checks with
`make GITLEAKS=/path/to/gitleaks check`.

## Delivery

1. Review the capability map and active task list.
2. Write or update a bounded spec with acceptance criteria. Follow the installed
   spec skill's review gates for a new feature; the approved research direction
   does not automatically approve every implementation detail.
3. Break the feature into vertical slices, each with an observable outcome and
   explicit verification. Keep task dependencies visible.
4. Write a failing behavioral test, implement the smallest useful slice, and
   verify its failure paths. Configuration and prose do not need cosmetic tests.
5. Run local checks, review the staged diff, and make a focused conventional commit.
6. Open a pull request. Describe behavior, validation evidence, limitations, and
   rollback. Resolve material review findings and obtain authorization to merge.
7. Release only after staging validation and a documented rollback. Release
   automation is introduced with the first deployable service.

Use synthetic or anonymized fixtures with source provenance. Live government
APIs are opt-in smoke tests; they must not make ordinary CI depend on government
uptime. Raw source archives and investigation data stay outside Git.

## Dependencies and skill updates

Update one dependency or related group at a time. Read release notes, review
the lockfile diff, and run checks. Keep third-party skill updates separate from
application changes and retain the MIT notice and provenance.
