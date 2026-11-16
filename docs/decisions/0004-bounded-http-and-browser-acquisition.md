# ADR-0004: Use HTTPX and Playwright for bounded acquisition

## Status

Accepted by the owner on 2026-11-16: “Lock that and continue”. This selects the
acquisition direction; it does not adopt another dependency or activate a source.

## Date

2026-11-16

## Context

Publicity is the primary GEMI channel to develop while its API key is pending.
Investigators need original evidence, exact company identifiers, predictable
failure handling and a remote boundary that keeps source traffic away from their
home/office connection. A general crawling framework does not establish that
boundary. The [local comparison](../research/acquisition-library-comparison.md)
measured candidate configurations on synthetic pages, including JavaScript content.

## Decision

Keep locked HTTPX for structured HTTP acquisition/downloads and locked Playwright
for JavaScript UI interaction and response capture. Prefer lxml for deterministic
HTML parsing; BeautifulSoup with lxml is an option where it simplifies extraction.
Parsing dependencies still require a reviewed implementation and lock/audit change;
this ADR adds none. Preserve the current Python 3.12/uv/just toolchain.

Use self-hosted Prefect for pipeline runs and downstream orchestration. Each
acquisition job has bounded work and one owner for retries/rate limits. A future
Crawlee adapter may manage a URL queue/browser pool inside such a job if measured
crawl needs justify it. Do not add a second general pipeline orchestrator.

Archive original responses/documents before extraction; retain request context,
observation time, content hash and source locations. Label rendered DOM/screenshots
separately. Keep identifiers as exact strings, original Greek text and incomplete
fields; adaptive matching cannot silently select another company. PostgreSQL and
the private original-file archive remain authoritative inputs for later graphs.

Publicity development remains primary and the official GEMI API secondary. Both
share source family `gemi`, rate/cooldown policy and reviewed identity semantics.
A block never triggers automatic IP/channel switching. Publicity's recorded
access-policy restriction remains a separate gate to unattended collection.

Use the [approved remote egress scope](../sources/remote-worker-egress-pilot.md)
before source-facing execution. Preserve normal TLS verification, Chromium's
sandbox, an allowlisting gateway and network-enforced denial of direct egress.
Library proxy settings alone do not establish the investigator-IP requirement.

## Alternatives

- **Requests:** mature synchronous client; measured similarly to HTTPX. Existing
  integration plus HTTPX's sync/async APIs favor retaining HTTPX.
- **Selenium:** a strong WebDriver/Grid alternative and faster on the tested UI
  fixture. That result does not outweigh Playwright's existing network capture and
  worker integration; revisit for a concrete compatibility/operational need.
- **Crawlee:** preferred future crawling-framework candidate for a persistent URL
  frontier, browser pooling and session management. Those needs are not yet shown
  for the bounded company pilot. Python was measured; JavaScript was not.
- **Scrapy:** mature Python HTTP crawling engine, useful for broad mostly static
  crawling. JavaScript rendering adds a browser integration.
- **Scrapling:** its selector performed similarly to lxml. Its current browser
  backend/defaults and moving API add review work; the comparison used a hardened
  session with challenge solving off, not an older DynamicFetcher example.
- **SeleniumBase:** useful automation/testing capabilities; the standard Linux
  launcher requires particular sandbox/TLS review. Measured timings used an
  evaluation-only hardening adapter, not a production configuration recommendation.
- **Cheerio:** suitable for Node services; adds an unnecessary runtime to this
  Python acquisition path. It and BeautifulSoup parse markup without executing JS.

## Consequences

The platform keeps a small acquisition surface and can add a crawler through a
reviewed adapter later. Source contracts, evidence completeness and remote egress
need their own tests; local latency does not prove live Publicity compatibility,
entity identity, anonymity or production readiness. No remote worker/proxy/VPN has
been deployed, and no company collector/extractor was completed by this decision.

## Sources

- [Measured configurations and limitations](../research/acquisition-library-comparison.md)
- https://www.python-httpx.org/advanced/clients/
- https://www.python-httpx.org/async/
- https://playwright.dev/python/docs/network
- https://playwright.dev/python/docs/docker
- https://crawlee.dev/python/api/class/PlaywrightCrawler
