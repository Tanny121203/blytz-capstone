/**
 * Customer order-page payment upload: channel details + client proof check.
 * On phones the form opens as a full-screen sheet.
 */
(function () {
  "use strict";

  function init(root) {
    if (!root || !window.BlytzPaymentDetails) return;
    const maxMb = root.dataset.proofMaxMb || "15";
    const select = root.querySelector("[data-channel-select]");
    const details = root.querySelector("[data-channel-details]");
    const form = root.querySelector("[data-payment-upload-form]");
    const proofInput = root.querySelector("[data-proof-input]");
    const clientError = root.querySelector("[data-payment-client-error]");
    const sheet = root.querySelector("[data-payment-sheet]");

    function refreshChannel() {
      if (!select || !details) return;
      const opt = select.options[select.selectedIndex];
      window.BlytzPaymentDetails.renderChannelDetails(details, opt);
    }

    function openSheet() {
      if (!sheet) return;
      sheet.classList.remove("hidden");
      sheet.classList.add("is-open");
      document.body.classList.add("overflow-hidden");
      refreshChannel();
    }

    function closeSheet() {
      if (!sheet) return;
      sheet.classList.add("hidden");
      sheet.classList.remove("is-open");
      document.body.classList.remove("overflow-hidden");
    }

    root.querySelectorAll("[data-payment-sheet-open]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        openSheet();
      });
    });
    root.querySelectorAll("[data-payment-sheet-close]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        e.preventDefault();
        closeSheet();
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && sheet && sheet.classList.contains("is-open")) {
        closeSheet();
      }
    });

    if (select) {
      select.addEventListener("change", refreshChannel);
      refreshChannel();
    }

    if (form) {
      form.addEventListener("submit", function (e) {
        if (!proofInput || !proofInput.files || !proofInput.files[0]) {
          e.preventDefault();
          if (clientError) clientError.textContent = "Choose a proof file.";
          return;
        }
        const err = window.BlytzPaymentDetails.validateProofFile(
          proofInput.files[0],
          maxMb
        );
        if (err) {
          e.preventDefault();
          if (clientError) clientError.textContent = err;
        }
      });
    }

    if (proofInput) {
      proofInput.addEventListener("change", function () {
        if (!clientError) return;
        if (!proofInput.files || !proofInput.files[0]) {
          clientError.textContent = "";
          return;
        }
        clientError.textContent = window.BlytzPaymentDetails.validateProofFile(
          proofInput.files[0],
          maxMb
        );
      });
    }

    // Re-open sheet if the form re-rendered with validation errors.
    if (
      sheet &&
      clientError &&
      (clientError.textContent || "").trim()
    ) {
      openSheet();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-payment-upload]").forEach(init);
  });
})();