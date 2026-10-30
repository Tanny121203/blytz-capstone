/**
 * Editor page wiring: save-state, navigation guards, payment modal, submit.
 * Stage G: dirty tracking via persist fingerprints; save status; readiness review.
 * Stage H: customer design preview / final review (presentation-only mock-ups).
 * Stage I: submission workflow hardening (submit lock, fingerprint, no false success).
 * Stage I.1: submit previews render from the frozen persist payload, not the live canvas.
 */
(function () {
  "use strict";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function openModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("hidden");
    el.classList.add("flex");
    document.body.classList.add("overflow-hidden");
  }

  function closeModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add("hidden");
    el.classList.remove("flex");
    if (!document.querySelector("[data-modal].flex, [data-drawer]:not(.hidden)")) {
      document.body.classList.remove("overflow-hidden");
    }
  }

  function modalFocusable(root) {
    if (!root) return [];
    return Array.prototype.slice
      .call(
        root.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      )
      .filter(function (el) {
        if (el.hasAttribute("disabled") || el.getAttribute("aria-hidden") === "true") {
          return false;
        }
        // Backdrop close targets are focusable for click but not tab stops.
        if (el.getAttribute("tabindex") === "-1") return false;
        return true;
      });
  }

  function formatMMSS(totalSeconds) {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
  }

  function countEnvelopeObjects(envelope) {
    var n = 0;
    function add(canvas) {
      if (canvas && Array.isArray(canvas.objects)) {
        n += canvas.objects.length;
      }
    }
    if (!envelope || typeof envelope !== "object") return 0;
    add(envelope.canvas);
    if (envelope.views && typeof envelope.views === "object") {
      add(envelope.views.back);
    }
    return n;
  }

  function initEditorPage(root) {
    if (!root || !window.BlytzEditor) return;
    if (root.dataset.editorPageWired === "1") return;
    root.dataset.editorPageWired = "1";

    const saveUrl = root.dataset.saveUrl;
    const windowMinutes = parseInt(root.dataset.paymentWindowMinutes || "10", 10);
    const proofMaxMb = root.dataset.proofMaxMb || "15";
    const initialJson = root.dataset.canvasJson || "{}";
    const alreadySubmitted = root.dataset.alreadySubmitted === "1";

    const saveBtn = qs("[data-editor-save]", root);
    const submitBtn = qs("[data-editor-submit]", root);
    const previewBtn = qs("[data-editor-preview]", root);
    const statusEl = qs("[data-editor-status]", root);
    const saveStatusEl = qs("[data-editor-save-status]", root);
    const titleInput = qs("[data-editor-title]", root);
    const titleCrumb = qs("[data-editor-title-crumb]");
    const readinessEl = qs("[data-editor-readiness]");
    const modalId = "payment-modal";
    const previewModalId = "design-preview-modal";
    const form = qs("#payment-submit-form");
    const amountInput = qs("#payment-amount");
    const proofInput = qs("#payment-proof");
    const channelSelect = qs("#payment-channel");
    const channelDetails = qs("[data-channel-details]");
    const sendBtn = qs("#payment-sent-btn");
    const cancelBtn = qs("#payment-cancel-btn");
    const timerEl = qs("[data-payment-timer]");
    const windowStartedInput = qs("#window-started-at");
    const canvasField = qs("#submit-canvas-json");
    const clientError = qs("[data-payment-client-error]");

    let timerId = null;
    let remaining = 0;
    let windowExpired = false;

    // --- Stage G save-state ---
    let lastSavedFingerprint = null;
    let dirty = false;
    /** @type {'idle'|'unsaved'|'saving'|'saved'|'error'} */
    let saveUiStatus = "idle";
    let saveErrorMessage = "";
    let saveInFlight = false;
    let saveGeneration = 0;
    /** Stage I: at most one client submit (preview gen + POST) at a time. */
    let submitInFlight = false;
    let submitGeneration = 0;
    let unloadExempt = false;
    let lastAnnouncedSaveLabel = "";
    const saveStateListeners = [];
    /** Stage H.1: assigned once preview machine wires; called on clean save SUCCESS. */
    let triggerPreviewRefreshAfterSave = null;

    function setStatus(msg) {
      if (statusEl) statusEl.textContent = msg || "";
    }

    function currentTitle() {
      return titleInput ? String(titleInput.value || "") : "";
    }

    function currentGarment() {
      if (
        window.BlytzEditor &&
        typeof window.BlytzEditor.getGarmentState === "function"
      ) {
        return window.BlytzEditor.getGarmentState() || {};
      }
      return {
        template: root.dataset.garmentTemplate || "tee",
        color: root.dataset.garmentColor || "white",
      };
    }

    function buildFingerprint(canvasJson, title, garment) {
      var g = garment || currentGarment();
      return JSON.stringify({
        canvas: canvasJson || null,
        title: title != null ? String(title) : currentTitle(),
        garment_template: g.template || "",
        garment_color: g.color || "",
      });
    }

    function readCurrentFingerprint() {
      var canvasJson = null;
      try {
        if (window.BlytzEditor && typeof window.BlytzEditor.getCanvasJSON === "function") {
          canvasJson = window.BlytzEditor.getCanvasJSON();
        }
      } catch (err) {
        canvasJson = null;
      }
      return buildFingerprint(canvasJson, currentTitle(), currentGarment());
    }

    function saveStatusLabel() {
      if (saveUiStatus === "saving") return "Saving…";
      if (saveUiStatus === "error") {
        return saveErrorMessage
          ? "Save failed — " + saveErrorMessage
          : "Save failed. Retry with Save.";
      }
      if (saveUiStatus === "unsaved" || dirty) return "Unsaved changes";
      if (saveUiStatus === "saved") return "Saved";
      return "";
    }

    function renderSaveStatus() {
      var label = saveStatusLabel();
      if (saveStatusEl) {
        saveStatusEl.textContent = label;
        saveStatusEl.dataset.saveState = saveUiStatus;
        saveStatusEl.classList.toggle("is-error", saveUiStatus === "error");
        saveStatusEl.classList.toggle("is-unsaved", saveUiStatus === "unsaved" || dirty);
        saveStatusEl.classList.toggle("is-saving", saveUiStatus === "saving");
        saveStatusEl.classList.toggle(
          "is-saved",
          saveUiStatus === "saved" && !dirty
        );
        // Avoid flooding screen readers: only update aria when the label changes.
        if (label !== lastAnnouncedSaveLabel) {
          lastAnnouncedSaveLabel = label;
          saveStatusEl.setAttribute("aria-label", label || "Save status");
        }
      }
      root.dataset.editorDirty = dirty ? "1" : "0";
      root.dataset.editorSaveState = saveUiStatus;
      saveStateListeners.slice().forEach(function (cb) {
        try {
          cb({
            dirty: dirty,
            status: saveUiStatus,
            error: saveErrorMessage,
            label: label,
          });
        } catch (err) {
          console.error(err);
        }
      });
      refreshReadiness();
    }

    function recomputeDirtyFromSnapshot() {
      if (lastSavedFingerprint == null) return;
      // Live curve preview mutates Fabric without commitEdit — ignore until Apply/Cancel.
      if (
        window.BlytzEditorProps &&
        typeof window.BlytzEditorProps.isCurvePreviewDirty === "function" &&
        window.BlytzEditorProps.isCurvePreviewDirty()
      ) {
        return;
      }
      var current = readCurrentFingerprint();
      dirty = current !== lastSavedFingerprint;
      if (saveInFlight) {
        // Keep Saving while in flight; completion reconciles.
        renderSaveStatus();
        return;
      }
      if (dirty) {
        if (saveUiStatus !== "error") {
          saveUiStatus = "unsaved";
          saveErrorMessage = "";
        }
      } else {
        saveUiStatus = "saved";
        saveErrorMessage = "";
      }
      renderSaveStatus();
    }

    function markBaselineSaved(fingerprint) {
      lastSavedFingerprint = fingerprint || readCurrentFingerprint();
      dirty = false;
      saveUiStatus = "saved";
      saveErrorMessage = "";
      renderSaveStatus();
    }

    function markUnsaved(reasonStatus) {
      dirty = true;
      if (!saveInFlight) {
        saveUiStatus = reasonStatus === "error" ? "error" : "unsaved";
      }
      renderSaveStatus();
    }

    function updateActionButtons() {
      const allow =
        window.BlytzEditor.canPersist && window.BlytzEditor.canPersist();
      const busy = saveInFlight || submitInFlight;
      if (saveBtn) saveBtn.disabled = !allow || busy;
      if (submitBtn) submitBtn.disabled = !allow || alreadySubmitted || busy;
      if (cancelBtn) cancelBtn.disabled = !!submitInFlight;
    }

    function updateSendEnabled() {
      if (!sendBtn) return;
      const hasAmount = amountInput && parseFloat(amountInput.value) > 0;
      const hasProof = proofInput && proofInput.files && proofInput.files.length > 0;
      const editorOk =
        window.BlytzEditor.canPersist && window.BlytzEditor.canPersist();
      sendBtn.disabled =
        windowExpired ||
        alreadySubmitted ||
        !editorOk ||
        saveInFlight ||
        submitInFlight ||
        !(hasAmount && hasProof);
    }

    function getSubmissionReadiness() {
      var checks = [];
      var blocking = false;

      if (alreadySubmitted) {
        checks.push({
          id: "submitted",
          ok: false,
          blocking: true,
          message: "This design is already submitted and can no longer be changed.",
        });
        blocking = true;
      } else {
        checks.push({
          id: "submitted",
          ok: true,
          blocking: false,
          message: "Design is still a draft (not yet submitted).",
        });
      }

      var canPersist =
        window.BlytzEditor.canPersist && window.BlytzEditor.canPersist();
      if (!canPersist) {
        var reason =
          (window.BlytzEditor.getPersistBlockReason &&
            window.BlytzEditor.getPersistBlockReason()) ||
          "Design is not ready to save or submit.";
        checks.push({
          id: "persist",
          ok: false,
          blocking: true,
          message: reason,
        });
        blocking = true;
      } else {
        checks.push({
          id: "persist",
          ok: true,
          blocking: false,
          message: "Editor is ready to persist this design.",
        });
      }

      if (saveInFlight) {
        checks.push({
          id: "save_inflight",
          ok: false,
          blocking: true,
          message: "A save is still in progress. Wait for it to finish before submitting.",
        });
        blocking = true;
      } else {
        checks.push({
          id: "save_inflight",
          ok: true,
          blocking: false,
          message: "No save is currently in progress.",
        });
      }

      if (submitInFlight) {
        checks.push({
          id: "submit_inflight",
          ok: false,
          blocking: true,
          message: "A submission is already in progress.",
        });
        blocking = true;
      } else {
        checks.push({
          id: "submit_inflight",
          ok: true,
          blocking: false,
          message: "No submission is currently in progress.",
        });
      }

      if (dirty) {
        checks.push({
          id: "unsaved",
          ok: false,
          blocking: false,
          message:
            "You have unsaved changes. Submit will send the current canvas; Save first if you want a draft copy stored.",
        });
      } else {
        checks.push({
          id: "unsaved",
          ok: true,
          blocking: false,
          message: "No unsaved changes relative to the last successful save.",
        });
      }

      // Non-destructive size/artwork probe — do NOT call preparePersistPayload here
      // (that discards in-progress curve previews). Submit/Save still use preparePersistPayload.
      var envelope = null;
      var byteLength = 0;
      var maxBytes =
        (window.BlytzCanvas && window.BlytzCanvas.MAX_CANVAS_JSON_BYTES) ||
        2 * 1024 * 1024;
      if (canPersist && window.BlytzEditor.getCanvasJSON) {
        try {
          envelope = window.BlytzEditor.getCanvasJSON();
          var jsonString = JSON.stringify(envelope);
          if (
            window.BlytzCanvas &&
            typeof window.BlytzCanvas.utf8ByteLength === "function"
          ) {
            byteLength = window.BlytzCanvas.utf8ByteLength(jsonString);
          } else {
            byteLength = jsonString.length;
          }
        } catch (err) {
          envelope = null;
          byteLength = 0;
        }
      }
      if (!canPersist) {
        checks.push({
          id: "payload",
          ok: false,
          blocking: true,
          message: "Payload check has not run because the editor is not ready.",
        });
        checks.push({
          id: "artwork",
          ok: false,
          blocking: false,
          message: "Artwork check has not run because the editor is not ready.",
        });
      } else if (!envelope) {
        checks.push({
          id: "payload",
          ok: false,
          blocking: true,
          message: "Design data could not be read for size validation.",
        });
        blocking = true;
        checks.push({
          id: "artwork",
          ok: false,
          blocking: false,
          message: "Artwork check could not run.",
        });
      } else if (byteLength > maxBytes) {
        checks.push({
          id: "payload",
          ok: false,
          blocking: true,
          message:
            "This design is too large to save (" +
            Math.ceil(byteLength / 1024) +
            " KB). Remove or use smaller images (max about " +
            Math.floor(maxBytes / 1024) +
            " KB total) and try again.",
        });
        blocking = true;
        var oversizedCount = countEnvelopeObjects(envelope);
        checks.push({
          id: "artwork",
          ok: oversizedCount > 0,
          blocking: false,
          message:
            oversizedCount > 0
              ? "Design includes artwork, but the payload exceeds the save limit."
              : "No artwork objects yet.",
        });
      } else {
        checks.push({
          id: "payload",
          ok: true,
          blocking: false,
          message:
            "Design data is within the " +
            Math.floor(maxBytes / 1024) +
            " KB save limit.",
        });
        var objCount = countEnvelopeObjects(envelope);
        if (objCount > 0) {
          checks.push({
            id: "artwork",
            ok: true,
            blocking: false,
            message:
              "Design includes " +
              objCount +
              " artwork object" +
              (objCount === 1 ? "" : "s") +
              " (front and/or back).",
          });
        } else {
          // Server does not require artwork — advisory only.
          checks.push({
            id: "artwork",
            ok: false,
            blocking: false,
            message:
              "No artwork objects yet. You can still submit, but consider adding text or images first.",
          });
        }
      }

      var hasChannels = !!(channelSelect && channelSelect.options && channelSelect.options.length);
      if (!hasChannels) {
        checks.push({
          id: "channels",
          ok: false,
          blocking: true,
          message:
            "No active payment channels are available. Contact staff before submitting.",
        });
        blocking = true;
      } else {
        checks.push({
          id: "channels",
          ok: true,
          blocking: false,
          message: "Payment channels are available for the submit form.",
        });
      }

      checks.push({
        id: "payment_fields",
        ok: false,
        blocking: false,
        message:
          "Amount and proof of payment are collected in the payment window (server validates them).",
      });

      return {
        ready: !blocking,
        checks: checks,
        dirty: dirty,
        saveStatus: saveUiStatus,
      };
    }

    function refreshReadiness() {
      if (!readinessEl) return;
      var result = getSubmissionReadiness();
      var html = "";
      html +=
        '<p class="editor-readiness-summary ' +
        (result.ready ? "is-ready" : "is-blocked") +
        '">' +
        (result.ready
          ? "Ready to open the payment window when you choose Submit."
          : "Resolve the issues below before submitting.") +
        "</p><ul class=\"editor-readiness-list\">";
      result.checks.forEach(function (c) {
        var cls = c.ok ? "is-ok" : c.blocking ? "is-block" : "is-warn";
        var mark = c.ok ? "✓" : c.blocking ? "!" : "•";
        html +=
          '<li class="' +
          cls +
          '" data-readiness-id="' +
          c.id +
          '"><span class="editor-readiness-mark" aria-hidden="true">' +
          mark +
          "</span> " +
          c.message +
          "</li>";
      });
      html += "</ul>";
      readinessEl.innerHTML = html;
      readinessEl.dataset.readinessReady = result.ready ? "1" : "0";
    }

    function validateProofClient() {
      if (!window.BlytzPaymentDetails) {
        return "Payment helpers failed to load.";
      }
      if (!proofInput || !proofInput.files || !proofInput.files[0]) {
        return "Choose a proof file.";
      }
      return window.BlytzPaymentDetails.validateProofFile(
        proofInput.files[0],
        proofMaxMb
      );
    }

    function showChannelDetails() {
      if (!channelSelect || !channelDetails || !window.BlytzPaymentDetails) return;
      const opt = channelSelect.options[channelSelect.selectedIndex];
      window.BlytzPaymentDetails.renderChannelDetails(channelDetails, opt || null);
    }

    function stopTimer() {
      if (timerId) {
        clearInterval(timerId);
        timerId = null;
      }
    }

    function expireWindow() {
      windowExpired = true;
      stopTimer();
      if (timerEl) timerEl.textContent = "00:00";
      updateSendEnabled();
      closeModal(modalId);
      setStatus("Payment window expired. Nothing was recorded.");
    }

    function startPaymentWindow() {
      windowExpired = false;
      remaining = Math.max(1, windowMinutes * 60);
      if (windowStartedInput) {
        windowStartedInput.value = new Date().toISOString();
      }
      if (timerEl) timerEl.textContent = formatMMSS(remaining);
      stopTimer();
      timerId = setInterval(function () {
        remaining -= 1;
        if (timerEl) timerEl.textContent = formatMMSS(Math.max(0, remaining));
        if (remaining <= 0) {
          expireWindow();
        }
      }, 1000);
      updateSendEnabled();
    }

    function cancelPayment() {
      // Do not dismiss while a submit POST may already be in flight — avoids
      // implying "nothing recorded" when the server might still create an order.
      if (submitInFlight) {
        setStatus("Submission in progress. Wait for the server response.");
        if (clientError) {
          clientError.textContent =
            "Submission in progress. Wait for the server response.";
        }
        return;
      }
      stopTimer();
      windowExpired = false;
      if (form) form.reset();
      if (windowStartedInput) windowStartedInput.value = "";
      if (clientError) clientError.textContent = "";
      closeModal(modalId);
      setStatus("Payment cancelled. Nothing was recorded.");
      updateSendEnabled();
    }

    function finishSubmitFailure(msg, gen) {
      if (gen != null && gen !== submitGeneration) {
        return;
      }
      submitInFlight = false;
      unloadExempt = false;
      setStatus(msg);
      if (clientError) clientError.textContent = msg;
      updateActionButtons();
      updateSendEnabled();
      refreshReadiness();
    }

    function preparePayloadOrWarn() {
      if (!window.BlytzEditor.preparePersistPayload) {
        return {
          ok: false,
          error: "Editor is not ready.",
        };
      }
      return window.BlytzEditor.preparePersistPayload();
    }

    function dataURLToBlob(dataURL) {
      if (!dataURL || typeof dataURL !== "string" || dataURL.indexOf("data:image/png") !== 0) {
        throw new Error("Invalid preview PNG.");
      }
      var parts = dataURL.split(",");
      var mimeMatch = parts[0].match(/:(.*?);/);
      var mime = mimeMatch ? mimeMatch[1] : "image/png";
      var binary = atob(parts[1] || "");
      var len = binary.length;
      var bytes = new Uint8Array(len);
      for (var i = 0; i < len; i++) {
        bytes[i] = binary.charCodeAt(i);
      }
      return new Blob([bytes], { type: mime });
    }

    function resolvePreview(result) {
      return Promise.resolve(result).then(function (url) {
        if (!url || typeof url !== "string" || url.indexOf("data:image/png") !== 0) {
          throw new Error("Preview generation failed.");
        }
        // Reject the 1×1 fallback stub — not a real mock-up.
        if (url.length < 200) {
          throw new Error("Preview generation failed.");
        }
        return url;
      });
    }

    function submitFailureMessage(err) {
      var fallback =
        "Could not finish submission (network or preview error). Check Orders before retrying if you are unsure whether it went through.";
      var msg = err && err.message ? String(err.message) : "";
      var safe = {
        "Could not create preview. Please try again.": true,
        "Preview generation failed.": true,
        "Could not render artwork for preview.": true,
        "Could not load image for preview.": true,
        "Could not load artwork for preview.": true,
        "Could not load garment for preview.": true,
        "Could not create preview canvas.": true,
        "Preview PNG exceeds the 5 MB upload limit.": true,
        "Preview could not render every design object.": true,
        "Garment export helpers are not available.": true,
        "Editor is not ready.": true,
        "Unknown preview view.": true,
        "Invalid preview PNG.": true,
        "Fabric StaticCanvas is not available.": true,
        "Missing garment SVG for export.": true,
      };
      return safe[msg] ? msg : fallback;
    }

    function formatSaveErrors(data) {
      if (!data || !data.errors) return "Save failed. Please try again.";
      var parts = [];
      Object.keys(data.errors).forEach(function (key) {
        var vals = data.errors[key];
        if (Array.isArray(vals)) {
          vals.forEach(function (v) {
            parts.push(v);
          });
        } else if (vals) {
          parts.push(String(vals));
        }
      });
      return parts.length ? parts.join(" ") : "Save failed. Please try again.";
    }

    function performSave() {
      if (submitInFlight) {
        setStatus("Wait for the current submission to finish before saving.");
        return;
      }
      if (saveInFlight) {
        setStatus("Save already in progress.");
        return;
      }
      const prepared = preparePayloadOrWarn();
      if (!prepared.ok) {
        setStatus(prepared.error || "Save blocked.");
        markUnsaved("error");
        saveUiStatus = "error";
        saveErrorMessage = prepared.error || "Save blocked.";
        renderSaveStatus();
        updateActionButtons();
        return;
      }
      const fingerprint = buildFingerprint(
        prepared.json,
        currentTitle(),
        currentGarment()
      );
      saveInFlight = true;
      saveGeneration += 1;
      const gen = saveGeneration;
      saveUiStatus = "saving";
      saveErrorMessage = "";
      renderSaveStatus();
      setStatus("Saving…");
      updateActionButtons();
      updateSendEnabled();

      const body = new FormData();
      body.append("canvas_json", prepared.jsonString);
      body.append("csrfmiddlewaretoken", getCookie("csrftoken"));
      if (titleInput) {
        body.append("title", titleInput.value || "");
      }
      const g = currentGarment();
      if (g && g.template) body.append("garment_template", g.template);
      if (g && g.color) body.append("garment_color", g.color);

      fetch(saveUrl, {
        method: "POST",
        body: body,
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (r) {
          return r
            .json()
            .then(function (data) {
              return { httpOk: r.ok, data: data };
            })
            .catch(function () {
              return { httpOk: false, data: null };
            });
        })
        .then(function (res) {
          if (gen !== saveGeneration) {
            return;
          }
          saveInFlight = false;
          const success = !!(res.httpOk && res.data && res.data.ok);
          if (success) {
            if (res.data && res.data.title) {
              if (titleInput) titleInput.value = res.data.title;
              if (titleCrumb) titleCrumb.textContent = res.data.title;
              document.title = "Editor · " + res.data.title + " — Blytz";
            }
            // Only treat as saved if the saved fingerprint still matches current
            // OR becomes the new baseline — then recompute vs live state.
            lastSavedFingerprint = fingerprint;
            var live = readCurrentFingerprint();
            dirty = live !== lastSavedFingerprint;
            saveUiStatus = dirty ? "unsaved" : "saved";
            saveErrorMessage = "";
            setStatus(dirty ? "Saved earlier revision; newer edits are unsaved." : "");
            renderSaveStatus();
            // Stage H.1: clean save SUCCESS → refresh open preview mock-up (not on failed/stale/dirty).
            if (
              !dirty &&
              saveUiStatus === "saved" &&
              typeof triggerPreviewRefreshAfterSave === "function"
            ) {
              triggerPreviewRefreshAfterSave(gen);
            }
          } else {
            dirty = true;
            saveUiStatus = "error";
            saveErrorMessage = formatSaveErrors(res.data);
            setStatus(saveErrorMessage);
            renderSaveStatus();
          }
          updateActionButtons();
          updateSendEnabled();
        })
        .catch(function () {
          if (gen !== saveGeneration) {
            return;
          }
          saveInFlight = false;
          dirty = true;
          saveUiStatus = "error";
          saveErrorMessage = "Network error. Your latest edits are still on this page — try Save again.";
          setStatus(saveErrorMessage);
          renderSaveStatus();
          updateActionButtons();
          updateSendEnabled();
        });
    }

    function shouldWarnUnload() {
      return dirty && !unloadExempt && !alreadySubmitted;
    }

    function allowUnloadOnce() {
      unloadExempt = true;
    }

    function confirmLeaveIfDirty(event) {
      if (!shouldWarnUnload()) return true;
      var ok = window.confirm(
        "You have unsaved changes. Leave this page without saving?"
      );
      if (!ok && event) {
        event.preventDefault();
        event.stopPropagation();
      }
      return ok;
    }

    // Initial load — do not treat sync return as "ready".
    setStatus("Loading design…");
    if (saveStatusEl) saveStatusEl.textContent = "";
    updateActionButtons();
    try {
      window.BlytzEditor.loadCanvasJSON(JSON.parse(initialJson));
    } catch (e) {
      window.BlytzEditor.loadCanvasJSON({});
    }

    if (window.BlytzEditor.whenReady) {
      window.BlytzEditor.whenReady().then(function (result) {
        updateActionButtons();
        updateSendEnabled();
        if (result && result.state === "error") {
          setStatus(
            (window.BlytzEditor.getPersistBlockReason &&
              window.BlytzEditor.getPersistBlockReason()) ||
              "Design could not be loaded."
          );
          saveUiStatus = "idle";
          renderSaveStatus();
        } else if (result && result.canPersist) {
          setStatus("");
          markBaselineSaved();
        } else {
          setStatus("");
          saveUiStatus = "idle";
          renderSaveStatus();
        }
        refreshReadiness();
      });
    }

    // Dirty triggers: committed canvas edits only (not selection / live preview).
    if (typeof window.BlytzEditor.onCommittedChange === "function") {
      window.BlytzEditor.onCommittedChange(function () {
        recomputeDirtyFromSnapshot();
      });
    }
    if (typeof window.BlytzEditor.onGarmentChange === "function") {
      window.BlytzEditor.onGarmentChange(function () {
        recomputeDirtyFromSnapshot();
      });
    }
    if (typeof window.BlytzEditor.onHistoryNavigate === "function") {
      window.BlytzEditor.onHistoryNavigate(function () {
        recomputeDirtyFromSnapshot();
      });
    }
    if (titleInput) {
      titleInput.addEventListener("input", function () {
        recomputeDirtyFromSnapshot();
      });
      titleInput.addEventListener("change", function () {
        recomputeDirtyFromSnapshot();
      });
    }

    // Browser reload / tab close — native dialog only (no custom text).
    window.addEventListener("beforeunload", function (e) {
      if (!shouldWarnUnload()) return;
      e.preventDefault();
      e.returnValue = "";
    });

    // In-app navigation from the editor (breadcrumb / site links), not global site-wide.
    root.addEventListener(
      "click",
      function (e) {
        var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
        if (!a || !root.contains(a)) return;
        if (a.getAttribute("download") != null) return;
        if (a.target === "_blank") return;
        var href = a.getAttribute("href") || "";
        if (!href || href.charAt(0) === "#") return;
        if (href.indexOf("javascript:") === 0) return;
        if (!shouldWarnUnload()) return;
        if (!confirmLeaveIfDirty(e)) {
          return;
        }
        allowUnloadOnce();
      },
      true
    );

    // --- Stage H: design preview / final review (presentation-only) ---
    const previewModal = document.getElementById(previewModalId);
    const previewImg = previewModal
      ? qs("[data-design-preview-img]", previewModal)
      : null;
    const previewLoading = previewModal
      ? qs("[data-design-preview-loading]", previewModal)
      : null;
    const previewError = previewModal
      ? qs("[data-design-preview-error]", previewModal)
      : null;
    const previewErrorPanel = previewModal
      ? qs("[data-design-preview-error-panel]", previewModal)
      : null;
    const previewTitleEl = previewModal
      ? qs("[data-design-preview-title]", previewModal)
      : null;
    const previewGarmentEl = previewModal
      ? qs("[data-design-preview-garment]", previewModal)
      : null;
    const previewSideLabelEl = previewModal
      ? qs("[data-design-preview-side-label]", previewModal)
      : null;
    const previewSaveStatusEl = previewModal
      ? qs("[data-design-preview-save-status]", previewModal)
      : null;
    const previewHonestyEl = previewModal
      ? qs("[data-design-preview-honesty]", previewModal)
      : null;
    const previewReadinessEl = previewModal
      ? qs("[data-design-preview-readiness]", previewModal)
      : null;
    const previewSaveBtn = previewModal
      ? qs("[data-design-preview-save]", previewModal)
      : null;
    const previewFigure = previewModal
      ? qs("#design-preview-figure", previewModal)
      : null;
    const previewRetryBtn = previewModal
      ? qs("[data-design-preview-refresh-retry]", previewModal)
      : null;
    const previewFrame = previewModal
      ? qs("[data-design-preview-frame]", previewModal)
      : null;

    let previewOpen = false;
    let previewSide = "front";
    let previewRequestGen = 0;
    let previewRestoreFocus = null;
    let previewObjectUrl = null;
    let previewUnsubSave = null;
    /** @type {'idle'|'loading'|'ready'|'error'} Distinct from saveUiStatus. */
    let previewRenderStatus = "idle";
    /** Save generation that requested a post-save mock-up refresh (0 = none). */
    let previewRefreshSaveGen = 0;

    function clearPreviewImageResources() {
      if (previewObjectUrl) {
        try {
          URL.revokeObjectURL(previewObjectUrl);
        } catch (err) {
          /* ignore */
        }
        previewObjectUrl = null;
      }
      if (previewImg) {
        previewImg.removeAttribute("src");
        previewImg.hidden = true;
        previewImg.alt = "";
      }
    }

    function assignPreviewImage(url, side) {
      if (!previewImg || !url) return;
      var prevUrl = previewObjectUrl;
      // Prefer blob URLs so obsolete object URLs can be revoked safely.
      var nextUrl = url;
      var nextObjectUrl = null;
      if (url.indexOf("data:image/png") === 0) {
        try {
          nextObjectUrl = URL.createObjectURL(dataURLToBlob(url));
          nextUrl = nextObjectUrl;
        } catch (err) {
          nextObjectUrl = null;
          nextUrl = url;
        }
      }
      previewImg.src = nextUrl;
      previewImg.hidden = false;
      previewImg.alt =
        "Garment mock-up, " + (side === "back" ? "back" : "front") + " view";
      previewObjectUrl = nextObjectUrl;
      if (prevUrl && prevUrl !== nextObjectUrl) {
        try {
          URL.revokeObjectURL(prevUrl);
        } catch (err) {
          /* ignore */
        }
      }
    }

    function setPreviewRenderUi(opts) {
      var loading = !!(opts && opts.loading);
      var errorMsg = opts && opts.errorMsg ? String(opts.errorMsg) : "";
      var loadingMsg =
        opts && opts.loadingMsg
          ? String(opts.loadingMsg)
          : "Preparing mock-up…";
      var showRetry = !!(opts && opts.showRetry);
      if (previewLoading) {
        previewLoading.hidden = !loading;
        previewLoading.textContent = loading ? loadingMsg : "";
      }
      if (previewError) {
        previewError.textContent = errorMsg || "";
      }
      if (previewErrorPanel) {
        previewErrorPanel.hidden = !errorMsg;
      }
      if (previewRetryBtn) {
        previewRetryBtn.hidden = !showRetry;
        previewRetryBtn.disabled = !!(loading || saveInFlight);
      }
      if (previewFrame) {
        previewFrame.dataset.previewRenderStatus = previewRenderStatus;
      }
    }

    function garmentReviewLabel() {
      var g = currentGarment();
      var tpl = g.template || "tee";
      var color = g.color || "white";
      var tplLabel = tpl;
      var colorLabel = color;
      if (window.BlytzGarments) {
        if (Array.isArray(window.BlytzGarments.GARMENT_TYPES)) {
          for (var i = 0; i < window.BlytzGarments.GARMENT_TYPES.length; i++) {
            var gt = window.BlytzGarments.GARMENT_TYPES[i];
            if (gt && gt.id === tpl) {
              tplLabel = gt.label || tpl;
              break;
            }
          }
        }
        if (Array.isArray(window.BlytzGarments.GARMENT_COLORS)) {
          for (var j = 0; j < window.BlytzGarments.GARMENT_COLORS.length; j++) {
            var gc = window.BlytzGarments.GARMENT_COLORS[j];
            if (gc && gc.id === color) {
              colorLabel = gc.label || color;
              break;
            }
          }
        }
      }
      return tplLabel + " · " + colorLabel;
    }

    function syncPreviewSideTabs() {
      if (!previewModal) return;
      previewModal
        .querySelectorAll("[data-design-preview-side]")
        .forEach(function (btn) {
          var side = btn.getAttribute("data-design-preview-side");
          var active = side === previewSide;
          btn.classList.toggle("is-active", active);
          btn.setAttribute("aria-selected", active ? "true" : "false");
          btn.tabIndex = active ? 0 : -1;
        });
      if (previewFigure) {
        previewFigure.setAttribute(
          "aria-labelledby",
          previewSide === "back"
            ? "design-preview-tab-back"
            : "design-preview-tab-front"
        );
      }
      if (previewSideLabelEl) {
        previewSideLabelEl.textContent =
          previewSide === "back" ? "Back" : "Front";
      }
    }

    function refreshPreviewReview() {
      if (!previewOpen) return;
      if (previewTitleEl) {
        previewTitleEl.textContent = currentTitle() || "Untitled";
      }
      if (previewGarmentEl) {
        previewGarmentEl.textContent = garmentReviewLabel();
      }
      if (previewSideLabelEl) {
        previewSideLabelEl.textContent =
          previewSide === "back" ? "Back" : "Front";
      }
      var label = saveStatusLabel() || "—";
      if (previewSaveStatusEl) {
        previewSaveStatusEl.textContent = label;
        previewSaveStatusEl.dataset.saveState = saveUiStatus;
      }
      if (previewHonestyEl) {
        var honesty = "";
        if (saveInFlight || saveUiStatus === "saving") {
          honesty =
            "Save in progress. This mock-up shows the current editor canvas, not a confirmed saved final yet.";
        } else if (saveUiStatus === "error") {
          honesty =
            "Last save failed. This is still an unsaved draft preview — do not treat it as a saved final.";
        } else if (dirty || saveUiStatus === "unsaved") {
          honesty =
            "Unsaved changes. This is a live draft mock-up, not a saved final design.";
        } else if (
          saveUiStatus === "saved" &&
          !dirty &&
          previewRenderStatus === "loading"
        ) {
          honesty =
            "Save succeeded. Updating the mock-up to match the saved design…";
        } else if (
          saveUiStatus === "saved" &&
          !dirty &&
          previewRenderStatus === "error"
        ) {
          honesty =
            "Save succeeded, but the mock-up could not be refreshed. Use Retry mock-up — your design remains saved.";
        } else if (saveUiStatus === "saved" && !dirty) {
          honesty =
            "Matches the last successful save. Close this preview and use Submit in the editor when ready to order.";
        } else {
          honesty = "Review the mock-up before returning to the editor.";
        }
        previewHonestyEl.textContent = honesty;
        previewHonestyEl.classList.toggle(
          "is-warn",
          !!(
            dirty ||
            saveUiStatus === "unsaved" ||
            saveUiStatus === "error" ||
            saveInFlight ||
            (previewRenderStatus === "error" && saveUiStatus === "saved")
          )
        );
        previewHonestyEl.classList.toggle(
          "is-ok",
          saveUiStatus === "saved" &&
            !dirty &&
            !saveInFlight &&
            previewRenderStatus === "ready"
        );
      }
      if (previewReadinessEl) {
        var result = getSubmissionReadiness();
        var html =
          '<p class="editor-readiness-summary ' +
          (result.ready ? "is-ready" : "is-blocked") +
          '">' +
          (result.ready
            ? "Client checks look ready for Submit (server remains authoritative)."
            : "Client checks show blocking issues — resolve them before Submit.") +
          "</p><ul class=\"editor-readiness-list\">";
        result.checks.forEach(function (c) {
          var cls = c.ok ? "is-ok" : c.blocking ? "is-block" : "is-warn";
          var mark = c.ok ? "✓" : c.blocking ? "!" : "•";
          html +=
            '<li class="' +
            cls +
            '" data-readiness-id="' +
            c.id +
            '"><span class="editor-readiness-mark" aria-hidden="true">' +
            mark +
            "</span> " +
            c.message +
            "</li>";
        });
        html += "</ul>";
        previewReadinessEl.innerHTML = html;
      }
      if (previewSaveBtn) {
        var allow =
          window.BlytzEditor.canPersist && window.BlytzEditor.canPersist();
        previewSaveBtn.disabled = !allow || alreadySubmitted || saveInFlight;
      }
    }

    function previewStillOpenForGen(gen) {
      return previewOpen && gen === previewRequestGen;
    }

    function matchesSavedFingerprintForRefresh() {
      if (dirty || saveUiStatus !== "saved") return false;
      if (lastSavedFingerprint == null) return false;
      return readCurrentFingerprint() === lastSavedFingerprint;
    }

    function requestPreviewRender(side) {
      var target = side === "back" ? "back" : "front";
      previewSide = target;
      syncPreviewSideTabs();
      previewRefreshSaveGen = 0;
      refreshPreviewReview();

      previewRequestGen += 1;
      var gen = previewRequestGen;
      clearPreviewImageResources();
      previewRenderStatus = "loading";
      setPreviewRenderUi({
        loading: true,
        loadingMsg: "Preparing mock-up…",
        errorMsg: "",
        showRetry: false,
      });
      refreshPreviewReview();

      var getPreview =
        window.BlytzEditor && window.BlytzEditor.getPreviewPNG
          ? window.BlytzEditor.getPreviewPNG.bind(window.BlytzEditor)
          : null;
      if (!getPreview) {
        if (!previewStillOpenForGen(gen)) return;
        previewRenderStatus = "error";
        setPreviewRenderUi({
          loading: false,
          errorMsg:
            "Preview is unavailable. Return to the editor and try again.",
          showRetry: false,
        });
        refreshPreviewReview();
        return;
      }

      // Presentation-only: includeGarment mock-up; never switches live view / commitEdit.
      Promise.resolve(getPreview({ view: target, includeGarment: true }))
        .then(function (url) {
          if (!previewStillOpenForGen(gen)) return;
          return resolvePreview(url);
        })
        .then(function (url) {
          if (!previewStillOpenForGen(gen) || !url) return;
          assignPreviewImage(url, target);
          previewRenderStatus = "ready";
          setPreviewRenderUi({
            loading: false,
            errorMsg: "",
            showRetry: false,
          });
          refreshPreviewReview();
        })
        .catch(function (err) {
          if (!previewStillOpenForGen(gen)) return;
          clearPreviewImageResources();
          previewRenderStatus = "error";
          var msg =
            (err && err.message) ||
            "Could not create this mock-up. Return to the editor and try again.";
          setPreviewRenderUi({
            loading: false,
            errorMsg: msg,
            showRetry: false,
          });
          refreshPreviewReview();
        });
    }

    /**
     * Stage H.1: after clean save SUCCESS, re-render the current preview side
     * while the modal stays open. Does not call performSave. Keeps prior image
     * until a newer successful render arrives (or on failure).
     */
    function refreshPreviewAfterSuccessfulSave(saveGen) {
      if (!previewOpen) return;
      if (!matchesSavedFingerprintForRefresh()) return;
      if (saveGen != null && saveGen !== saveGeneration) return;

      var target = previewSide === "back" ? "back" : "front";
      previewRefreshSaveGen = saveGen != null ? saveGen : saveGeneration;
      previewRequestGen += 1;
      var gen = previewRequestGen;
      previewRenderStatus = "loading";
      // Keep existing image visible under the loading overlay — do not blank it.
      setPreviewRenderUi({
        loading: true,
        loadingMsg: "Updating saved mock-up…",
        errorMsg: "",
        showRetry: false,
      });
      refreshPreviewReview();

      var getPreview =
        window.BlytzEditor && window.BlytzEditor.getPreviewPNG
          ? window.BlytzEditor.getPreviewPNG.bind(window.BlytzEditor)
          : null;
      if (!getPreview) {
        if (!previewStillOpenForGen(gen)) return;
        previewRenderStatus = "error";
        setPreviewRenderUi({
          loading: false,
          errorMsg:
            "Could not update the saved mock-up. Your design remains saved — retry the preview.",
          showRetry: true,
        });
        refreshPreviewReview();
        return;
      }

      Promise.resolve(getPreview({ view: target, includeGarment: true }))
        .then(function (url) {
          if (!previewStillOpenForGen(gen)) return;
          return resolvePreview(url);
        })
        .then(function (url) {
          if (!previewStillOpenForGen(gen) || !url) return;
          // Edits / newer save during render: do not overwrite with a stale "saved" image.
          if (!matchesSavedFingerprintForRefresh()) {
            previewRenderStatus = previewImg && previewImg.getAttribute("src")
              ? "ready"
              : "idle";
            setPreviewRenderUi({
              loading: false,
              errorMsg: "",
              showRetry: false,
            });
            refreshPreviewReview();
            return;
          }
          assignPreviewImage(url, target);
          previewRenderStatus = "ready";
          setPreviewRenderUi({
            loading: false,
            errorMsg: "",
            showRetry: false,
          });
          refreshPreviewReview();
        })
        .catch(function (err) {
          if (!previewStillOpenForGen(gen)) return;
          // Save stays Saved; keep prior image; surface refresh error + retry only.
          previewRenderStatus = "error";
          var msg =
            (err && err.message) ||
            "Could not update the saved mock-up. Your design remains saved — retry the preview.";
          setPreviewRenderUi({
            loading: false,
            errorMsg: msg,
            showRetry: true,
          });
          refreshPreviewReview();
        });
    }

    triggerPreviewRefreshAfterSave = function (saveGen) {
      refreshPreviewAfterSuccessfulSave(saveGen);
    };

    function onPreviewKeydown(e) {
      if (!previewOpen || !previewModal) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        closeDesignPreview();
        return;
      }
      if (e.key !== "Tab") return;
      var nodes = modalFocusable(previewModal);
      if (!nodes.length) return;
      var first = nodes[0];
      var last = nodes[nodes.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first || !previewModal.contains(document.activeElement)) {
          e.preventDefault();
          last.focus();
        }
      } else if (
        document.activeElement === last ||
        !previewModal.contains(document.activeElement)
      ) {
        e.preventDefault();
        first.focus();
      }
    }

    function closeDesignPreview() {
      if (!previewOpen && !(previewModal && previewModal.classList.contains("flex"))) {
        return;
      }
      previewOpen = false;
      previewRequestGen += 1;
      previewRefreshSaveGen = 0;
      previewRenderStatus = "idle";
      clearPreviewImageResources();
      setPreviewRenderUi({
        loading: false,
        errorMsg: "",
        showRetry: false,
      });
      document.removeEventListener("keydown", onPreviewKeydown, true);
      if (typeof previewUnsubSave === "function") {
        previewUnsubSave();
        previewUnsubSave = null;
      }
      closeModal(previewModalId);
      var restore = previewRestoreFocus;
      previewRestoreFocus = null;
      if (restore && typeof restore.focus === "function") {
        try {
          restore.focus();
        } catch (err) {
          /* ignore */
        }
      }
    }

    function openDesignPreview() {
      if (!previewModal) return;
      var paymentEl = document.getElementById(modalId);
      if (paymentEl && paymentEl.classList.contains("flex")) {
        setStatus("Close the payment window before opening Preview.");
        return;
      }
      previewRestoreFocus = document.activeElement;
      previewOpen = true;
      openModal(previewModalId);
      document.addEventListener("keydown", onPreviewKeydown, true);
      var onSaveChange = function () {
        refreshPreviewReview();
      };
      saveStateListeners.push(onSaveChange);
      previewUnsubSave = function () {
        var i = saveStateListeners.indexOf(onSaveChange);
        if (i >= 0) saveStateListeners.splice(i, 1);
      };
      // Default preview side to the editor's active view (read-only; does not mutate it).
      var active =
        window.BlytzEditor && typeof window.BlytzEditor.getActiveView === "function"
          ? window.BlytzEditor.getActiveView()
          : "front";
      previewSide = active === "back" ? "back" : "front";
      syncPreviewSideTabs();
      refreshPreviewReview();
      requestPreviewRender(previewSide);
      var focusFirst = previewModal.querySelector(
        "[data-design-preview-close], [data-design-preview-side].is-active"
      );
      if (focusFirst && typeof focusFirst.focus === "function") {
        focusFirst.focus();
      }
    }

    window.BlytzEditorDesignPreview = {
      open: openDesignPreview,
      close: closeDesignPreview,
      isOpen: function () {
        return !!previewOpen;
      },
      getSide: function () {
        return previewSide;
      },
      setSide: function (side) {
        if (!previewOpen) return;
        requestPreviewRender(side === "back" ? "back" : "front");
      },
      getRequestGeneration: function () {
        return previewRequestGen;
      },
      getRenderStatus: function () {
        return previewRenderStatus;
      },
      refreshAfterSave: function () {
        refreshPreviewAfterSuccessfulSave(saveGeneration);
      },
      refreshReview: refreshPreviewReview,
    };

    if (previewBtn) {
      previewBtn.addEventListener("click", function () {
        openDesignPreview();
      });
    }
    if (previewModal) {
      previewModal
        .querySelectorAll("[data-design-preview-close]")
        .forEach(function (el) {
          el.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            closeDesignPreview();
          });
        });
      previewModal
        .querySelectorAll("[data-design-preview-side]")
        .forEach(function (btn) {
          btn.addEventListener("click", function () {
            var side = btn.getAttribute("data-design-preview-side");
            requestPreviewRender(side === "back" ? "back" : "front");
          });
        });
      if (previewRetryBtn) {
        previewRetryBtn.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          if (!previewOpen || saveInFlight) return;
          refreshPreviewAfterSuccessfulSave(saveGeneration);
        });
      }
      if (previewSaveBtn) {
        previewSaveBtn.addEventListener("click", function () {
          // Already matches last successful save — no unnecessary save / refresh loop.
          if (!dirty && saveUiStatus === "saved" && !saveInFlight) {
            return;
          }
          performSave();
        });
      }
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        performSave();
      });
    }

    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        if (alreadySubmitted) {
          setStatus("Already submitted.");
          refreshReadiness();
          return;
        }
        if (submitInFlight) {
          setStatus("A submission is already in progress.");
          refreshReadiness();
          return;
        }
        if (saveInFlight) {
          setStatus("Wait for the current save to finish before submitting.");
          refreshReadiness();
          return;
        }
        // Re-check readiness at click time (not only disabled-button state).
        const readiness = getSubmissionReadiness();
        refreshReadiness();
        if (!readiness.ready) {
          var blockMsgs = readiness.checks
            .filter(function (c) {
              return !c.ok && c.blocking;
            })
            .map(function (c) {
              return c.message;
            });
          setStatus(blockMsgs[0] || "Submit blocked.");
          return;
        }
        const prepared = preparePayloadOrWarn();
        if (!prepared.ok) {
          setStatus(prepared.error || "Submit blocked.");
          return;
        }
        if (canvasField) {
          canvasField.value = prepared.jsonString;
        }
        const gTpl = document.getElementById("submit-garment-template");
        const gCol = document.getElementById("submit-garment-color");
        const g = currentGarment();
        if (gTpl && g && g.template) gTpl.value = g.template;
        if (gCol && g && g.color) gCol.value = g.color;
        openModal(modalId);
        showChannelDetails();
        startPaymentWindow();
      });
    }

    if (channelSelect) {
      channelSelect.addEventListener("change", showChannelDetails);
    }
    if (amountInput) amountInput.addEventListener("input", updateSendEnabled);
    if (proofInput) {
      proofInput.addEventListener("change", function () {
        if (clientError) {
          clientError.textContent = validateProofClient() || "";
        }
        updateSendEnabled();
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener("click", function (e) {
        e.preventDefault();
        cancelPayment();
      });
    }

    const modal = document.getElementById(modalId);
    if (modal) {
      modal.querySelectorAll("[data-modal-close]").forEach(function (el) {
        el.addEventListener("click", function () {
          cancelPayment();
        });
      });
    }

    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        if (windowExpired) {
          setStatus("Payment window expired. Nothing was recorded.");
          return;
        }
        // Duplicate Submit / Enter: one overlapping client request only.
        if (submitInFlight) {
          setStatus("A submission is already in progress.");
          if (clientError) {
            clientError.textContent = "A submission is already in progress.";
          }
          return;
        }
        if (saveInFlight) {
          setStatus("Wait for the current save to finish before submitting.");
          if (clientError) {
            clientError.textContent =
              "Wait for the current save to finish before submitting.";
          }
          return;
        }
        // Re-check readiness at payment-send time (not just button disabled state).
        var readinessAtSend = getSubmissionReadiness();
        refreshReadiness();
        if (!readinessAtSend.ready) {
          var blockMsgs2 = readinessAtSend.checks
            .filter(function (c) {
              return !c.ok && c.blocking;
            })
            .map(function (c) {
              return c.message;
            });
          var blockMsg = blockMsgs2[0] || "Submit blocked.";
          setStatus(blockMsg);
          if (clientError) clientError.textContent = blockMsg;
          return;
        }
        const prepared = preparePayloadOrWarn();
        if (!prepared.ok) {
          setStatus(prepared.error || "Submit blocked.");
          if (clientError) clientError.textContent = prepared.error || "Submit blocked.";
          return;
        }
        const proofErr = validateProofClient();
        if (proofErr) {
          if (clientError) clientError.textContent = proofErr;
          return;
        }
        if (!amountInput || !(parseFloat(amountInput.value) > 0)) {
          if (clientError) clientError.textContent = "Enter an amount.";
          return;
        }
        // Snapshot intended design via canonical preparePersistPayload; fingerprint
        // must still match after async preview gen (no stale/partial handoff).
        const submitFingerprint = buildFingerprint(
          prepared.json,
          currentTitle(),
          currentGarment()
        );
        var frozenEnvelope;
        try {
          frozenEnvelope = JSON.parse(prepared.jsonString);
        } catch (parseErr) {
          setStatus("Could not create preview. Please try again.");
          if (clientError) {
            clientError.textContent = "Could not create preview. Please try again.";
          }
          return;
        }
        const g2 = currentGarment();
        var garmentSnap = {
          template: g2 && g2.template ? String(g2.template) : "",
          color: g2 && g2.color ? String(g2.color) : "",
        };
        if (canvasField) {
          canvasField.value = prepared.jsonString;
        }
        const gTpl2 = document.getElementById("submit-garment-template");
        const gCol2 = document.getElementById("submit-garment-color");
        if (gTpl2 && garmentSnap.template) gTpl2.value = garmentSnap.template;
        if (gCol2 && garmentSnap.color) gCol2.value = garmentSnap.color;

        submitInFlight = true;
        submitGeneration += 1;
        const gen = submitGeneration;
        if (clientError) clientError.textContent = "";
        setStatus("Generating previews…");
        updateActionButtons();
        updateSendEnabled();
        refreshReadiness();

        var renderFrozen =
          window.BlytzEditor && window.BlytzEditor.renderFrozenPreview
            ? window.BlytzEditor.renderFrozenPreview.bind(window.BlytzEditor)
            : null;
        if (!renderFrozen) {
          finishSubmitFailure("Could not create preview. Please try again.", gen);
          return;
        }

        Promise.all([
          resolvePreview(
            renderFrozen({
              envelope: frozenEnvelope,
              view: "front",
              garment: garmentSnap,
            })
          ),
          resolvePreview(
            renderFrozen({
              envelope: frozenEnvelope,
              view: "back",
              garment: garmentSnap,
            })
          ),
        ])
          .then(function (urls) {
            if (gen !== submitGeneration) {
              return null;
            }
            // Design must still match the snapshotted payload (mutation during submit).
            var liveFp = readCurrentFingerprint();
            if (liveFp !== submitFingerprint) {
              finishSubmitFailure(
                "Design changed during submission. Review your design and try Submit again.",
                gen
              );
              return null;
            }
            // Re-bind from the frozen snapshot (not a later live read).
            if (canvasField) {
              canvasField.value = prepared.jsonString;
            }
            if (gTpl2 && garmentSnap.template) gTpl2.value = garmentSnap.template;
            if (gCol2 && garmentSnap.color) gCol2.value = garmentSnap.color;
            setStatus("Submitting…");
            var body = new FormData(form);
            body.set("canvas_json", prepared.jsonString);
            if (garmentSnap.template) body.set("garment_template", garmentSnap.template);
            if (garmentSnap.color) body.set("garment_color", garmentSnap.color);
            body.set(
              "preview_image",
              dataURLToBlob(urls[0]),
              "preview_front.png"
            );
            body.set(
              "preview_back_image",
              dataURLToBlob(urls[1]),
              "preview_back.png"
            );
            return fetch(form.action, {
              method: "POST",
              body: body,
              headers: {
                "X-Requested-With": "XMLHttpRequest",
                Accept: "application/json",
              },
              credentials: "same-origin",
            }).then(function (r) {
              return r
                .json()
                .then(function (data) {
                  return { httpOk: r.ok, status: r.status, data: data };
                })
                .catch(function () {
                  return { httpOk: false, status: r.status, data: null };
                });
            });
          })
          .then(function (res) {
            if (gen !== submitGeneration) {
              return;
            }
            if (res == null) {
              return;
            }
            if (res && res.httpOk && res.data && res.data.ok && res.data.redirect) {
              // Never claim success before server confirms; only then leave page.
              allowUnloadOnce();
              window.location.href = res.data.redirect;
              return;
            }
            var msg = "Submit failed. Please try again.";
            if (res && res.data && res.data.errors) {
              var parts = [];
              Object.keys(res.data.errors).forEach(function (key) {
                var vals = res.data.errors[key];
                if (Array.isArray(vals)) {
                  vals.forEach(function (v) {
                    parts.push(v);
                  });
                } else if (vals) {
                  parts.push(String(vals));
                }
              });
              if (parts.length) msg = parts.join(" ");
            } else if (res && !res.data) {
              msg =
                "Submit response was unclear. Check Orders before retrying — do not submit again if an order already appears.";
            }
            finishSubmitFailure(msg, gen);
          })
          .catch(function (err) {
            if (gen !== submitGeneration) {
              return;
            }
            finishSubmitFailure(submitFailureMessage(err), gen);
          });
      });
    }

    // Public probe API for tests / QA (does not replace BlytzEditor persist locks).
    window.BlytzEditorSaveState = {
      isDirty: function () {
        return !!dirty;
      },
      getStatus: function () {
        return saveUiStatus;
      },
      getError: function () {
        return saveErrorMessage;
      },
      getLabel: saveStatusLabel,
      isSaveInFlight: function () {
        return !!saveInFlight;
      },
      isSubmitInFlight: function () {
        return !!submitInFlight;
      },
      getSubmitGeneration: function () {
        return submitGeneration;
      },
      getSubmissionReadiness: getSubmissionReadiness,
      recompute: recomputeDirtyFromSnapshot,
      allowUnloadOnce: allowUnloadOnce,
      shouldWarnUnload: shouldWarnUnload,
      onChange: function (cb) {
        if (typeof cb === "function") saveStateListeners.push(cb);
        return function () {
          var i = saveStateListeners.indexOf(cb);
          if (i >= 0) saveStateListeners.splice(i, 1);
        };
      },
      _test: {
        buildFingerprint: buildFingerprint,
        readCurrentFingerprint: readCurrentFingerprint,
        markBaselineSaved: markBaselineSaved,
        countEnvelopeObjects: countEnvelopeObjects,
      },
    };

    updateActionButtons();
    updateSendEnabled();
    showChannelDetails();
    refreshReadiness();
  }

  document.addEventListener("DOMContentLoaded", function () {
    const root = qs("[data-editor-page]");
    if (root) initEditorPage(root);
  });
})();
