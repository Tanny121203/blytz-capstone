/**
 * Shared payment channel details + proof size helpers.
 */
(function (global) {
  "use strict";

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function copyText(text, button) {
    const value = text || "";
    const done = function () {
      if (!button) return;
      const prev = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(function () {
        button.textContent = prev || "Copy";
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done).catch(function () {
        fallbackCopy(value, done);
      });
    } else {
      fallbackCopy(value, done);
    }
  }

  function fallbackCopy(value, done) {
    const ta = document.createElement("textarea");
    ta.value = value;
    ta.setAttribute("readonly", "");
    ta.style.position = "absolute";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      done();
    } catch (err) {
      /* ignore */
    }
    document.body.removeChild(ta);
  }

  function renderChannelDetails(container, optionEl) {
    if (!container) return;
    if (!optionEl) {
      container.innerHTML = "";
      return;
    }
    const name = optionEl.dataset.accountName || "";
    const number = optionEl.dataset.accountNumber || "";
    const qr = optionEl.dataset.qrUrl || "";
    const instructions = optionEl.dataset.instructions || "";

    container.innerHTML =
      '<dl class="mt-3 space-y-3 text-sm">' +
      '<div>' +
      '<dt class="text-ink-subtle">Account name</dt>' +
      '<dd class="mt-1 flex flex-wrap items-center gap-2">' +
      '<span class="font-medium text-ink break-all" data-copy-value>' +
      escapeHtml(name) +
      "</span>" +
      '<button type="button" class="inline-flex min-h-11 min-w-[4.5rem] items-center justify-center rounded-md border border-border-strong bg-canvas px-3 py-2 text-sm font-medium text-ink hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink" data-copy-btn>Copy</button>' +
      "</dd></div>" +
      '<div>' +
      '<dt class="text-ink-subtle">Account number</dt>' +
      '<dd class="mt-1 flex flex-wrap items-center gap-2">' +
      '<span class="font-mono text-ink break-all" data-copy-value>' +
      escapeHtml(number) +
      "</span>" +
      '<button type="button" class="inline-flex min-h-11 min-w-[4.5rem] items-center justify-center rounded-md border border-border-strong bg-canvas px-3 py-2 text-sm font-medium text-ink hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink" data-copy-btn>Copy</button>' +
      "</dd></div>" +
      (instructions
        ? '<div><dt class="text-ink-subtle">Instructions</dt><dd class="mt-1 text-ink-muted">' +
          escapeHtml(instructions) +
          "</dd></div>"
        : "") +
      "</dl>" +
      (qr
        ? '<img src="' +
          escapeHtml(qr) +
          '" alt="Payment QR" class="mt-4 w-full max-w-xs rounded-md border border-border object-contain bg-surface sm:max-w-sm">'
        : '<p class="mt-3 text-sm text-ink-subtle">No QR image uploaded.</p>');

    container.querySelectorAll("[data-copy-btn]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const valueEl = btn.parentElement
          ? btn.parentElement.querySelector("[data-copy-value]")
          : null;
        copyText(valueEl ? valueEl.textContent : "", btn);
      });
    });
  }

  function proofMaxBytes(maxMb) {
    const mb = parseInt(maxMb, 10);
    return (Number.isFinite(mb) && mb > 0 ? mb : 15) * 1024 * 1024;
  }

  function validateProofFile(file, maxMb) {
    const allowed = [".png", ".jpg", ".jpeg", ".pdf"];
    if (!file) return "Choose a proof file.";
    const name = (file.name || "").toLowerCase();
    const okExt = allowed.some(function (ext) {
      return name.endsWith(ext);
    });
    if (!okExt) {
      return "Proof must be PNG, JPG, JPEG, or PDF.";
    }
    const limit = proofMaxBytes(maxMb);
    const label = String(parseInt(maxMb, 10) || 15) + " MB";
    if (file.size > limit) {
      return "Proof file must be " + label + " or smaller.";
    }
    return "";
  }

  global.BlytzPaymentDetails = {
    renderChannelDetails: renderChannelDetails,
    validateProofFile: validateProofFile,
    proofMaxBytes: proofMaxBytes,
  };
})(window);
