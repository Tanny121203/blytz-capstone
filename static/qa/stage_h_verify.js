/**
 * Stage H browser verification — run via CDP Runtime.evaluate on design editor.
 * Disposable design only. Does not complete a real payment.
 */
(async function stageHVerify() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const designId =
    (location.pathname.match(/\/designs\/(\d+)\//) || [])[1] || "?";
  const report = { steps: [], ok: true, designId: designId };

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
  const previewBtn = document.querySelector("[data-editor-preview]");
  const modal = document.getElementById("design-preview-modal");

  if (!ss || !preview || !api) {
    return { ok: false, reason: "missing-stage-h-apis", designId: designId };
  }

  function snapshot() {
    return {
      view: BlytzEditor.getActiveView(),
      dirty: ss.isDirty(),
      status: ss.getStatus(),
      fingerprint:
        ss._test && ss._test.readCurrentFingerprint
          ? ss._test.readCurrentFingerprint()
          : null,
      title: (
        document.querySelector("[data-editor-title]") || {}
      ).value,
      garment: BlytzEditor.getGarmentState
        ? BlytzEditor.getGarmentState()
        : null,
      historyUndo: BlytzEditor.canUndo ? BlytzEditor.canUndo() : null,
      objCount: ((getJSON().canvas || {}).objects || []).length,
    };
  }

  function sameSnap(a, b, keys) {
    return keys.every(function (k) {
      return JSON.stringify(a[k]) === JSON.stringify(b[k]);
    });
  }

  // Stage H.1 may assign blob: object URLs (revocable) or data:image/png URLs.
  function isPreviewSrc(src) {
    if (!src || typeof src !== "string") return false;
    if (src.indexOf("blob:") === 0) return src.length > 10;
    return src.indexOf("data:image/png") === 0 && src.length > 200;
  }

  // Ensure distinct front/back artwork for mock-up checks
  api.addText(getJSON, { text: "HFront", skipEditing: true });
  await sleep(100);
  await BlytzEditor.setActiveView("back");
  await sleep(120);
  api.addText(getJSON, { text: "HBack", skipEditing: true });
  await sleep(100);
  await BlytzEditor.setActiveView("front");
  await sleep(120);

  // Save so we can test clean vs dirty honesty
  const saveBtn = document.querySelector("[data-editor-save]");
  if (saveBtn && !saveBtn.disabled) {
    saveBtn.click();
    for (let i = 0; i < 60; i++) {
      if (ss.getStatus() === "saved" && !ss.isDirty()) break;
      await sleep(100);
    }
  }
  step("baseline_saved", {
    ok: ss.getStatus() === "saved" && !ss.isDirty(),
    status: ss.getStatus(),
  });

  const beforeOpen = snapshot();
  if (previewBtn) previewBtn.click();
  else preview.open();
  await sleep(80);
  step("preview_opens", {
    ok:
      preview.isOpen() &&
      modal &&
      modal.classList.contains("flex") &&
      !modal.classList.contains("hidden"),
  });

  // Wait for front render
  for (let i = 0; i < 80; i++) {
    const img = document.querySelector("[data-design-preview-img]");
    if (img && isPreviewSrc(img.getAttribute("src"))) {
      break;
    }
    const err = document.querySelector("[data-design-preview-error]");
    if (err && err.textContent) break;
    await sleep(100);
  }
  const imgFront = document.querySelector("[data-design-preview-img]");
  const frontSrc = imgFront && imgFront.getAttribute("src");
  step("front_mockup_rendered", {
    ok: isPreviewSrc(frontSrc),
    side: preview.getSide(),
    srcLen: frontSrc ? frontSrc.length : 0,
    srcKind: frontSrc
      ? frontSrc.indexOf("blob:") === 0
        ? "blob"
        : "data"
      : null,
  });

  const midFront = snapshot();
  step("no_mutation_during_front_preview", {
    ok: sameSnap(beforeOpen, midFront, [
      "view",
      "dirty",
      "status",
      "fingerprint",
      "title",
      "garment",
      "historyUndo",
      "objCount",
    ]),
    before: beforeOpen,
    after: midFront,
  });

  // Switch preview to back without changing editor view
  const genBefore = preview.getRequestGeneration();
  preview.setSide("back");
  for (let i = 0; i < 80; i++) {
    const img = document.querySelector("[data-design-preview-img]");
    const src = img && img.getAttribute("src");
    if (
      preview.getSide() === "back" &&
      preview.getRequestGeneration() > genBefore &&
      isPreviewSrc(src) &&
      src !== frontSrc
    ) {
      break;
    }
    await sleep(100);
  }
  const imgBack = document.querySelector("[data-design-preview-img]");
  const backSrc = imgBack && imgBack.getAttribute("src");
  step("back_mockup_independent", {
    ok:
      preview.getSide() === "back" &&
      isPreviewSrc(backSrc) &&
      backSrc !== frontSrc &&
      BlytzEditor.getActiveView() === "front",
    editorView: BlytzEditor.getActiveView(),
    previewSide: preview.getSide(),
    srcChanged: backSrc !== frontSrc,
  });

  const afterBack = snapshot();
  step("no_mutation_after_side_switch", {
    ok: sameSnap(beforeOpen, afterBack, [
      "view",
      "dirty",
      "status",
      "fingerprint",
      "title",
      "garment",
      "objCount",
    ]),
  });

  // Review honesty when saved
  const honesty = document.querySelector("[data-design-preview-honesty]");
  const saveStatusPreview = document.querySelector(
    "[data-design-preview-save-status]"
  );
  step("review_saved_honesty", {
    ok:
      honesty &&
      /last successful save|Matches the last/i.test(honesty.textContent || "") &&
      saveStatusPreview &&
      /Saved/i.test(saveStatusPreview.textContent || ""),
    honesty: honesty && honesty.textContent,
    saveStatus: saveStatusPreview && saveStatusPreview.textContent,
  });

  // Close via API (same path as Back to edit)
  preview.close();
  await sleep(80);
  step("preview_closes", {
    ok: !preview.isOpen() && modal && modal.classList.contains("hidden"),
  });

  // Dirty edit → reopen → honesty warns unsaved
  api.addText(getJSON, { text: "HDirty", skipEditing: true });
  await sleep(120);
  const dirtyBefore = snapshot();
  preview.open();
  await sleep(100);
  for (let i = 0; i < 40; i++) {
    const img = document.querySelector("[data-design-preview-img]");
    if (img && img.getAttribute("src")) break;
    await sleep(100);
  }
  const honesty2 = document.querySelector("[data-design-preview-honesty]");
  step("unsaved_honesty", {
    ok:
      ss.isDirty() &&
      honesty2 &&
      /Unsaved changes|live draft/i.test(honesty2.textContent || "") &&
      !/saved final design/i.test(
        (honesty2.textContent || "").replace(/not a saved final/i, "")
      ),
    honesty: honesty2 && honesty2.textContent,
    dirty: ss.isDirty(),
  });

  // Stale request: flip sides quickly; generation must advance; editor unchanged
  const genA = preview.getRequestGeneration();
  preview.setSide("front");
  preview.setSide("back");
  preview.setSide("front");
  await sleep(400);
  step("stale_request_generation", {
    ok: preview.getRequestGeneration() > genA && preview.getSide() === "front",
    genA: genA,
    genNow: preview.getRequestGeneration(),
    side: preview.getSide(),
  });

  const afterStale = snapshot();
  step("no_mutation_after_stale_flips", {
    ok: sameSnap(dirtyBefore, afterStale, [
      "view",
      "dirty",
      "fingerprint",
      "title",
      "garment",
      "objCount",
    ]),
  });

  // Escape closes
  document.dispatchEvent(
    new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    })
  );
  await sleep(80);
  // Capture-phase handler is on document — dispatch may not hit capture listeners
  // the same way; call close if still open and note method.
  let escapeClosed = !preview.isOpen();
  if (preview.isOpen()) {
    preview.close();
    escapeClosed = false;
  }
  step("escape_or_close", {
    ok: !preview.isOpen(),
    escapeClosedNative: escapeClosed,
  });

  // Preview Save uses existing save path + H.1 post-save image refresh while open
  api.addText(getJSON, { text: "HSaveFromPreview", skipEditing: true });
  await sleep(100);
  preview.open();
  await sleep(150);
  for (let i = 0; i < 80; i++) {
    const img = document.querySelector("[data-design-preview-img]");
    if (img && isPreviewSrc(img.getAttribute("src"))) break;
    await sleep(100);
  }
  const imgBeforeSave = document.querySelector("[data-design-preview-img]");
  const srcBeforeSave = imgBeforeSave && imgBeforeSave.getAttribute("src");
  const genBeforeSave = preview.getRequestGeneration();
  const snapBeforePreviewSave = snapshot();
  const pSave = document.querySelector("[data-design-preview-save]");
  if (pSave && !pSave.disabled) {
    pSave.click();
    for (let i = 0; i < 80; i++) {
      if (ss.getStatus() === "saved" || ss.getStatus() === "error") break;
      await sleep(100);
    }
    // Wait for post-save refresh to finish (render status ready or error)
    for (let i = 0; i < 80; i++) {
      const rs =
        typeof preview.getRenderStatus === "function"
          ? preview.getRenderStatus()
          : null;
      const img = document.querySelector("[data-design-preview-img]");
      const src = img && img.getAttribute("src");
      if (ss.getStatus() === "error") break;
      if (
        ss.getStatus() === "saved" &&
        !ss.isDirty() &&
        (rs === "ready" || rs === "error") &&
        preview.getRequestGeneration() > genBeforeSave &&
        isPreviewSrc(src) &&
        src !== srcBeforeSave
      ) {
        break;
      }
      await sleep(100);
    }
  }
  const imgAfterSave = document.querySelector("[data-design-preview-img]");
  const srcAfterSave = imgAfterSave && imgAfterSave.getAttribute("src");
  const honestyAfterSave = document.querySelector(
    "[data-design-preview-honesty]"
  );
  const renderStatus =
    typeof preview.getRenderStatus === "function"
      ? preview.getRenderStatus()
      : null;
  step("preview_save_path", {
    ok: ss.getStatus() === "saved" && !ss.isDirty(),
    status: ss.getStatus(),
  });
  step("post_save_image_refresh_while_open", {
    ok:
      preview.isOpen() &&
      ss.getStatus() === "saved" &&
      !ss.isDirty() &&
      preview.getRequestGeneration() > genBeforeSave &&
      isPreviewSrc(srcAfterSave) &&
      srcAfterSave !== srcBeforeSave &&
      renderStatus === "ready" &&
      honestyAfterSave &&
      /Matches the last successful save/i.test(
        honestyAfterSave.textContent || ""
      ),
    genBefore: genBeforeSave,
    genAfter: preview.getRequestGeneration(),
    srcChanged: srcAfterSave !== srcBeforeSave,
    renderStatus: renderStatus,
    modalOpen: preview.isOpen(),
    honesty: honestyAfterSave && honestyAfterSave.textContent,
  });
  const afterPreviewSave = snapshot();
  step("no_mutation_after_preview_save_refresh", {
    ok: sameSnap(snapBeforePreviewSave, afterPreviewSave, [
      "view",
      "title",
      "garment",
      "objCount",
    ]) &&
      afterPreviewSave.dirty === false &&
      afterPreviewSave.status === "saved",
    before: snapBeforePreviewSave,
    after: afterPreviewSave,
  });

  // Already-saved Preview Save must not start another save
  const statusBeforeNoop = ss.getStatus();
  const genBeforeNoop = preview.getRequestGeneration();
  if (pSave) pSave.click();
  await sleep(200);
  step("already_saved_no_unnecessary_save", {
    ok:
      ss.getStatus() === statusBeforeNoop &&
      ss.getStatus() === "saved" &&
      !ss.isSaveInFlight() &&
      preview.getRequestGeneration() === genBeforeNoop,
    status: ss.getStatus(),
    genBefore: genBeforeNoop,
    genAfter: preview.getRequestGeneration(),
  });
  preview.close();

  // Narrow viewport smoke (~390px)
  const prevW = window.innerWidth;
  try {
    // Visual CSS presence — cannot reliably resize Chromium via evaluate alone
    const cssOk = !!document.querySelector(".design-preview-frame");
    step("narrow_css_present", {
      ok: cssOk,
      note: "Layout at ~390px verified separately in browser QA when viewport is set",
      innerWidth: prevW,
    });
  } catch (e) {
    step("narrow_css_present", { ok: false, error: String(e) });
  }

  // Regression: Stage G APIs intact; no payment completed
  step("stage_g_intact", {
    ok:
      typeof ss.getSubmissionReadiness === "function" &&
      typeof ss.shouldWarnUnload === "function",
  });
  step("payment_modal_closed", {
    ok: !(
      document.getElementById("payment-modal") &&
      document.getElementById("payment-modal").classList.contains("flex")
    ),
  });

  return report;
})();
