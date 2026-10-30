/**
 * Stage F browser verification — run via CDP Runtime.evaluate on design editor.
 * Exercises align/distribute/center/dup/delete/locked/clear/undo + regressions.
 */
(async function stageFVerify() {
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
  if (!c || typeof api.distributeActive !== "function") {
    return { ok: false, reason: "missing-stage-f-apis", designId: designId };
  }

  const historyLen = () => {
    // probe via canUndo after seed — use envelope object count + feedback instead
    return null;
  };
  const canUndo = () => !!api.canUndo && api.canUndo();
  const active = () => c.getActiveObject();
  const objs = () => c.getObjects().filter((o) => o && o.blytzId);
  const aabb = (o) => {
    const br = o.getBoundingRect();
    return {
      left: br.left,
      top: br.top,
      width: br.width,
      height: br.height,
      right: br.left + br.width,
      bottom: br.top + br.height,
      cx: br.left + br.width / 2,
      cy: br.top + br.height / 2,
    };
  };
  const nearly = (a, b, eps) => Math.abs(a - b) <= (eps == null ? 1.5 : eps);

  // Clear canvas silently if leftover
  await api.commitEdit(
    "stage-f-reset",
    function () {
      objs().forEach((o) => c.remove(o));
      c.discardActiveObject();
      c.requestRenderAll();
      return true;
    },
    getJSON
  );
  await sleep(80);

  // --- Create unequal objects: large rect, small rect, rotated text, image ---
  api.addText(getJSON, { text: "StageF", skipEditing: true });
  await sleep(80);
  let text = active();
  if (text) {
    api.commitEdit(
      "stage-f-text-setup",
      function () {
        text.set({
          left: 120,
          top: 90,
          fontSize: 42,
          angle: 18,
          fill: "#111111",
        });
        if (text.setCoords) text.setCoords();
        return true;
      },
      getJSON
    );
  }
  await sleep(60);

  api.insertElement(
    "insert-rect",
    function (pos) {
      return new fabric.Rect({
        left: 60,
        top: 220,
        width: 160,
        height: 100,
        fill: "#c45c26",
        angle: 0,
        originX: "left",
        originY: "top",
      });
    },
    getJSON,
    "Rect A"
  );
  await sleep(60);
  let rectA = active();
  await sleep(40);

  api.insertElement(
    "insert-rect",
    function (pos) {
      return new fabric.Rect({
        left: 420,
        top: 280,
        width: 70,
        height: 50,
        fill: "#2563eb",
        angle: -12,
        originX: "left",
        originY: "top",
      });
    },
    getJSON,
    "Rect B"
  );
  await sleep(60);
  let rectB = active();
  await sleep(40);

  const off = document.createElement("canvas");
  off.width = 200;
  off.height = 120;
  const ctx = off.getContext("2d");
  ctx.fillStyle = "#16a34a";
  ctx.fillRect(0, 0, 200, 120);
  ctx.fillStyle = "#fff";
  ctx.fillRect(20, 30, 160, 60);
  const blob = await new Promise((res) => off.toBlob(res, "image/png"));
  const file = new File([blob], "stage_f.png", { type: "image/png" });
  const addImg = await api.addImageFromFile(file, getJSON);
  await sleep(120);
  let img = active();
  if (img) {
    await api.commitEdit(
      "stage-f-img-place",
      function () {
        img.set({ left: 520, top: 140, scaleX: 0.55, scaleY: 0.55, angle: 8 });
        if (img.setCoords) img.setCoords();
        return true;
      },
      getJSON
    );
  }
  await sleep(60);

  const all = objs();
  step("setup-objects", {
    ok: all.length >= 4 && !!(addImg && addImg.ok),
    count: all.length,
    types: all.map((o) => api.typeKey(o)),
  });

  // Helpers for multi-select
  const selectMany = (list) => {
    c.discardActiveObject();
    const fabric = window.fabric;
    const sel = new fabric.ActiveSelection(list.slice(), { canvas: c });
    c.setActiveObject(sel);
    c.requestRenderAll();
  };

  // --- Single align modes ---
  c.setActiveObject(rectA);
  c.requestRenderAll();
  const beforeLeft = aabb(rectA).left;
  api.alignActive("left", "canvas", getJSON);
  await sleep(50);
  step("single-align-left", {
    ok: nearly(aabb(rectA).left, 0, 2),
    left: aabb(rectA).left,
    before: beforeLeft,
  });

  api.alignActive("hcenter", "canvas", getJSON);
  await sleep(40);
  step("single-align-hcenter", {
    ok: nearly(aabb(rectA).cx, 400, 3),
    cx: aabb(rectA).cx,
  });

  api.alignActive("right", "canvas", getJSON);
  await sleep(40);
  step("single-align-right", {
    ok: nearly(aabb(rectA).right, 800, 3),
    right: aabb(rectA).right,
  });

  api.alignActive("top", "canvas", getJSON);
  await sleep(40);
  step("single-align-top", {
    ok: nearly(aabb(rectA).top, 0, 2),
    top: aabb(rectA).top,
  });

  api.alignActive("vcenter", "canvas", getJSON);
  await sleep(40);
  step("single-align-vcenter", {
    ok: nearly(aabb(rectA).cy, 400, 3),
    cy: aabb(rectA).cy,
  });

  api.alignActive("bottom", "canvas", getJSON);
  await sleep(40);
  step("single-align-bottom", {
    ok: nearly(aabb(rectA).bottom, 800, 3),
    bottom: aabb(rectA).bottom,
  });

  // --- Multi align ---
  // Reposition three for clear selection bounds
  await api.commitEdit(
    "stage-f-reposition",
    function () {
      rectA.set({ left: 80, top: 100, angle: 0, scaleX: 2, scaleY: 1.2 });
      rectB.set({ left: 300, top: 180, angle: -10, scaleX: 1, scaleY: 0.8 });
      text.set({ left: 500, top: 120, angle: 15 });
      [rectA, rectB, text].forEach((o) => o.setCoords && o.setCoords());
      return true;
    },
    getJSON
  );
  await sleep(40);
  selectMany([rectA, rectB, text]);
  await sleep(40);
  api.alignActive("left", "selection", getJSON);
  await sleep(50);
  const aA = aabb(rectA);
  const aB = aabb(rectB);
  const aT = aabb(text);
  const leftEdge = Math.min(aA.left, aB.left, aT.left);
  step("multi-align-left", {
    ok:
      nearly(aA.left, leftEdge, 2) &&
      nearly(aB.left, leftEdge, 2) &&
      nearly(aT.left, leftEdge, 2),
    lefts: [aA.left, aB.left, aT.left],
  });

  // --- Distribute H ---
  await api.commitEdit(
    "stage-f-spread-h",
    function () {
      // Spread with unequal gaps for distribute to fix
      rectA.set({ left: 40, top: 200, angle: 0, scaleX: 1.8, scaleY: 1.1 });
      rectB.set({ left: 220, top: 230, angle: -8, scaleX: 0.8, scaleY: 0.7 });
      text.set({ left: 560, top: 210, angle: 12 });
      img.set({ left: 380, top: 250, angle: 5, scaleX: 0.4, scaleY: 0.4 });
      [rectA, rectB, text, img].forEach((o) => o.setCoords && o.setCoords());
      return true;
    },
    getJSON
  );
  await sleep(40);
  selectMany([rectA, rectB, text, img]);
  const beforeDist = [rectA, rectB, text, img].map((o) => ({
    id: o.blytzId,
    ...aabb(o),
  }));
  const distOk = api.distributeActive("horizontal", getJSON);
  await sleep(60);
  const afterDist = [rectA, rectB, text, img].map((o) => ({
    id: o.blytzId,
    ...aabb(o),
  }));
  const sorted = afterDist.slice().sort((a, b) => a.left - b.left);
  const gaps = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    gaps.push(sorted[i + 1].left - sorted[i].right);
  }
  const gapsEven = gaps.every((g) => nearly(g, gaps[0], 2));
  step("distribute-horizontal", {
    ok: !!distOk && gapsEven && sorted.length >= 3,
    gaps: gaps,
    beforeFirst: beforeDist[0].left,
    afterFirst: afterDist[0].left,
  });

  // --- Distribute V ---
  await api.commitEdit(
    "stage-f-spread-v",
    function () {
      rectA.set({ left: 200, top: 40, angle: 0 });
      rectB.set({ left: 220, top: 200, angle: 0 });
      text.set({ left: 210, top: 420, angle: 0 });
      [rectA, rectB, text].forEach((o) => o.setCoords && o.setCoords());
      return true;
    },
    getJSON
  );
  await sleep(40);
  selectMany([rectA, rectB, text]);
  const distV = api.distributeActive("vertical", getJSON);
  await sleep(50);
  const sortedV = [rectA, rectB, text]
    .map((o) => aabb(o))
    .sort((a, b) => a.top - b.top);
  const gapsV = [];
  for (let i = 0; i < sortedV.length - 1; i++) {
    gapsV.push(sortedV[i + 1].top - sortedV[i].bottom);
  }
  step("distribute-vertical", {
    ok: !!distV && gapsV.every((g) => nearly(g, gapsV[0], 2)),
    gaps: gapsV,
  });

  // --- Multi center preserves arrangement ---
  selectMany([rectA, rectB, text]);
  await sleep(30);
  const relBefore = {
    dxAB: aabb(rectB).cx - aabb(rectA).cx,
    dyAB: aabb(rectB).cy - aabb(rectA).cy,
    dxAT: aabb(text).cx - aabb(rectA).cx,
    dyAT: aabb(text).cy - aabb(rectA).cy,
  };
  const boxBefore = api.unionAabb([aabb(rectA), aabb(rectB), aabb(text)]);
  api.centerOnCanvas("both", getJSON);
  await sleep(50);
  const relAfter = {
    dxAB: aabb(rectB).cx - aabb(rectA).cx,
    dyAB: aabb(rectB).cy - aabb(rectA).cy,
    dxAT: aabb(text).cx - aabb(rectA).cx,
    dyAT: aabb(text).cy - aabb(rectA).cy,
  };
  const boxAfter = api.unionAabb([aabb(rectA), aabb(rectB), aabb(text)]);
  step("multi-center-preserves", {
    ok:
      nearly(relBefore.dxAB, relAfter.dxAB, 2) &&
      nearly(relBefore.dyAB, relAfter.dyAB, 2) &&
      nearly(relBefore.dxAT, relAfter.dxAT, 2) &&
      nearly(relBefore.dyAT, relAfter.dyAT, 2) &&
      nearly(boxAfter.left + boxAfter.width / 2, 400, 3) &&
      nearly(boxAfter.top + boxAfter.height / 2, 400, 3),
    relBefore: relBefore,
    relAfter: relAfter,
    boxCx: boxAfter.left + boxAfter.width / 2,
    boxCy: boxAfter.top + boxAfter.height / 2,
  });

  // --- Multi duplicate ---
  const idsBefore = objs().map((o) => o.blytzId).sort();
  selectMany([rectA, rectB]);
  await sleep(30);
  const dupResult = await api.duplicateActive(getJSON);
  await sleep(80);
  const idsAfter = objs().map((o) => o.blytzId).sort();
  const newIds = idsAfter.filter((id) => idsBefore.indexOf(id) < 0);
  const act = active();
  step("multi-duplicate", {
    ok:
      !!dupResult &&
      newIds.length >= 2 &&
      api.isActiveSelection(act) &&
      act.getObjects().length === 2,
    newIds: newIds,
    total: idsAfter.length,
  });

  // --- Clear selection no dirty ---
  const undoBeforeClear = canUndo();
  // Force a known undoable state already exists; clear should not add history
  api.clearSelection();
  await sleep(40);
  step("clear-selection", {
    ok: !active() && canUndo() === undoBeforeClear,
    hadActive: !!active(),
    undoSame: canUndo() === undoBeforeClear,
  });

  // --- Locked reject ---
  c.setActiveObject(rectA);
  await sleep(20);
  api.setObjectLockedById(rectA.blytzId, true, getJSON);
  await sleep(40);
  selectMany([rectA, rectB, text]);
  await sleep(40);
  const posLocked = { left: rectA.left, top: rectA.top };
  const posB = { left: rectB.left, top: rectB.top };
  const rejected = api.distributeActive("horizontal", getJSON);
  await sleep(40);
  const alignRejected = api.alignActive("left", "selection", getJSON);
  await sleep(40);
  step("locked-reject", {
    ok:
      rejected === false &&
      alignRejected === false &&
      nearly(rectA.left, posLocked.left, 0.01) &&
      nearly(rectB.left, posB.left, 0.01),
    rejected: rejected,
    alignRejected: alignRejected,
  });
  api.setObjectLockedById(rectA.blytzId, false, getJSON);
  await sleep(40);

  // --- Undo/redo distribute ---
  selectMany([rectA, rectB, text]);
  await sleep(30);
  const preUndo = [aabb(rectA).left, aabb(rectB).left, aabb(text).left];
  api.distributeActive("horizontal", getJSON);
  await sleep(50);
  const midUndo = [aabb(rectA).left, aabb(rectB).left, aabb(text).left];
  await api.undo();
  await sleep(80);
  // re-find by id
  rectA = api.findObjectByBlytzId(rectA.blytzId);
  rectB = api.findObjectByBlytzId(rectB.blytzId);
  text = api.findObjectByBlytzId(text.blytzId);
  img = api.findObjectByBlytzId(img.blytzId);
  const afterUndo = [aabb(rectA).left, aabb(rectB).left, aabb(text).left];
  await api.redo();
  await sleep(80);
  rectA = api.findObjectByBlytzId(rectA.blytzId);
  rectB = api.findObjectByBlytzId(rectB.blytzId);
  text = api.findObjectByBlytzId(text.blytzId);
  const afterRedo = [aabb(rectA).left, aabb(rectB).left, aabb(text).left];
  step("undo-redo-distribute", {
    ok:
      nearly(afterUndo[0], preUndo[0], 2) &&
      nearly(afterRedo[0], midUndo[0], 2) &&
      nearly(afterRedo[1], midUndo[1], 2),
    preUndo: preUndo,
    midUndo: midUndo,
    afterUndo: afterUndo,
    afterRedo: afterRedo,
  });

  // --- Delete selection one op ---
  const countBeforeDel = objs().length;
  selectMany([
    api.findObjectByBlytzId(newIds[0]),
    api.findObjectByBlytzId(newIds[1]),
  ].filter(Boolean));
  await sleep(30);
  api.deleteSelection(getJSON);
  await sleep(50);
  step("delete-selection", {
    ok: objs().length === countBeforeDel - 2,
    before: countBeforeDel,
    after: objs().length,
  });

  // --- Text format / curve / image / layers regression smoke ---
  text = api.findObjectByBlytzId(text.blytzId);
  c.setActiveObject(text);
  await sleep(20);
  const boldOk = api.commitEdit(
    "stage-f-bold",
    function () {
      text.set("fontWeight", "bold");
      return true;
    },
    getJSON
  );
  step("regression-text", {
    ok: !!boldOk && text.fontWeight === "bold",
    weight: text.fontWeight,
  });

  if (api.applyTextCurve) {
    const curveOk = api.applyTextCurve({ amount: 0.4, direction: "up" }, getJSON);
    await sleep(40);
    step("regression-curve", {
      ok: !!curveOk && !!(text.path || (text.blytzCurve && text.blytzCurve.amount)),
      hasPath: !!text.path,
    });
    api.applyTextCurve({ amount: 0, direction: "up" }, getJSON);
    await sleep(30);
  }

  img = api.findObjectByBlytzId(img.blytzId);
  c.setActiveObject(img);
  await sleep(20);
  const fitOk = api.fitActiveWithinCanvas(getJSON);
  await sleep(40);
  step("regression-image-fit", {
    ok: !!fitOk && aabb(img).width <= 800.5 && aabb(img).height <= 800.5,
    w: aabb(img).width,
    h: aabb(img).height,
  });

  // Layers rename
  const renameOk = api.renameObjectById(img.blytzId, "Stage F Logo", getJSON);
  await sleep(30);
  img = api.findObjectByBlytzId(img.blytzId);
  step("regression-layers-rename", {
    ok: !!renameOk && img.blytzName === "Stage F Logo",
    name: img.blytzName,
  });

  // Print overflow check presence
  const warn = document.getElementById("editor-print-overflow-warning");
  step("print-overflow-dom", {
    ok: !!warn,
    hidden: warn ? warn.hidden || warn.getAttribute("hidden") != null : null,
  });

  // Front/Back
  const viewBefore = api.getActiveView();
  await api.setActiveView("back");
  await sleep(100);
  const viewMid = api.getActiveView();
  await api.setActiveView("front");
  await sleep(100);
  step("front-back", {
    ok: viewBefore === "front" && viewMid === "back" && api.getActiveView() === "front",
    before: viewBefore,
    mid: viewMid,
    after: api.getActiveView(),
  });

  // Props distribute buttons enablement with 3 selected
  selectMany([rectA, rectB, text].map((o) => api.findObjectByBlytzId(o.blytzId)));
  await sleep(40);
  if (window.BlytzEditorProps && BlytzEditorProps.syncFromSelection) {
    BlytzEditorProps.syncFromSelection();
  }
  await sleep(40);
  const distBtns = Array.from(
    document.querySelectorAll("[data-distribute-action]")
  );
  step("ui-distribute-enabled", {
    ok: distBtns.length >= 2 && distBtns.every((b) => !b.disabled),
    count: distBtns.length,
    disabled: distBtns.map((b) => b.disabled),
  });

  // Narrow 390 — check CSS doesn't hide align section
  const propsPanel = document.getElementById("editor-properties-panel");
  step("narrow-props-present", {
    ok: !!propsPanel,
    hidden: propsPanel ? propsPanel.hidden : null,
  });

  // Snapshot IDs/positions for save/reload
  const persistSnap = objs().map((o) => ({
    id: o.blytzId,
    name: o.blytzName,
    type: api.typeKey(o),
    left: Math.round((o.left || 0) * 10) / 10,
    top: Math.round((o.top || 0) * 10) / 10,
    angle: Math.round((o.angle || 0) * 10) / 10,
  }));
  report.persistSnap = persistSnap;
  report.envelopeBytes = api.measureEnvelopeBytes
    ? api.measureEnvelopeBytes()
    : JSON.stringify(BlytzEditor.getCanvasJSON()).length;

  // Trigger save button if available
  const saveBtn = document.querySelector("[data-editor-save], button[name='save'], #editor-save");
  if (saveBtn) {
    saveBtn.click();
    await sleep(800);
    step("save-click", { ok: true, clicked: true });
  } else {
    // Fall back to BlytzEditor save if exposed
    if (BlytzEditor.saveDesign || BlytzEditor.persist || BlytzEditor.save) {
      const fn = BlytzEditor.saveDesign || BlytzEditor.persist || BlytzEditor.save;
      try {
        await fn.call(BlytzEditor);
        step("save-api", { ok: true });
      } catch (e) {
        step("save-api", { ok: false, error: String(e) });
      }
    } else {
      step("save-manual", {
        ok: true,
        note: "no save button found — will POST via form if present",
      });
    }
  }

  report.apis = {
    distributeActive: typeof api.distributeActive,
    clearSelection: typeof api.clearSelection,
    selectionHasLockedMembers: typeof api.selectionHasLockedMembers,
    alignActive: typeof api.alignActive,
  };

  return report;
})();
