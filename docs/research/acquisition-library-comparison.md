# Acquisition library comparison

Measured 2026-11-16; direction accepted in [ADR-0004](../decisions/0004-bounded-http-and-browser-acquisition.md).
No application dependency, source contract, deployment or CI configuration changed.

## Method and scope

The accepted dataset contains 51 subprocess trials: 27 acquisition trials,
15 parser trials and nine expected dead-proxy failures; 1,530 timed samples total.
Three rounds used deterministic shuffled candidate order and concurrency one.
The shared Linux worker ran Python 3.12.14, Chromium 156.0.8078.79, ChromeDriver
156.0.8078.80 and Node 24.22.1. All browser candidates used the same system Chromium,
not the repository's pinned Chromium 158 Docker fixture.

Each synthetic Greek profile has five required string fields, including a
leading-zero AFM, plus 2,000 filler rows. The JavaScript page waits 80 ms before
fetching/rendering JSON. All exact values must match; wrong-company and missing-AFM
fixtures must fail a common adapter assertion. This is not built-in library
identity verification or an implemented product quarantine workflow.

Acquisition ran through a local allowlisting proxy in a loopback-only network
namespace with no external route. No government/source requests occurred.
Normal trials matched origin deliveries to proxy forwards, rejected an untrusted
self-signed certificate and reported Chromium namespace/seccomp sandbox active.
A separately trusted TLS control proved the endpoint healthy. All nine dead-proxy
trials failed with zero origin deliveries; those nonzero exits are expected.

## Results

Warm navigation/request through exact extraction; 45 samples per scenario.
Cells show median / nearest-rank p95 milliseconds.

| Configuration | Static | JavaScript |
|---|---:|---:|
| Playwright 1.65.1 | 118.00 / 163.42 | 189.90 / 231.81 |
| Selenium 4.52.0 | 91.16 / 111.28 | 163.37 / 176.57 |
| SeleniumBase 4.58.0, evaluation hardening | 89.22 / 134.45 | 162.71 / 185.94 |
| Crawlee Python 1.11.2 + Playwright | 125.22 / 165.82 | 193.90 / 215.30 |
| Scrapling 0.5.1 browser, hardened, solver off | 132.50 / 172.12 | 210.49 / 250.94 |
| HTTPX 0.28.1 + lxml | 4.01 / 6.79 | Incomplete initial HTML |
| Requests 2.34.2 + lxml | 4.25 / 6.22 | Incomplete initial HTML |
| Scrapling 0.5.1 HTTP + lxml | 5.61 / 10.17 | Incomplete initial HTML |
| Scrapy 2.20.0 + lxml | 7.24 / 10.54 | Incomplete initial HTML |

Parser-only, identical retained HTML; 180 samples per parser:

| Parser | Median ms | p95 ms |
|---|---:|---:|
| lxml 6.1.3 | 2.59 | 2.88 |
| Scrapling 0.5.1 Selector | 2.64 | 3.21 |
| BeautifulSoup 4.15.0 with lxml | 51.20 | 79.32 |
| BeautifulSoup 4.15.0 with html.parser | 71.61 | 110.70 |
| Cheerio 1.2.0 | 7.26 | 34.72 |

## Interpretation and configuration

Selenium was faster on this fixture; HTTPX/Requests and lxml/Scrapling Selector
were close. Browser waiting/polling and page lifecycle differ: Playwright/Selenium
reuse a page; Scrapling's fetch creates/parses a page/response; Crawlee uses its
browser pool. Crawlee samples exclude queue/page lifecycle overhead. Scrapy
samples cover downloader middleware through callback, excluding queue/startup.
Scrapling HTTP includes its built-in response parsing before common lxml extraction.
These are adapter configurations, not equalized engine measurements. Warm samples
exclude launch/imports; parser samples exclude network. GC remained enabled; the
machine had no CPU affinity/exclusive cores. Pooled median/p95 are descriptive,
not production SLOs or significance tests.

Scrapling 0.5.1 uses StealthySession, not the older DynamicFetcher API. The measured
session overrides certificate-ignore/browser-sandbox defaults; challenge solving,
Google referrer, proxy rotation and DoH are off. Patchright 1.64.4 remains its
browser backend. Adaptive parsing is disabled. SeleniumBase measurements use an
evaluation-only ChromeOptions adapter removing no-sandbox, certificate-ignore,
web-security-disable and insecure-localhost/content flags, with
acceptInsecureCerts=False. This is not stock SeleniumBase or a supported production
hardening recipe. Scrapy explicitly enables DOWNLOAD_VERIFY_CERTIFICATES=True;
its default is false. Crawlee disables fingerprint generation, retry-on-block and
session pooling; its explicit browser sandbox/TLS settings remain on.

No concurrency/HTTP2, malformed-document recovery, source access-policy compliance,
live Publicity workflow or distributed crawling benchmark was run. The local proxy
is not Nima's Envoy/kernel test matrix; missing/invalid proxy auth, removal/bypass,
DNS/IPv6/UDP/WebRTC leaks and a running gateway outage still require the separate
remote boundary experiment. No source-facing worker/proxy/VPN exists yet.

## Reproducibility and sources

The operator retains `nima-scraping-evaluation.zip` outside Git: 126,728 bytes,
SHA-256 `e9bad65a995762732601652aec1f79f13ec8c63ce7b8340d28e6e8bea6187446`.
It contains the synthetic fixtures/harness, package-version lists, npm lockfile,
all accepted per-trial logs/JSON, samples.csv, summary/validation JSON and a file
hash manifest. No environments, executable browsers, generated fixture private key,
source credentials or real-company evidence are included. It was supplied with
the comparison; this repository records the reviewed summary, not the raw bundle.
Scrapy's accepted subset uses the current TLS setting after a focused re-run.

Official references, with version-specific defaults also checked in installed source:

- https://www.python-httpx.org/advanced/clients/
- https://playwright.dev/python/docs/network
- https://crawlee.dev/python/docs/introduction
- https://docs.scrapy.org/en/latest/topics/settings.html#download-verify-certificates
- https://seleniumbase.io/help_docs/customizing_test_runs/
- https://github.com/D4Vinci/Scrapling
- https://www.crummy.com/software/BeautifulSoup/bs4/doc/
- https://cheerio.js.org/docs/intro/
