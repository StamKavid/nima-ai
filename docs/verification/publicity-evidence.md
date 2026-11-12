# Offline manual Publicity evidence verification

Date: 2026-11-12. Approved contract: docs/sources/gemi-publicity-fallback.md;
approved implementation plan: tasks/plan.md. Delivery uses the private repository
and StamKavid attribution. No provider request or production deployment.

## Implemented boundary

- Strict bounded UTF-8 JSON claims for 1–10 selected registry numbers/files, using
  existing GEMI number rules. Original supplied values remain available; canonical
  numbers and UTC capture dates are explicitly derived from operator claims.
- Offline PDF/PNG/JPEG intake checks signatures and copies exact original bytes
  into a distinct private manual-evidence archive. No renderer, parser, OCR, LLM,
  HTML, session-state importer or source fetch is exposed.
- POSIX no-follow directory/file descriptors, owner-only roots/artifacts, bounded
  regular-file reads, SHA-256 objects and an immutable completion manifest.
  Cooperative writers serialize through an archive-directory advisory lock.
- Existing completed bundles verify before replay writes. Conflicting content,
  corrupt bodies/metadata, missing blobs and changed Git exclusions fail visibly.
  New requests cannot silently repair damaged shared archive metadata.
- Redacted CLI outcomes explicitly deny verified origin/identity/capture context
  and completed extraction. Verifier reads no input files and does not repair data.
  Existing API and manual verifiers reject each other's archive formats.

## Measured checks

- Focused tests: **90 passed**. Covers invalid/duplicate metadata, credentials in
  URLs, unsupported formats, timestamp overflow, symlinks/FIFOs/path traversal,
  unsafe archive permissions, original image bytes and actual aggregate limits.
- Real subprocesses were SIGKILLed immediately before and after completed-manifest
  publication. Before publication no completed bundle exists; after publication
  it is verifiable. Same-request replay preserves the first accepted manifest.
- Competing identical/conflicting submissions use real filesystem/advisory-lock
  operations. Input mutation during an actual descriptor read is rejected.
- A fresh Python process installs a socket audit guard before importing the CLI;
  module startup and intake succeed without socket operations. In-process guards
  also forbid DNS, socket connections and database connections during both commands.
- Mutation: replaced the verifier's SHA-256 recomputation with the supplied digest.
  The same-size corruption regression failed. Original source was restored
  byte-for-byte; final normal-source checks are required below.
- Final local `just check`: **576 passed**, **93.03%** combined line/branch
  coverage, clean build/lint/types/skills/Bandit/secrets. `just audit` reported
  no known dependency advisories. Runtime/test revision: `f309961`; subsequent
  delivery-documentation changes do not alter the tested implementation.
- Both module commands also completed against an external-to-Git synthetic
  capture/archive: intake reported `staged`, then independent verification reported
  `verified`, with identity/origin/capture-context flags remaining false.

Final-head hosted quality and Compose results belong in the delivery PRs. A local
test or push is not evidence that hosted CI passed. Human merges only.

## Review and limits

Correctness: content hashes, bounded metadata, strict reconciliation and real
interruption/replay tests; integrity does not authenticate a supplied document.
Readability: small evidence modules, fixed failure codes and a separate CLI parser
that avoids echoing invalid user values. Architecture: no API archive reuse,
database/schema/dependency/CI changes or identity decisions. Security: private
descriptor-based local storage, no rendering or source traffic, no session export
support. Performance: bounded cohort/metadata/files, one body at a time, serial
archive publication; replay/verification have no source-request cost.

Local application immutability and read-only hash verification are not WORM storage,
signed provenance, independent origin verification or evidence of the IP used for
manual acquisition. A malicious process with the same user privileges can ignore
advisory locks or replace both evidence and its manifest. Power-loss durability,
network filesystems, real-provider payloads and live identity accuracy are untested.
Input documents remain opaque: selecting appropriate public files is an operator
responsibility; their contents are not inspected or redacted by this importer.

Remote browsing, packet-level egress/leak checks, proxy failure isolation, permitted
UI automation, source-field extraction, SQL import and graph integration remain
separate milestones. No privacy-infrastructure deployment is claimed here.
