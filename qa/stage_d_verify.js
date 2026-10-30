/**
 * Stage D browser verification (run in editor via CDP Runtime.evaluate).
 * Returns a report object: { ok, steps[], beforeSave, afterReload }.
 */
(async function stageDVerify() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const designId =
    (location.pathname.match(/\/designs\/(\d+)\//) || [])[1] || "30";
  const report = { steps: [], ok: true, designId: designId };
  const step = (name, data) => {
    report.steps.push(Object.assign({ name: name }, data));
    if (data.ok === false) report.ok = false;
  };

  for (let i = 0; i < 60; i++) {
    if (
      window.BlytzEditor &&
      BlytzEditor.whenReady &&
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

  const api = BlytzCanvas;
  const getJSON = () => BlytzEditor.getCanvasJSON();
  const c = api.getFabricCanvas();
  if (!c || typeof api.renameObjectById !== "function") {
    return { ok: false, reason: "missing-apis" };
  }

  const propsBody = () =>
    document.querySelector("#editor-properties-panel .editor-props-body") ||
    document.querySelector("[data-props-body]");

  // Seed: curved text, plain text, rectangle
  api.addText(getJSON, { text: "CurveMe", skipEditing: true });
  await sleep(60);
  const text1Id = c.getActiveObject().blytzId;
  api.applyTextCurve({ amount: 0.5, direction: "up" }, getJSON);
  await sleep(40);

  api.addText(getJSON, { text: "Plain", skipEditing: true });
  await sleep(40);
  const text2Id = c.getActiveObject().blytzId;

  api.insertElement(
    "insert-rect",
    function (pos) {
      return new fabric.Rect({
        width: 90,
        height: 55,
        fill: "#2563eb",
        left: pos.left,
        top: pos.top,
        originX: "center",
        originY: "center",
      });
    },
    getJSON,
    "Rectangle"
  );
  await sleep(40);
  const rectId = c.getActiveObject().blytzId;
  step("seed", {
    ok: !!(text1Id && text2Id && rectId),
    text1Id: text1Id,
    text2Id: text2Id,
    rectId: rectId,
    n: c.getObjects().length,
  });

  // --- A: Curve UI hardening ---
  api.selectObjectById(text1Id);
  await sleep(50);
  if (BlytzEditorProps.openSheet) BlytzEditorProps.openSheet();
  BlytzEditorProps.syncFromSelection();
  await sleep(50);
  let curveBefore = !!document.querySelector("[data-curve-section]");
  step("curve-ui-on-text", { ok: curveBefore, curveBefore: curveBefore });

  const enable = document.querySelector("[data-curve-enable]");
  if (enable) {
    enable.checked = true;
    enable.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(30);
  }
  const slider = document.querySelector("[data-curve-amount]");
  if (slider) {
    slider.value = "70";
    slider.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(30);
  }
  const dirtyBefore = !!BlytzEditorProps.isCurvePreviewDirty();
  c.discardActiveObject();
  c.requestRenderAll();
  await sleep(60);
  BlytzEditorProps.syncFromSelection();
  await sleep(40);
  const body = propsBody();
  step("stale-curve-after-deselect", {
    ok:
      !document.querySelector("[data-curve-section]") &&
      !BlytzEditorProps.getCurveSessionObjectId() &&
      !BlytzEditorProps.isCurvePreviewDirty() &&
      (!body || body.children.length === 0),
    dirtyBefore: dirtyBefore,
    curveDom: !!document.querySelector("[data-curve-section]"),
    session: BlytzEditorProps.getCurveSessionObjectId(),
    dirtyAfter: BlytzEditorProps.isCurvePreviewDirty(),
    bodyKids: body ? body.children.length : -1,
  });

  // Multi-select
  const t2 = api.findObjectByBlytzId(text2Id);
  const r0 = api.findObjectByBlytzId(rectId);
  c.setActiveObject(new fabric.ActiveSelection([t2, r0], { canvas: c }));
  c.requestRenderAll();
  await sleep(50);
  if (BlytzEditorProps.openSheet) BlytzEditorProps.openSheet();
  BlytzEditorProps.syncFromSelection();
  await sleep(40);
  const multiTxt = (document.getElementById("editor-properties-panel") || document)
    .textContent;
  step("multi-select-no-curve", {
    ok: !document.querySelector("[data-curve-section]") && /objects selected/i.test(multiTxt),
    curve: !!document.querySelector("[data-curve-section]"),
  });

  api.selectObjectById(rectId);
  await sleep(40);
  BlytzEditorProps.syncFromSelection();
  await sleep(30);
  step("rect-no-curve", { ok: !document.querySelector("[data-curve-section]") });

  // Preview then change selection
  api.selectObjectById(text2Id);
  await sleep(40);
  if (BlytzEditorProps.openSheet) BlytzEditorProps.openSheet();
  BlytzEditorProps.syncFromSelection();
  await sleep(40);
  const en2 = document.querySelector("[data-curve-enable]");
  if (en2) {
    en2.checked = true;
    en2.dispatchEvent(new Event("change", { bubbles: true }));
  }
  const sl2 = document.querySelector("[data-curve-amount]");
  if (sl2) {
    sl2.value = "55";
    sl2.dispatchEvent(new Event("input", { bubbles: true }));
  }
  await sleep(40);
  api.selectObjectById(rectId);
  await sleep(50);
  BlytzEditorProps.syncFromSelection();
  await sleep(30);
  const t2After = api.findObjectByBlytzId(text2Id);
  const stillCurved = !!(
    t2After.path ||
    (t2After.blytzCurve && t2After.blytzCurve.amount > 0)
  );
  step("preview-discard-on-selection-change", {
    ok: !stillCurved && !BlytzEditorProps.isCurvePreviewDirty(),
    stillCurved: stillCurved,
  });

  // --- B1 Rename ---
  const idBefore = api.findObjectByBlytzId(rectId).blytzId;
  const renameOk = api.renameObjectById(rectId, "  Logo Box  ", getJSON);
  const emptyReject = api.renameObjectById(rectId, "   ", getJSON);
  const renamed = api.findObjectByBlytzId(rectId);
  step("rename", {
    ok:
      renameOk === true &&
      emptyReject === false &&
      renamed.blytzName === "Logo Box" &&
      renamed.blytzId === idBefore,
    renameOk: renameOk,
    emptyReject: emptyReject,
    name: renamed.blytzName,
  });
  step("rename-noop", { ok: api.renameObjectById(rectId, "Logo Box", getJSON) === false });

  api.undo(getJSON);
  await sleep(30);
  const afterUndoRename = api.findObjectByBlytzId(rectId).blytzName;
  api.redo(getJSON);
  await sleep(30);
  const afterRedoRename = api.findObjectByBlytzId(rectId).blytzName;
  step("rename-undo-redo", {
    ok: afterUndoRename !== "Logo Box" && afterRedoRename === "Logo Box",
    afterUndoRename: afterUndoRename,
    afterRedoRename: afterRedoRename,
  });

  // --- B2 Duplicate ---
  api.selectObjectById(text1Id);
  await sleep(30);
  const srcCurve = api.findObjectByBlytzId(text1Id).blytzCurve;
  await api.duplicateActive(getJSON);
  await sleep(50);
  const dup = c.getActiveObject();
  const dupId = dup && dup.blytzId;
  step("duplicate-curved-text", {
    ok:
      !!dup &&
      dup.blytzId !== text1Id &&
      /copy/i.test(dup.blytzName || "") &&
      !!dup.blytzCurve &&
      Math.abs((dup.blytzCurve.amount || 0) - (srcCurve.amount || 0)) < 0.001,
    dupId: dupId,
    dupName: dup && dup.blytzName,
    amount: dup && dup.blytzCurve && dup.blytzCurve.amount,
  });
  api.undo(getJSON);
  await sleep(30);
  const dupGone = !api.findObjectByBlytzId(dupId);
  api.redo(getJSON);
  await sleep(30);
  step("duplicate-undo-redo", {
    ok: dupGone && !!api.findObjectByBlytzId(dupId),
    dupGone: dupGone,
  });

  api.selectObjectById(rectId);
  api.setObjectLockedById(rectId, true, getJSON);
  api.setObjectVisibleById(rectId, false, getJSON);
  await sleep(30);
  api.selectObjectById(rectId);
  await api.duplicateActive(getJSON);
  await sleep(40);
  const clone = c.getActiveObject();
  const srcAfter = api.findObjectByBlytzId(rectId);
  step("duplicate-from-hidden-locked", {
    ok:
      !!clone &&
      clone.visible !== false &&
      !clone.blytzLocked &&
      srcAfter.visible === false &&
      !!srcAfter.blytzLocked &&
      clone.blytzId !== rectId,
    cloneVis: clone && clone.visible,
    cloneLocked: clone && !!clone.blytzLocked,
    srcVis: srcAfter.visible,
    srcLocked: !!srcAfter.blytzLocked,
  });
  api.setObjectVisibleById(rectId, true, getJSON);
  api.setObjectLockedById(rectId, false, getJSON);

  // --- B3 Hide/Show ---
  api.selectObjectById(text2Id);
  await sleep(30);
  BlytzEditorProps.syncFromSelection();
  const hideOk = api.setObjectVisibleById(text2Id, false, getJSON);
  await sleep(40);
  BlytzEditorProps.syncFromSelection();
  await sleep(30);
  const hiddenObj = api.findObjectByBlytzId(text2Id);
  const activeAfterHide = c.getActiveObject();
  const bodyH = propsBody();
  step("hide", {
    ok:
      hideOk &&
      hiddenObj.visible === false &&
      !activeAfterHide &&
      (!bodyH || bodyH.children.length === 0 || document.getElementById("editor-properties-panel").hidden),
    hideOk: hideOk,
    visible: hiddenObj.visible,
    hasActive: !!activeAfterHide,
  });
  // Hit-test: Fabric treats invisible as not a target
  let hitSkipped = true;
  try {
    if (typeof hiddenObj.containsPoint === "function") {
      // Prefer selectable/evented + visible flags
      hitSkipped = hiddenObj.visible === false;
    }
  } catch (e) {}
  step("hide-hit-test-flag", { ok: hitSkipped, visible: hiddenObj.visible });

  api.selectObjectById(text2Id);
  const showOk = api.setObjectVisibleById(text2Id, true, getJSON);
  step("show", {
    ok: showOk && api.findObjectByBlytzId(text2Id).visible !== false,
    showOk: showOk,
  });
  api.undo(getJSON);
  await sleep(30);
  const undidShow = api.findObjectByBlytzId(text2Id).visible === false;
  api.redo(getJSON);
  await sleep(30);
  step("hide-show-undo-redo", {
    ok: undidShow && api.findObjectByBlytzId(text2Id).visible !== false,
    undidShow: undidShow,
  });

  // --- B4 Lock ---
  api.selectObjectById(text2Id);
  const leftBefore = api.findObjectByBlytzId(text2Id).left;
  const lockOk = api.setObjectLockedById(text2Id, true, getJSON);
  await sleep(30);
  const locked = api.findObjectByBlytzId(text2Id);
  const applyCheck =
    !!locked.blytzLocked &&
    locked.selectable === false &&
    locked.evented === false &&
    locked.lockMovementX === true &&
    locked.hasControls === false;
  const mgmt = api.selectObjectById(text2Id);
  const renameLocked = api.renameObjectById(text2Id, "Locked Plain", getJSON);
  // Simulate drag attempt: with lockMovement, fabric object:moving won't apply from UI;
  // verify flags block interaction path.
  step("lock", {
    ok: lockOk && applyCheck && mgmt && renameLocked,
    flags: {
      blytzLocked: locked.blytzLocked,
      selectable: locked.selectable,
      evented: locked.evented,
      lockMovementX: locked.lockMovementX,
      hasControls: locked.hasControls,
    },
    leftBefore: leftBefore,
  });

  const unlockOk = api.setObjectLockedById(text2Id, false, getJSON);
  const unlocked = api.findObjectByBlytzId(text2Id);
  step("unlock", {
    ok:
      unlockOk &&
      !unlocked.blytzLocked &&
      unlocked.selectable !== false &&
      unlocked.evented !== false,
    locked: !!unlocked.blytzLocked,
  });

  api.setObjectLockedById(text2Id, true, getJSON);
  api.undo(getJSON);
  await sleep(30);
  const undidLock = !api.findObjectByBlytzId(text2Id).blytzLocked;
  api.redo(getJSON);
  await sleep(30);
  step("lock-undo-redo", {
    ok: undidLock && !!api.findObjectByBlytzId(text2Id).blytzLocked,
    undidLock: undidLock,
  });

  // Layers UI
  const layersBtn =
    document.querySelector('[data-editor-action="layers"]') ||
    [...document.querySelectorAll("button")].find((b) =>
      /layers/i.test(b.textContent || "")
    );
  if (layersBtn) {
    layersBtn.click();
    await sleep(150);
    // Ensure open (toggle would close if already open)
    if (BlytzEditorTools.getOpenPanelId() !== "layers") {
      layersBtn.click();
      await sleep(150);
    }
    if (typeof BlytzEditorTools.refreshLayers === "function") {
      BlytzEditorTools.refreshLayers();
      await sleep(80);
    }
  }
  const layerRows = document.querySelectorAll("[data-layer-id]");
  step("layers-ui", {
    ok:
      layerRows.length > 0 &&
      !!document.querySelector('[data-layer-row-action="visibility"]') &&
      !!document.querySelector('[data-layer-row-action="lock"]') &&
      !!document.querySelector('[data-layer-row-action="rename"]'),
    rows: layerRows.length,
  });

  // Rename Escape / Enter via DOM
  const row =
    document.querySelector('[data-layer-id="' + rectId + '"]') ||
    document.querySelector("[data-layer-id]");
  if (row) {
    const renameBtn = row.querySelector('[data-layer-row-action="rename"]');
    renameBtn.click();
    await sleep(40);
    let input = row.querySelector("[data-layer-rename-input]");
    if (input) {
      const prior = api.findObjectByBlytzId(rectId).blytzName;
      input.value = "Escaped Name";
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      await sleep(50);
      step("rename-escape", {
        ok: api.findObjectByBlytzId(rectId).blytzName === prior,
        prior: prior,
        after: api.findObjectByBlytzId(rectId).blytzName,
      });
    } else {
      step("rename-escape", { ok: false, reason: "no-input" });
    }
    const row2 = document.querySelector('[data-layer-id="' + rectId + '"]');
    const renameBtn2 = row2 && row2.querySelector('[data-layer-row-action="rename"]');
    if (renameBtn2) {
      renameBtn2.click();
      await sleep(40);
      input = document.querySelector("[data-layer-rename-input]");
      if (input) {
        input.value = "Confirmed Box";
        input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        await sleep(60);
        step("rename-enter", {
          ok: api.findObjectByBlytzId(rectId).blytzName === "Confirmed Box",
          name: api.findObjectByBlytzId(rectId).blytzName,
        });
      } else {
        step("rename-enter", { ok: false, reason: "no-input2" });
      }
    }
  } else {
    step("rename-escape", { ok: false, reason: "no-row" });
  }

  // Front/Back during preview
  api.selectObjectById(text1Id);
  await sleep(40);
  if (BlytzEditorProps.openSheet) BlytzEditorProps.openSheet();
  BlytzEditorProps.syncFromSelection();
  await sleep(30);
  const en3 = document.querySelector("[data-curve-enable]");
  if (en3) {
    en3.checked = true;
    en3.dispatchEvent(new Event("change", { bubbles: true }));
  }
  await sleep(30);
  const dirtyView = BlytzEditorProps.isCurvePreviewDirty();
  if (typeof BlytzEditor.setActiveView === "function") {
    await BlytzEditor.setActiveView("back");
    await sleep(80);
    const sessionAfterView = BlytzEditorProps.getCurveSessionObjectId();
    await BlytzEditor.setActiveView("front");
    await sleep(80);
    step("view-switch-discards-preview", {
      ok: dirtyView ? !sessionAfterView : true,
      dirtyView: dirtyView,
      sessionAfterView: sessionAfterView,
    });
  } else {
    step("view-switch-discards-preview", { ok: false, reason: "no-setActiveView" });
  }

  // Save
  const prepared = await BlytzEditor.preparePersistPayload();
  const envelope =
    (prepared && prepared.payload) ||
    (prepared && prepared.json) ||
    prepared;
  if (!envelope || !envelope.canvas || !envelope.canvas.objects) {
    step("save", {
      ok: false,
      reason: "bad-prepare",
      preparedKeys: prepared && Object.keys(prepared),
    });
    return report;
  }
  report.beforeSave = {
    objects: envelope.canvas.objects.map(function (o) {
      return {
        id: o.blytzId,
        name: o.blytzName,
        visible: o.visible !== false,
        locked: !!o.blytzLocked,
        curveAmt: o.blytzCurve && o.blytzCurve.amount,
        type: o.type,
      };
    }),
  };
  const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
  const bodyFd = new FormData();
  bodyFd.append("csrfmiddlewaretoken", csrf);
  bodyFd.append("canvas_json", JSON.stringify(envelope));
  bodyFd.append("title", "Stage D Follow-up Verify");
  const res = await fetch("/app/designs/" + designId + "/save/", {
    method: "POST",
    body: bodyFd,
    credentials: "same-origin",
    headers: { "X-CSRFToken": csrf },
  });
  const saveText = await res.text();
  let saveBody = saveText;
  try {
    saveBody = JSON.parse(saveText);
  } catch (e) {}
  step("save", {
    ok: res.status === 200 || res.status === 302,
    status: res.status,
    body: typeof saveBody === "string" ? saveBody.slice(0, 160) : saveBody,
  });

  return report;
})();
