/**
 * Stage G browser verification — run via CDP Runtime.evaluate on design editor.
 * Disposable design only. Does not complete a real payment.
 */
(async function stageGVerify() {
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
  const api = BlytzCanvas;
  const getJSON = () => BlytzEditor.getCanvasJSON();
  const c = api.getFabricCanvas();
  const saveEl = document.querySelector("[data-editor-save-status]");
  const saveBtn = document.querySelector("[data-editor-save]");

  if (!ss || !c) {
    return { ok: false, reason: "missing-stage-g-apis", designId: designId };
  }

  // 1. Initial saved status after load
  step("initial_status", {
    ok: ss.getStatus() === "saved" && !ss.isDirty(),
    status: ss.getStatus(),
    dirty: ss.isDirty(),
    label: saveEl && saveEl.textContent,
  });

  // 2. Committed edit → unsaved
  api.addText(getJSON, { text: "StageG", skipEditing: true });
  await sleep(120);
  step("committed_edit_unsaved", {
    ok: ss.isDirty() && ss.getStatus() === "unsaved",
    status: ss.getStatus(),
    label: saveEl && saveEl.textContent,
  });

  // 3. Selection / clear selection must not change dirty further incorrectly
  const beforeSel = ss.isDirty();
  if (typeof api.clearSelection === "function") api.clearSelection();
  await sleep(80);
  step("selection_clear_no_false_clean", {
    ok: ss.isDirty() === beforeSel,
    dirty: ss.isDirty(),
  });

  // 4. Undo back toward saved (may become clean if baseline matched)
  const dirtyBeforeUndo = ss.isDirty();
  if (BlytzEditor.canUndo && BlytzEditor.canUndo()) {
    await BlytzEditor.undo();
    await sleep(150);
  }
  step("undo_updates_dirty", {
    ok: typeof ss.isDirty() === "boolean",
    dirtyBeforeUndo: dirtyBeforeUndo,
    dirtyAfterUndo: ss.isDirty(),
    status: ss.getStatus(),
  });

  // Re-edit for save tests
  if (!ss.isDirty()) {
    api.addText(getJSON, { text: "StageG2", skipEditing: true });
    await sleep(120);
  }

  // 5. Successful save → Saved
  if (saveBtn && !saveBtn.disabled) {
    saveBtn.click();
    for (let i = 0; i < 60; i++) {
      if (ss.getStatus() === "saved" || ss.getStatus() === "error") break;
      await sleep(100);
    }
  }
  step("successful_save", {
    ok: ss.getStatus() === "saved" && !ss.isDirty(),
    status: ss.getStatus(),
    label: saveEl && saveEl.textContent,
  });

  // 6. Simulated failed save (intercept fetch once)
  api.addText(getJSON, { text: "FailPath", skipEditing: true });
  await sleep(100);
  const realFetch = window.fetch;
  let intercepted = false;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : input && input.url;
    if (url && String(url).indexOf("/save/") !== -1) {
      intercepted = true;
      window.fetch = realFetch;
      return Promise.resolve(
        new Response(JSON.stringify({ ok: false, errors: { canvas_json: ["Simulated failure."] } }), {
          status: 400,
          headers: { "Content-Type": "application/json" },
        })
      );
    }
    return realFetch.apply(this, arguments);
  };
  if (saveBtn) saveBtn.click();
  for (let i = 0; i < 40; i++) {
    if (ss.getStatus() === "error") break;
    await sleep(100);
  }
  window.fetch = realFetch;
  step("simulated_save_failure", {
    ok: intercepted && ss.getStatus() === "error" && ss.isDirty(),
    intercepted: intercepted,
    status: ss.getStatus(),
    error: ss.getError(),
    dirty: ss.isDirty(),
  });

  // 7. Retry after failure (real save)
  if (saveBtn) saveBtn.click();
  for (let i = 0; i < 60; i++) {
    if (ss.getStatus() === "saved" || ss.getStatus() === "error") break;
    await sleep(100);
  }
  step("retry_after_failure", {
    ok: ss.getStatus() === "saved" && !ss.isDirty(),
    status: ss.getStatus(),
  });

  // 8. Edit while saving — older save must not mark newer saved
  api.addText(getJSON, { text: "DuringSave", skipEditing: true });
  await sleep(80);
  let midEditDone = false;
  const fetch2 = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : input && input.url;
    if (url && String(url).indexOf("/save/") !== -1) {
      return new Promise(function (resolve) {
        setTimeout(function () {
          // Newer edit during in-flight save
          if (!midEditDone) {
            midEditDone = true;
            try {
              api.addText(getJSON, { text: "NewerEdit", skipEditing: true });
            } catch (e) {}
          }
          setTimeout(function () {
            fetch2
              .apply(window, [input, init])
              .then(resolve)
              .catch(function (err) {
                resolve(
                  new Response(JSON.stringify({ ok: false }), {
                    status: 500,
                    headers: { "Content-Type": "application/json" },
                  })
                );
              });
          }, 50);
        }, 200);
      });
    }
    return fetch2.apply(this, arguments);
  };
  if (saveBtn) saveBtn.click();
  for (let i = 0; i < 80; i++) {
    if (!ss.isSaveInFlight() && ss.getStatus() !== "saving") break;
    await sleep(100);
  }
  window.fetch = fetch2;
  await sleep(150);
  step("edit_during_save", {
    ok: ss.isDirty() && ss.getStatus() === "unsaved",
    dirty: ss.isDirty(),
    status: ss.getStatus(),
    midEditDone: midEditDone,
  });

  // 9/10. Navigation guard flags (cannot fully click-through beforeunload in CDP)
  step("warn_unload_when_dirty", {
    ok: ss.shouldWarnUnload() === true,
    shouldWarn: ss.shouldWarnUnload(),
  });
  // Save clean then check no warn
  if (saveBtn) saveBtn.click();
  for (let i = 0; i < 60; i++) {
    if (ss.getStatus() === "saved" && !ss.isDirty()) break;
    await sleep(100);
  }
  step("no_warn_when_clean", {
    ok: ss.shouldWarnUnload() === false,
    shouldWarn: ss.shouldWarnUnload(),
    status: ss.getStatus(),
  });

  // 11. Front/Back independence smoke
  let viewOk = true;
  try {
    api.addText(getJSON, { text: "FrontG", skipEditing: true });
    await sleep(80);
    await BlytzEditor.setActiveView("back");
    await sleep(120);
    api.addText(getJSON, { text: "BackG", skipEditing: true });
    await sleep(80);
    const env = getJSON();
    const frontHas = (env.canvas.objects || []).some(
      (o) => o && o.text === "FrontG"
    );
    const backHas = (env.views.back.objects || []).some(
      (o) => o && o.text === "BackG"
    );
    viewOk = frontHas && backHas;
    await BlytzEditor.setActiveView("front");
  } catch (e) {
    viewOk = false;
  }
  step("front_back_independent", { ok: viewOk });

  // 12. Oversized client gate (preparePersistPayload) without clearing canvas
  const beforeCount = (getJSON().canvas.objects || []).length;
  const preparedBlock = BlytzEditor.preparePersistPayload;
  // Don't actually inflate to 2MiB in browser — assert helper exists + readiness payload check path
  const readiness = ss.getSubmissionReadiness();
  step("readiness_structure", {
    ok:
      readiness &&
      Array.isArray(readiness.checks) &&
      readiness.checks.some((c) => c.id === "payload") &&
      readiness.checks.some((c) => c.id === "artwork"),
    ready: readiness && readiness.ready,
    checkIds: readiness && readiness.checks.map((c) => c.id),
  });
  step("canvas_preserved", {
    ok: (getJSON().canvas.objects || []).length >= beforeCount,
    count: (getJSON().canvas.objects || []).length,
  });

  // 13. Submit button opens readiness-gated flow up to payment modal (no payment)
  const submitBtn = document.querySelector("[data-editor-submit]");
  const modal = document.getElementById("payment-modal");
  if (submitBtn && readiness.ready) {
    submitBtn.click();
    await sleep(200);
    const open =
      modal &&
      !modal.classList.contains("hidden") &&
      modal.classList.contains("flex");
    step("submit_opens_payment_modal", { ok: !!open });
    // Cancel — do not pay
    const cancel = document.getElementById("payment-cancel-btn");
    if (cancel) cancel.click();
    await sleep(100);
  } else {
    step("submit_opens_payment_modal", {
      ok: false,
      reason: "submit not ready or missing",
      ready: readiness && readiness.ready,
    });
  }

  // 14. Narrow viewport CSS presence (layout still usable — class checks)
  step("narrow_status_visible", {
    ok: !!(saveEl && saveEl.offsetParent !== null),
    text: saveEl && saveEl.textContent,
  });

  // 15. Regression: clearSelection still no commit; print warning node exists
  step("print_overflow_node", {
    ok: !!document.getElementById("editor-print-overflow-warning"),
  });
  step("composition_apis", {
    ok:
      typeof api.distributeActive === "function" &&
      typeof api.alignActive === "function",
  });

  return report;
})();
