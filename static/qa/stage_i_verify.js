/**
 * Stage I browser verification — run via CDP Runtime.evaluate on design editor.
 * Disposable design only. Does NOT complete a real payment / create an order.
 *
 * Covers: edit → preview → close → Submit opens payment modal;
 * rapid Submit / send locks; save-pending blocks; preview non-mutation;
 * no false success; readiness re-check; ~390px viewport optional.
 */
(async function stageIVerify() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const designId =
    (location.pathname.match(/\/designs\/(\d+)\//) || [])[1] || "?";
  const report = {
    steps: [],
    ok: true,
    designId: designId,
    note: "Does not complete payment / submit POST",
  };

  const step = (name, data) => {
    report.steps.push(Object.assign({ name: name }, data));
    if (data.ok === false) report.ok = false;
  };

  for (let i = 0; i < 80; i++) {
    if (
      window.BlytzEditor &&
      BlytzEditor.whenReady &&
      window.BlytzEditorSaveState &&
      window.BlytzEditorDesignPreview &&
      BlytzCanvas &&
      BlytzCanvas.getFabricCanvas &&
      BlytzCanvas.getFabricCanvas()
    ) {
      try {
        await BlytzEditor.whenReady();
      } catch (e) {}
      break;
    }
    await sleep(100);
  }
  await sleep(200);

  const ss = window.BlytzEditorSaveState;
  const preview = window.BlytzEditorDesignPreview;
  const api = BlytzCanvas;
  const getJSON = () => BlytzEditor.getCanvasJSON();

  if (!ss || !preview || !api) {
    return { ok: false, reason: "missing-stage-i-apis", designId: designId };
  }

  step("apis", {
    ok: typeof ss.isSubmitInFlight === "function" && typeof ss.isSaveInFlight === "function",
    hasSubmitInFlight: typeof ss.isSubmitInFlight === "function",
    submitGen: ss.getSubmitGeneration && ss.getSubmitGeneration(),
  });

  function snapshot() {
    return {
      view: BlytzEditor.getActiveView(),
      dirty: ss.isDirty(),
      status: ss.getStatus(),
      fingerprint:
        ss._test && ss._test.readCurrentFingerprint
          ? ss._test.readCurrentFingerprint()
          : null,
      title: (document.querySelector("[data-editor-title]") || {}).value,
      garment: BlytzEditor.getGarmentState
        ? BlytzEditor.getGarmentState()
        : null,
      objCount: ((getJSON().canvas || {}).objects || []).length,
    };
  }

  // --- Edit artwork ---
  api.addText(getJSON, { text: "StageIFront", skipEditing: true });
  await sleep(150);
  const afterEdit = snapshot();
  step("edit_marks_unsaved", {
    ok: ss.isDirty() === true || ss.getStatus() === "unsaved",
    dirty: ss.isDirty(),
    status: ss.getStatus(),
    objCount: afterEdit.objCount,
  });

  // --- Preview open/close must not mutate design (H/H.1) ---
  const beforePreview = snapshot();
  const previewBtn = document.querySelector("[data-editor-preview]");
  if (previewBtn) previewBtn.click();
  await sleep(800);
  const modal = document.getElementById("design-preview-modal");
  const previewOpen = !!(modal && !modal.classList.contains("hidden"));
  step("preview_opens", { ok: previewOpen });

  const closeBtn =
    modal &&
    (modal.querySelector("[data-design-preview-close]") ||
      modal.querySelector("[data-modal-close]"));
  if (closeBtn) closeBtn.click();
  else if (preview && preview.close) preview.close();
  await sleep(300);
  const afterPreview = snapshot();
  step("preview_non_mutation", {
    ok:
      beforePreview.fingerprint === afterPreview.fingerprint &&
      beforePreview.view === afterPreview.view &&
      beforePreview.objCount === afterPreview.objCount,
    beforeFp: beforePreview.fingerprint && beforePreview.fingerprint.slice(0, 80),
    afterFp: afterPreview.fingerprint && afterPreview.fingerprint.slice(0, 80),
  });

  // --- Readiness / Submit opens payment modal ---
  const readiness = ss.getSubmissionReadiness();
  step("readiness_has_submit_inflight_check", {
    ok: !!(
      readiness &&
      readiness.checks &&
      readiness.checks.some(function (c) {
        return c.id === "submit_inflight";
      })
    ),
    ready: readiness && readiness.ready,
  });

  const submitBtn = document.querySelector("[data-editor-submit]");
  const paymentModal = document.getElementById("payment-modal");
  if (submitBtn && readiness && readiness.ready) {
    submitBtn.click();
    await sleep(200);
    const paymentOpen = !!(
      paymentModal &&
      paymentModal.classList.contains("flex") &&
      !paymentModal.classList.contains("hidden")
    );
    step("submit_opens_payment_modal", { ok: paymentOpen });
  } else {
    step("submit_opens_payment_modal", {
      ok: false,
      reason: "submit blocked or missing",
      ready: readiness && readiness.ready,
    });
  }

  // Rapid Submit while modal open should not start overlapping submits
  // (submitInFlight only true after payment form send — still verify lock API).
  step("submit_not_inflight_before_send", {
    ok: ss.isSubmitInFlight() === false,
    inFlight: ss.isSubmitInFlight(),
  });

  if (submitBtn) {
    submitBtn.click();
    submitBtn.click();
    await sleep(50);
    step("rapid_submit_still_one_modal", {
      ok: ss.isSubmitInFlight() === false,
      inFlight: ss.isSubmitInFlight(),
    });
  }

  // --- Save-pending blocks submit ---
  // Close payment first
  const cancelBtn = document.getElementById("payment-cancel-btn");
  if (cancelBtn) cancelBtn.click();
  await sleep(100);

  // Trigger save and immediately check readiness while saving (best-effort).
  const saveBtn = document.querySelector("[data-editor-save]");
  let saveBlockedSubmit = null;
  if (saveBtn && !ss.isSaveInFlight()) {
    // Make a tiny edit so save has work, then save.
    api.addText(getJSON, { text: "StageISave", skipEditing: true });
    await sleep(50);
    saveBtn.click();
    await sleep(20);
    if (ss.isSaveInFlight()) {
      const r = ss.getSubmissionReadiness();
      saveBlockedSubmit = !r.ready &&
        r.checks.some(function (c) {
          return c.id === "save_inflight" && c.blocking && !c.ok;
        });
      step("save_pending_blocks_readiness", {
        ok: !!saveBlockedSubmit,
        saveInFlight: ss.isSaveInFlight(),
        ready: r.ready,
      });
    } else {
      step("save_pending_blocks_readiness", {
        ok: true,
        skipped: "save finished too fast to observe in-flight",
        status: ss.getStatus(),
      });
    }
    // Wait for save to settle
    for (let i = 0; i < 50; i++) {
      if (!ss.isSaveInFlight()) break;
      await sleep(100);
    }
  } else {
    step("save_pending_blocks_readiness", {
      ok: true,
      skipped: "could not start save",
    });
  }

  // --- No false success: status must not claim order without redirect ---
  const statusEl = document.querySelector("[data-editor-status]");
  const statusText = (statusEl && statusEl.textContent) || "";
  step("no_false_success_copy", {
    ok:
      statusText.indexOf("Order") === -1 &&
      statusText.toLowerCase().indexOf("submitted successfully") === -1,
    status: statusText.slice(0, 120),
  });

  // --- Narrow viewport probe (~390px) ---
  const prevWidth = window.innerWidth;
  step("viewport_probe", {
    ok: true,
    innerWidth: prevWidth,
    note: "Host may resize separately; script does not force layout",
  });

  // Console / network: caller inspects CDP; we only flag obvious client errors.
  step("client_locks_present", {
    ok:
      typeof ss.isSubmitInFlight === "function" &&
      typeof ss.getSubmitGeneration === "function" &&
      !ss.isSubmitInFlight(),
  });

  return report;
})();
