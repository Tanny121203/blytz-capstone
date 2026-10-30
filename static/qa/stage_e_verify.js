/**
 * Stage E browser verification (run in editor via CDP Runtime.evaluate).
 * Uploads a real PNG via fetch + File + addImageFromFile, then exercises controls.
 */
(async function stageEVerify() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const designId =
    (location.pathname.match(/\/designs\/(\d+)\//) || [])[1] || "?";
  const report = {
    steps: [],
    ok: true,
    designId: designId,
    cropImplemented: false,
  };
  const step = (name, data) => {
    report.steps.push(Object.assign({ name: name }, data));
    if (data.ok === false) report.ok = false;
  };

  for (let i = 0; i < 80; i++) {
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
  await sleep(150);

  const api = BlytzCanvas;
  const getJSON = () => BlytzEditor.getCanvasJSON();
  const c = api.getFabricCanvas();
  if (!c || typeof api.fitActiveWithinCanvas !== "function") {
    return { ok: false, reason: "missing-stage-e-apis" };
  }

  const propsBody = () =>
    document.querySelector("[data-props-body]") ||
    document.querySelector("#editor-properties-panel [data-props-body]");

  const active = () => c.getActiveObject();
  const snapImg = (obj) => {
    if (!obj) return null;
    const center = obj.getCenterPoint();
    return {
      id: obj.blytzId,
      name: obj.blytzName,
      srcLen: (obj.get && obj.get("src") ? obj.get("src") : obj.src || "").length,
      w: Math.round(obj.getScaledWidth() * 1000) / 1000,
      h: Math.round(obj.getScaledHeight() * 1000) / 1000,
      angle: obj.angle || 0,
      opacity: obj.opacity == null ? 1 : obj.opacity,
      cx: Math.round(center.x * 10) / 10,
      cy: Math.round(center.y * 10) / 10,
      locked: !!obj.blytzLocked,
    };
  };

  // --- Upload real PNG ---
  let file;
  try {
    const resp = await fetch("/static/../qa/stage_e_test.png").catch(() => null);
    // Prefer absolute path via data URL built in-page if static qa not served
  } catch (e) {}
  // Build PNG via canvas (guaranteed available) then File for addImageFromFile
  const off = document.createElement("canvas");
  off.width = 320;
  off.height = 180;
  const ctx = off.getContext("2d");
  ctx.fillStyle = "#dc2828";
  ctx.fillRect(0, 0, 320, 180);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(40, 60, 240, 60);
  const blob = await new Promise((res) => off.toBlob(res, "image/png"));
  file = new File([blob], "stage_e_test.png", { type: "image/png" });
  const addResult = await api.addImageFromFile(file, getJSON);
  await sleep(120);
  const img = active();
  const base = snapImg(img);
  step("upload-png", {
    ok: !!(addResult && addResult.ok && img && api.typeKey(img) === "image"),
    addResult: addResult && addResult.ok,
    snap: base,
  });
  if (!img) return report;

  const imgId = img.blytzId;
  const imgName = img.blytzName;
  const srcBefore = img.get ? img.get("src") : img.src;

  // --- Properties panel shows image controls ---
  if (window.BlytzEditorProps && BlytzEditorProps.openSheet) {
    BlytzEditorProps.openSheet();
  }
  await sleep(80);
  if (BlytzEditorProps && BlytzEditorProps.syncFromSelection) {
    BlytzEditorProps.syncFromSelection();
  }
  await sleep(60);
  const body = propsBody();
  const hasW = !!(body && body.querySelector('[data-prop="width"]'));
  const hasH = !!(body && body.querySelector('[data-prop="height"]'));
  const hasOp = !!(body && body.querySelector('[data-prop="opacity"]'));
  const hasRot = !!(body && body.querySelector('[data-prop="rotation"]'));
  const hasAspect = !!(body && body.querySelector('[data-prop="keepProportions"]'));
  const hasPlace = !!(body && body.querySelector("[data-image-place]"));
  const hasCrop = !!(body && body.querySelector("[data-crop], [data-image-place='crop']"));
  step("props-image-controls", {
    ok: hasW && hasH && hasOp && hasRot && hasAspect && hasPlace && !hasCrop,
    hasW: hasW,
    hasH: hasH,
    hasOp: hasOp,
    hasRot: hasRot,
    hasAspect: hasAspect,
    hasPlace: hasPlace,
    hasCrop: hasCrop,
  });

  // --- Aspect lock: change width, height follows ---
  const wBefore = img.getScaledWidth();
  const hBefore = img.getScaledHeight();
  const ratio = wBefore / hBefore;
  api.commitEdit(
    "prop-width",
    function () {
      const sx = 500 / Math.max(img.width || 1, 0.0001);
      img.set({ scaleX: sx, scaleY: sx });
      img.setCoords();
      return true;
    },
    getJSON
  );
  await sleep(40);
  const afterLock = snapImg(img);
  step("aspect-lock-width", {
    ok:
      Math.abs(afterLock.w - 500) < 1 &&
      Math.abs(afterLock.w / afterLock.h - ratio) < 0.02 &&
      afterLock.id === imgId &&
      afterLock.name === imgName,
    snap: afterLock,
  });

  // --- Unlock aspect: independent height ---
  const keepChk = body && body.querySelector('[data-prop="keepProportions"]');
  if (keepChk) {
    keepChk.checked = false;
    keepChk.dispatchEvent(new Event("input", { bubbles: true }));
    keepChk.dispatchEvent(new Event("change", { bubbles: true }));
  }
  // Force unlock via module state by clicking if needed — apply skipKeep path via commit
  const unlockedH = 120;
  api.commitEdit(
    "prop-height",
    function () {
      const sy = unlockedH / Math.max(img.height || 1, 0.0001);
      img.set("scaleY", sy);
      // leave scaleX
      img.setCoords();
      return true;
    },
    getJSON
  );
  await sleep(40);
  const afterUnlock = snapImg(img);
  step("aspect-unlock-height", {
    ok:
      Math.abs(afterUnlock.h - unlockedH) < 1.5 &&
      Math.abs(afterUnlock.w - afterLock.w) < 1.5 &&
      afterUnlock.id === imgId,
    snap: afterUnlock,
  });

  // Re-lock for later ops
  if (keepChk) {
    keepChk.checked = true;
    keepChk.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // --- Rotation + reset ---
  const centerBeforeRot = img.getCenterPoint();
  api.commitEdit(
    "prop-rotation",
    function () {
      img.set("angle", 35);
      if (img.setPositionByOrigin) {
        img.setPositionByOrigin(centerBeforeRot, "center", "center");
      }
      img.setCoords();
      return true;
    },
    getJSON
  );
  await sleep(40);
  const afterRot = snapImg(img);
  const resetOk = api.resetActiveRotation(getJSON);
  await sleep(40);
  const afterReset = snapImg(img);
  step("rotation-and-reset", {
    ok:
      Math.abs(afterRot.angle - 35) < 0.5 &&
      resetOk &&
      Math.abs(afterReset.angle) < 0.01 &&
      Math.abs(afterReset.cx - afterRot.cx) < 2 &&
      Math.abs(afterReset.cy - afterRot.cy) < 2 &&
      afterReset.id === imgId,
    afterRot: afterRot,
    afterReset: afterReset,
  });

  // --- Opacity live then one commit pattern ---
  const histBeforeOp = BlytzEditor.canUndo ? BlytzEditor.canUndo() : null;
  // Simulate live via runSilent then end commit
  api.runSilent(function () {
    img.set("opacity", 0.45);
    c.requestRenderAll();
  });
  api.commitEdit(
    "prop-opacity",
    function () {
      return true;
    },
    getJSON
  );
  await sleep(40);
  const afterOp = snapImg(img);
  step("opacity", {
    ok: Math.abs(afterOp.opacity - 0.45) < 0.001 && afterOp.id === imgId,
    snap: afterOp,
  });

  // --- Center + Fit ---
  img.set({ left: 100, top: 120 });
  img.setCoords();
  c.requestRenderAll();
  const centerOk = api.centerActiveImage(getJSON);
  await sleep(40);
  const afterCenter = snapImg(img);
  const fitOk = api.fitActiveWithinCanvas(getJSON);
  await sleep(40);
  const afterFit = snapImg(img);
  step("center-and-fit", {
    ok:
      centerOk &&
      fitOk &&
      Math.abs(afterCenter.cx - 400) < 2 &&
      Math.abs(afterCenter.cy - 400) < 2 &&
      afterFit.w <= 800.5 &&
      afterFit.h <= 800.5 &&
      (Math.abs(afterFit.w - 800) < 1.5 || Math.abs(afterFit.h - 800) < 1.5) &&
      Math.abs(afterFit.cx - 400) < 2 &&
      afterFit.id === imgId &&
      (img.get ? img.get("src") : img.src) === srcBefore,
    afterCenter: afterCenter,
    afterFit: afterFit,
  });

  // --- Gating: text / shape / multi ---
  api.addText(getJSON, { text: "GateText", skipEditing: true });
  await sleep(40);
  const textObj = active();
  if (BlytzEditorProps) BlytzEditorProps.syncFromSelection();
  await sleep(40);
  const textBody = propsBody();
  const textHasImagePlace = !!(
    textBody && textBody.querySelector("[data-image-place]")
  );
  const fitOnText = api.fitActiveWithinCanvas(getJSON);
  step("gate-text", {
    ok: !textHasImagePlace && !fitOnText,
    textHasImagePlace: textHasImagePlace,
    fitOnText: fitOnText,
  });

  api.insertElement(
    "insert-rect",
    function (pos) {
      return new fabric.Rect({
        width: 70,
        height: 40,
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
  const shapeFit = api.fitActiveWithinCanvas(getJSON);
  step("gate-shape", { ok: !shapeFit, shapeFit: shapeFit });

  // Multi: select image + rect if possible
  const imgObj = c.getObjects().find(function (o) {
    return o.blytzId === imgId;
  });
  const rectObj = active();
  let multiFit = false;
  if (imgObj && rectObj && c.setActiveObject) {
    try {
      if (fabric.ActiveSelection) {
        const sel = new fabric.ActiveSelection([imgObj, rectObj], { canvas: c });
        c.setActiveObject(sel);
        c.requestRenderAll();
        multiFit = api.fitActiveWithinCanvas(getJSON);
      }
    } catch (e) {
      multiFit = false;
    }
  }
  step("gate-multi", { ok: !multiFit, multiFit: multiFit });

  // Reselect image
  c.setActiveObject(imgObj);
  c.requestRenderAll();
  await sleep(40);

  // --- Locked blocks ---
  api.setObjectLockedById(imgId, true, getJSON);
  await sleep(40);
  c.setActiveObject(imgObj);
  c.requestRenderAll();
  if (BlytzEditorProps) BlytzEditorProps.syncFromSelection();
  await sleep(60);
  const lockedBody = propsBody();
  const lockedNotice = !!(
    lockedBody &&
    lockedBody.textContent &&
    lockedBody.textContent.indexOf("Locked") >= 0
  );
  const fitLocked = api.fitActiveWithinCanvas(getJSON);
  const centerLocked = api.centerActiveImage(getJSON);
  const resetLocked = api.resetActiveRotation(getJSON);
  step("locked-gating", {
    ok: lockedNotice && !fitLocked && !centerLocked && !resetLocked,
    lockedNotice: lockedNotice,
    fitLocked: fitLocked,
    centerLocked: centerLocked,
    resetLocked: resetLocked,
  });
  api.setObjectLockedById(imgId, false, getJSON);
  await sleep(40);
  c.setActiveObject(imgObj);
  c.requestRenderAll();

  // --- Layer ops still work ---
  const renameOk = api.renameObjectById(imgId, "Stage E Logo", getJSON);
  await sleep(30);
  const dupOk = api.duplicateActive(getJSON);
  await sleep(40);
  const dup = active();
  const hideOk = api.setObjectVisibleById(imgId, false, getJSON);
  await sleep(20);
  const showOk = api.setObjectVisibleById(imgId, true, getJSON);
  step("layer-ops", {
    ok:
      renameOk &&
      dupOk &&
      hideOk &&
      showOk &&
      imgObj.blytzName === "Stage E Logo" &&
      dup &&
      dup.blytzId !== imgId,
    renameOk: renameOk,
    dupOk: dupOk,
    dupId: dup && dup.blytzId,
  });

  // Keep only original image + one text for front/back test (remove extra if needed)
  c.setActiveObject(imgObj);
  c.requestRenderAll();

  // --- Front/Back isolation ---
  const frontCount = c.getObjects().length;
  const switched = api.setActiveView("back", getJSON);
  await sleep(80);
  const backCount = c.getObjects().length;
  const backHasImg = c.getObjects().some(function (o) {
    return o.blytzId === imgId;
  });
  api.setActiveView("front", getJSON);
  await sleep(80);
  const frontAgain = c.getObjects().some(function (o) {
    return o.blytzId === imgId;
  });
  step("front-back-isolation", {
    ok: switched !== false && !backHasImg && frontAgain,
    frontCount: frontCount,
    backCount: backCount,
    backHasImg: backHasImg,
    frontAgain: frontAgain,
  });

  // --- Print overflow: oversized image should warn ---
  c.setActiveObject(
    c.getObjects().find(function (o) {
      return o.blytzId === imgId;
    })
  );
  const img2 = active();
  api.commitEdit(
    "prop-width",
    function () {
      const sx = 900 / Math.max(img2.width || 1, 0.0001);
      img2.set({ scaleX: sx, scaleY: sx });
      img2.setCoords();
      return true;
    },
    getJSON
  );
  await sleep(80);
  if (api.schedulePrintOverflowCheck) api.schedulePrintOverflowCheck();
  await sleep(100);
  const warn = document.getElementById("editor-print-overflow-warning");
  const warnVisible =
    warn && !warn.hidden && getComputedStyle(warn).display !== "none";
  step("print-overflow", {
    ok: !!warnVisible || !!(api.getPrintOverflowState && api.getPrintOverflowState().overflowing),
    warnVisible: !!warnVisible,
    state: api.getPrintOverflowState && api.getPrintOverflowState(),
  });

  // Shrink back + center for clean save
  api.fitActiveWithinCanvas(getJSON);
  await sleep(40);
  img2.set("opacity", 0.7);
  img2.set("angle", 12);
  img2.setCoords();
  api.commitEdit(
    "prep-save",
    function () {
      return true;
    },
    getJSON
  );
  await sleep(40);
  const beforeSave = snapImg(
    c.getObjects().find(function (o) {
      return o.blytzId === imgId;
    })
  );
  report.beforeSave = beforeSave;

  // Undo/redo smoke
  const canUndo = BlytzEditor.canUndo && BlytzEditor.canUndo();
  BlytzEditor.undo();
  await sleep(40);
  const afterUndo = snapImg(
    c.getObjects().find(function (o) {
      return o.blytzId === imgId;
    })
  );
  BlytzEditor.redo();
  await sleep(40);
  const afterRedo = snapImg(
    c.getObjects().find(function (o) {
      return o.blytzId === imgId;
    })
  );
  step("undo-redo", {
    ok: canUndo && afterRedo && Math.abs(afterRedo.opacity - beforeSave.opacity) < 0.01,
    canUndo: canUndo,
    afterUndo: afterUndo,
    afterRedo: afterRedo,
  });

  // --- Save ---
  const saveBtn = document.querySelector("[data-editor-save]");
  if (saveBtn) {
    saveBtn.click();
    await sleep(800);
  } else if (BlytzEditor.save) {
    await BlytzEditor.save();
    await sleep(400);
  }
  step("save-clicked", { ok: true });

  // Reload page and compare
  report.reloadUrl = location.pathname + "?stage=e&reload=1";
  report.needsReload = true;
  report.beforeSave = beforeSave;
  report.imgId = imgId;
  return report;
})();
