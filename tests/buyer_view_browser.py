"""Explicit offline browser proof; run in an isolated network namespace, not pytest.

Uses the existing pinned Playwright dependency and installed sandboxed Chromium.
The manifest must name the fictional paired, empty and hostile-label fixtures.
"""

import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Error, Page, sync_playwright


def _payload(body: str) -> dict[str, Any]:
    match = re.search(r'<script id="view-data" type="application/json">(.*?)</script>', body, re.S)
    assert match is not None
    return dict(json.loads(match[1]))


def _download(page: Page, selector: str, payload: dict[str, Any], output: Path) -> None:
    button = page.locator(selector).first
    digest = button.get_attribute("data-download")
    assert digest is not None
    with page.expect_download() as pending:
        button.click()
    saved = output / pending.value.suggested_filename
    pending.value.save_as(saved)
    expected = base64.b64decode(payload["downloads"][digest]["base64"])
    assert saved.read_bytes() == expected
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == digest


def run(manifest_path: Path, output: Path) -> None:
    assert not Path("/proc/net/route").read_text().splitlines()[1:], (
        "External network route present"
    )
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.environ["XDG_CONFIG_HOME"] = str(output / "browser-config")
    os.environ["XDG_CACHE_HOME"] = str(output / "browser-cache")
    manifest = json.loads(manifest_path.read_bytes())
    documents = {}
    for name in ("paired", "empty", "hostile"):
        row = manifest[name]
        body = Path(row["path"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == row["sha256"]
        assert all(
            "Fictional" in e["label"] or "Ελληνικά" in e["label"]
            for e in _payload(body.decode())["manifest"]["entries"]
        )
        documents[name] = body.decode()
    errors: list[str] = []
    requests: list[str] = []
    with sync_playwright() as engine:
        browser = engine.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            chromium_sandbox=True,
            args=[
                "--disable-setuid-sandbox",
                "--disable-background-networking",
                "--disable-component-update",
                "--no-first-run",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000}, accept_downloads=True
        )
        probe = context.new_page()
        probe.goto("chrome://sandbox")
        sandbox = probe.locator("body").inner_text()
        assert re.search(r"Seccomp-BPF sandbox\s+Yes", sandbox, re.I)
        probe.close()
        probe = context.new_page()
        try:
            probe.goto(Path(manifest["paired"]["path"]).as_uri(), timeout=10000)
            file_navigation = probe.title() == "Nima · Buyer evidence"
        except Error:
            file_navigation = False
        probe.close()
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.set_content(documents["paired"])
        payload = _payload(documents["paired"])
        assert page.title() == "Nima · Buyer evidence"
        assert page.locator("#e0").is_visible() and not page.locator("#e1").is_visible()
        assert page.locator("#e0 td.draft-share").all_text_contents() == ["2/3", "2/3"]
        assert page.locator("#e0 .tie-note").count() == 2
        page.locator("h1").scroll_into_view_if_needed()
        page.screenshot(path=str(output / "desktop.png"), full_page=False)
        page.locator("#cohort-select").select_option("e1")
        assert not page.locator("#e0").is_visible() and page.locator("#e1").is_visible()
        assert "data_limited" in page.locator("#e1 .reason-list").inner_text()
        page.locator("#cohort-select").focus()
        page.keyboard.press("Home")
        page.keyboard.press("Enter")
        assert page.locator("#e0").is_visible()
        first = page.locator("#e0 .supplier summary").first
        first.focus()
        page.keyboard.press("Enter")
        large = "900719925474099312345"
        page.get_by_role("link", name="kimdis:" + large, exact=True).click()
        assert page.locator("#e0-r0").evaluate("(e) => e.open")
        original = page.locator("#e0-r0 button[data-original]").first
        digest = original.get_attribute("data-original")
        assert digest is not None
        original.click()
        exact = base64.b64decode(payload["downloads"][digest]["base64"])
        assert page.locator("#original-text").evaluate("(e) => e.textContent") == exact.decode()
        assert "123456789012345678901234567890" in page.locator("#original-text").inner_text()
        assert page.locator("img").count() == 0
        _download(page, "#e0-r0 button[data-download]", payload, output)
        page.locator("#close-original").click()
        for button in ("Exact readout", "Data assessment", "Insight decision"):
            selector = f'#e0 button[data-download]:text-is("{button}")'
            _download(page, selector, payload, output)
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("h1").scroll_into_view_if_needed()
        assert page.locator("body").evaluate("(e) => e.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(output / "mobile.png"), full_page=False)
        page.close()
        for name in ("empty", "hostile"):
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request.url))
            page.set_content(documents[name])
            assert page.locator("img").count() == 0
            if name == "empty":
                assert page.locator(".supplier").count() == 0
                assert "No captured buyer publications" in page.locator("body").inner_text()
            else:
                assert "</script><img" in page.locator("#e0 h2").first.inner_text()
            page.close()
        tampered = context.new_page()
        tampered.set_content(
            documents["paired"].replace(
                '<script id="view-script">',
                '<script id="view-script">window.untrustedAssetExecuted = true;',
            )
        )
        assert tampered.evaluate("typeof window.untrustedAssetExecuted") == "undefined"
        tampered.close()
        assert not errors, errors
        assert not [url for url in requests if url.startswith(("http:", "https:", "ws:", "wss:"))]
        proof = {
            "browser": browser.version,
            "sandbox": sandbox,
            "external_routes": False,
            "file_uri_navigation": file_navigation,
            "runtime_method": "set_content of exact verified artifact",
            "keyboard_mobile_flow": True,
            "exact_downloads": 4,
            "all_ties": True,
            "empty_limited_hostile_states": True,
            "csp_asset_tamper_blocked": True,
            "javascript_errors": errors,
            "external_page_requests": 0,
            "human_observation": False,
        }
        (output / "browser-proof.private.json").write_text(json.dumps(proof, indent=2) + "\n")
        browser.close()
    print(
        "Offline keyboard/mobile/evidence downloads, hostile text and CSP tamper refusal verified."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    run(arguments.manifest, arguments.output)
