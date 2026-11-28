"use strict";
(() => {
  const payload = JSON.parse(document.getElementById("view-data").textContent);
  const original = document.getElementById("original-view");
  const bytes = (digest) => Uint8Array.from(atob(payload.downloads[digest].base64), (c) => c.charCodeAt(0));
  document.getElementById("cohort-select").addEventListener("change", (event) => {
    document.querySelectorAll("[data-entry]").forEach((section) => {
      section.hidden = section.id !== event.target.value;
    });
    original.hidden = true;
    document.getElementById(event.target.value).querySelector("h2").focus();
  });
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest("button");
    if (button && button.dataset.download) {
      const digest = button.dataset.download;
      const url = URL.createObjectURL(new Blob([bytes(digest)], {type: "application/octet-stream"}));
      const link = document.createElement("a");
      link.href = url;
      link.download = payload.downloads[digest].filename;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    if (button && button.dataset.original) {
      const digest = button.dataset.original;
      document.getElementById("original-text").textContent = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(bytes(digest));
      document.getElementById("original-pointer").textContent = button.dataset.pointer || "Complete archived response page";
      document.getElementById("original-hash").textContent = "SHA-256: " + digest;
      original.hidden = false;
      original.scrollIntoView({block: "start"});
      document.getElementById("original-heading").focus();
    }
    const link = event.target.closest("a[data-publication]");
    if (link) {
      const record = document.getElementById(link.dataset.publication);
      record.open = true;
      record.querySelector("summary").focus();
    }
  });
  document.getElementById("close-original").addEventListener("click", () => {
    original.hidden = true;
    document.getElementById("cohort-select").focus();
  });
})();
