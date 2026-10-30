/**
 * Stage 3a verification harness — run via CDP Runtime.evaluate on the live editor.
 * Path: C:\Users\acer\Desktop\blytz_stage3a_verify.js
 */
(async () => {
  const report = { ok: false };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function idsOf(env) {
    return (env.canvas.objects || []).map((o) => o.blytzId);
  }

  let commits = 0;
  const unsub = BlytzEditor.onCommittedChange(() => {
    commits += 1;
  });

  async function loadAndWait(json) {
    BlytzEditor.loadCanvasJSON(json);
    await BlytzEditor.whenReady();
    await sleep(40);
  }

  // ---------- Task A ----------
  report.A = {};

  // A1 legacy load without blytzId
  commits = 0;
  await loadAndWait({
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: fabric.version,
      objects: [
        { type: "Rect", left: 10, top: 10, width: 40, height: 30, fill: "#111" },
        { type: "IText", left: 80, top: 80, text: "Hi", fontSize: 24 },
      ],
    },
  });
  const a1Ids = idsOf(BlytzEditor.getCanvasJSON());
  report.A.legacy = {
    ids: a1Ids,
    allNonEmpty: a1Ids.every((id) => typeof id === "string" && id.length > 0),
    unique: new Set(a1Ids).size === a1Ids.length,
    commitsFromIdAssign: commits,
    canPersist: BlytzEditor.canPersist(),
  };

  // A6 stability (uses objects that now have ids)
  const snap1 = BlytzEditor.getCanvasJSON();
  const ids1 = idsOf(snap1);
  commits = 0;
  await loadAndWait(snap1);
  const ids2 = idsOf(BlytzEditor.getCanvasJSON());
  commits = 0;
  await loadAndWait(BlytzEditor.getCanvasJSON());
  const ids3 = idsOf(BlytzEditor.getCanvasJSON());
  report.A.stability = {
    ids1,
    ids2,
    ids3,
    identical: JSON.stringify(ids1) === JSON.stringify(ids2) && JSON.stringify(ids2) === JSON.stringify(ids3),
    commitsOnReloads: commits,
  };

  // A7 persist payload
  const prepared = BlytzEditor.preparePersistPayload();
  report.A.persist = {
    ok: prepared.ok,
    idsInPayload: prepared.ok ? idsOf(prepared.json) : null,
    matchesCanvas: prepared.ok && JSON.stringify(idsOf(prepared.json)) === JSON.stringify(ids3),
  };

  // A2 addText
  commits = 0;
  await loadAndWait({
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: { version: fabric.version, objects: [] },
  });
  const commitsBeforeAdd = commits;
  commits = 0;
  document.querySelector("[data-editor-action='add-text']").click();
  await sleep(50);
  const afterAddText = BlytzEditor.getCanvasJSON().canvas.objects;
  report.A.addText = {
    objectCount: afterAddText.length,
    blytzId: afterAddText[0] && afterAddText[0].blytzId,
    commitsFromAdd: commits,
    // id assignment itself should not add extra commits beyond the one add-text commit
  };

  // A2 addImageFromFile — tiny 1x1 png
  const tinyPng =
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
  const blob = await (await fetch(tinyPng)).blob();
  const file = new File([blob], "t.png", { type: "image/png" });
  commits = 0;
  const beforeImgCount = BlytzCanvas.getFabricCanvas().getObjects().length;
  BlytzCanvas.getFabricCanvas(); // ensure
  // Call addImage via internal path: wireTools uses file input; invoke BlytzCanvas through change event
  const input = document.querySelector("[data-editor-image-input]");
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event("change", { bubbles: true }));
  await sleep(400);
  const objsAfterImg = BlytzEditor.getCanvasJSON().canvas.objects;
  const imgObj = objsAfterImg.find((o) => String(o.type).toLowerCase() === "image");
  report.A.addImage = {
    beforeCount: beforeImgCount,
    afterCount: objsAfterImg.length,
    imageBlytzId: imgObj && imgObj.blytzId,
    commitsFromAdd: commits,
  };

  // A3 AI preview/apply both mock candidates
  const mockA = {
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: fabric.version,
      objects: [
        {
          type: "IText",
          left: 120,
          top: 340,
          text: "WORD",
          fontSize: 42,
          originX: "left",
          originY: "top",
        },
      ],
    },
  };
  const mockB = {
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: fabric.version,
      objects: [
        {
          type: "Rect",
          left: 48,
          top: 48,
          width: 72,
          height: 72,
          fill: "#f7f1de",
          originX: "left",
          originY: "top",
        },
        {
          type: "IText",
          left: 60,
          top: 68,
          text: "B",
          fontSize: 36,
          originX: "left",
          originY: "top",
        },
      ],
    },
  };
  commits = 0;
  const prevA = await BlytzEditor.previewCanvasJSON(mockA);
  await sleep(40);
  const idsPrevA = idsOf(BlytzEditor.getCanvasJSON());
  const commitsAfterPrevA = commits;
  commits = 0;
  const appA = await BlytzEditor.applyCanvasJSON(mockA);
  await sleep(40);
  const idsAppA = idsOf(BlytzEditor.getCanvasJSON());
  const commitsAfterAppA = commits;
  commits = 0;
  const prevB = await BlytzEditor.previewCanvasJSON(mockB);
  await sleep(40);
  const idsPrevB = idsOf(BlytzEditor.getCanvasJSON());
  const commitsAfterPrevB = commits;
  commits = 0;
  const appB = await BlytzEditor.applyCanvasJSON(mockB);
  await sleep(40);
  const idsAppB = idsOf(BlytzEditor.getCanvasJSON());
  report.A.ai = {
    previewA: { ok: prevA.ok, ids: idsPrevA, allHaveIds: idsPrevA.every(Boolean), unique: new Set(idsPrevA).size === idsPrevA.length, commits: commitsAfterPrevA },
    applyA: { ok: appA.ok, ids: idsAppA, allHaveIds: idsAppA.every(Boolean), unique: new Set(idsAppA).size === idsAppA.length, commits: commitsAfterAppA },
    previewB: { ok: prevB.ok, ids: idsPrevB, allHaveIds: idsPrevB.every(Boolean), unique: new Set(idsPrevB).size === idsPrevB.length, commits: commitsAfterPrevB },
    applyB: { ok: appB.ok, ids: idsAppB, allHaveIds: idsAppB.every(Boolean), unique: new Set(idsAppB).size === idsAppB.length, commits: commits },
  };

  // A4 duplicates — first keeps original
  commits = 0;
  await loadAndWait({
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: fabric.version,
      objects: [
        { type: "Rect", left: 1, top: 1, width: 10, height: 10, fill: "#000", blytzId: "keep_me" },
        { type: "Rect", left: 20, top: 20, width: 10, height: 10, fill: "#111", blytzId: "keep_me" },
        { type: "Rect", left: 40, top: 40, width: 10, height: 10, fill: "#222", blytzId: "other" },
      ],
    },
  });
  const dupIds = idsOf(BlytzEditor.getCanvasJSON());
  report.A.duplicates = {
    ids: dupIds,
    firstKept: dupIds[0] === "keep_me",
    unique: new Set(dupIds).size === dupIds.length,
    thirdKept: dupIds[2] === "other",
    commitsFromIdAssign: commits,
  };

  // ---------- Task B ----------
  report.B = {};
  report.B.fabricVersion = fabric.version;

  // B1 contextmenu / dragstart
  function fireCancelable(target, type) {
    const ev = new Event(type, { bubbles: true, cancelable: true });
    target.dispatchEvent(ev);
    return ev.defaultPrevented;
  }
  const wrap = document.getElementById("editor-canvas-wrap");
  const canvasEl = document.getElementById("blytz-fabric-canvas");
  const header = document.querySelector("[data-editor-page] h1") || document.body;
  report.B.contextmenu = {
    wrapPrevented: fireCancelable(wrap, "contextmenu"),
    canvasPrevented: fireCancelable(canvasEl, "contextmenu"),
    headerPrevented: fireCancelable(header, "contextmenu"),
    bodyPrevented: fireCancelable(document.body, "contextmenu"),
  };
  report.B.dragstart = {
    wrapPrevented: fireCancelable(wrap, "dragstart"),
    canvasPrevented: fireCancelable(canvasEl, "dragstart"),
    headerPrevented: fireCancelable(header, "dragstart"),
  };

  // B2 delete key guard
  await loadAndWait({
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: fabric.version,
      objects: [{ type: "Rect", left: 5, top: 5, width: 30, height: 20, fill: "#c00", blytzId: "del_target" }],
    },
  });
  const fc = BlytzCanvas.getFabricCanvas();
  const targetObj = fc.getObjects()[0];
  fc.setActiveObject(targetObj);
  fc.requestRenderAll();

  async function pressDeleteOn(el) {
    el.focus();
    const before = fc.getObjects().length;
    const ev = new KeyboardEvent("keydown", { key: "Delete", bubbles: true, cancelable: true });
    el.dispatchEvent(ev);
    await sleep(30);
    return { before, after: fc.getObjects().length, deleted: fc.getObjects().length < before };
  }

  // inject temp focusables
  const host = document.body;
  const inp = document.createElement("input");
  const ta = document.createElement("textarea");
  const sel = document.createElement("select");
  sel.appendChild(document.createElement("option"));
  const ce = document.createElement("div");
  ce.contentEditable = "true";
  ce.textContent = "x";
  [inp, ta, sel, ce].forEach((el) => {
    el.style.position = "fixed";
    el.style.left = "0";
    el.style.top = "0";
    el.style.opacity = "0.01";
    host.appendChild(el);
  });
  fc.setActiveObject(targetObj);
  const delInput = await pressDeleteOn(inp);
  fc.setActiveObject(fc.getObjects()[0] || targetObj);
  const delTa = await pressDeleteOn(ta);
  fc.setActiveObject(fc.getObjects()[0] || targetObj);
  const delSel = await pressDeleteOn(sel);
  fc.setActiveObject(fc.getObjects()[0] || targetObj);
  const delCe = await pressDeleteOn(ce);
  // canvas focus delete
  commits = 0;
  if (fc.getObjects().length === 0) {
    BlytzCanvas.commitEdit("reseed", () => {
      const r = new fabric.Rect({ left: 5, top: 5, width: 30, height: 20, fill: "#c00" });
      r.blytzId = "del_target2";
      fc.add(r);
      return true;
    });
  }
  fc.setActiveObject(fc.getObjects()[0]);
  fc.requestRenderAll();
  wrap.focus?.();
  document.activeElement?.blur?.();
  // dispatch on document (handler is document-level) with body not input
  const bodyFocus = document.createElement("button");
  bodyFocus.type = "button";
  bodyFocus.textContent = "f";
  host.appendChild(bodyFocus);
  bodyFocus.focus();
  commits = 0;
  const beforeCanvasDel = fc.getObjects().length;
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Delete", bubbles: true, cancelable: true }));
  await sleep(40);
  report.B.deleteGuard = {
    input: delInput,
    textarea: delTa,
    select: delSel,
    contentEditable: delCe,
    canvasFocus: {
      before: beforeCanvasDel,
      after: fc.getObjects().length,
      deleted: fc.getObjects().length < beforeCanvasDel,
      commits,
    },
  };
  [inp, ta, sel, ce, bodyFocus].forEach((el) => el.remove());

  // B3 placeholders
  const elBtn = document.querySelector("[data-editor-action='elements']");
  const lyBtn = document.querySelector("[data-editor-action='layers']");
  let elementsClicked = false;
  const clickProbe = () => {
    elementsClicked = true;
  };
  elBtn.addEventListener("click", clickProbe);
  elBtn.click();
  report.B.placeholders = {
    elements: {
      ariaDisabled: elBtn.getAttribute("aria-disabled"),
      disabled: elBtn.disabled,
      title: elBtn.getAttribute("title"),
      tabIndex: elBtn.tabIndex,
      clickFired: elementsClicked,
    },
    layers: {
      ariaDisabled: lyBtn.getAttribute("aria-disabled"),
      disabled: lyBtn.disabled,
      title: lyBtn.getAttribute("title"),
      tabIndex: lyBtn.tabIndex,
    },
  };
  elBtn.removeEventListener("click", clickProbe);

  // B4 touch handles
  const defaults = fabric.FabricObject && fabric.FabricObject.ownDefaults;
  const sample = fc.getObjects()[0] || new fabric.Rect({ left: 0, top: 0, width: 10, height: 10 });
  report.B.touchHandles = {
    pointerCoarse: matchMedia("(pointer: coarse)").matches,
    ownDefaults: defaults
      ? { cornerSize: defaults.cornerSize, touchCornerSize: defaults.touchCornerSize, cornerStyle: defaults.cornerStyle }
      : null,
    sampleObject: { cornerSize: sample.cornerSize, touchCornerSize: sample.touchCornerSize },
  };

  // B5 multi-select
  await loadAndWait({
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: fabric.version,
      objects: [
        { type: "Rect", left: 40, top: 40, width: 50, height: 40, fill: "#f00", blytzId: "ms_a" },
        { type: "Rect", left: 160, top: 80, width: 50, height: 40, fill: "#0f0", blytzId: "ms_b" },
        { type: "Rect", left: 280, top: 120, width: 50, height: 40, fill: "#00f", blytzId: "ms_c" },
      ],
    },
  });
  const objs = fc.getObjects();
  const multiBtn = document.querySelector("[data-editor-action='multi-select']");
  const selectBtn = document.querySelector("[data-editor-action='select']");
  commits = 0;
  BlytzCanvas.setMultiSelectMode(true);
  report.B.multi = {
    onPressed: multiBtn.getAttribute("aria-pressed"),
    onClass: multiBtn.classList.contains("is-active"),
    selectionKey: fc.selectionKey,
  };

  // Simulate Fabric multi-select path: with selectionKey including blytzMultiSelect,
  // fire pointerdown with flag then use ActiveSelection APIs the same way Fabric would
  // Prefer public: setActiveObject first A, then with multi mode simulate shift-add via ActiveSelection
  fc.setActiveObject(objs[0]);
  fc.requestRenderAll();
  // Use Fabric's handle: create ActiveSelection of A+B (equivalent outcome of multi tap)
  // Then measure toggle remove
  const as = new fabric.ActiveSelection([objs[0], objs[1]], { canvas: fc });
  fc.setActiveObject(as);
  fc.requestRenderAll();
  const activeTwo = fc.getActiveObjects().length;
  // Remove B from selection (multiSelect remove)
  as.remove(objs[1]);
  if (as.size && as.size() === 1) {
    fc.setActiveObject(as.getObjects()[0]);
  } else if (as.getObjects && as.getObjects().length === 1) {
    fc.setActiveObject(as.getObjects()[0]);
  }
  fc.requestRenderAll();
  const afterRemove = fc.getActiveObjects().length;
  BlytzCanvas.setMultiSelectMode(false);
  fc.setActiveObject(objs[2] || objs[0]);
  const singleType = fc.getActiveObject() && fc.getActiveObject().type;
  // shift-click equivalent: selectionKey back to shiftKey; build multi with ActiveSelection while "shift"
  const as2 = new fabric.ActiveSelection([objs[0], objs[2] || objs[1]], { canvas: fc });
  fc.setActiveObject(as2);
  report.B.multi.results = {
    activeTwo,
    afterRemoveOne: afterRemove,
    offPressed: multiBtn.getAttribute("aria-pressed"),
    selectPressed: selectBtn.getAttribute("aria-pressed"),
    singleType,
    shiftMultiCount: fc.getActiveObjects().length,
    commits,
    note: "Tap simulation used ActiveSelection public API after setMultiSelectMode; pointer flag path verified by selectionKey value",
  };

  // ---------- Task F ----------
  report.F = {};
  const netBefore = performance.getEntriesByType("resource").length;
  commits = 0;
  await loadAndWait({
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: fabric.version,
      objects: [
        {
          type: "Image",
          left: 10,
          top: 10,
          src: "https://example.com/does-not-exist-blytz-probe.png",
        },
      ],
    },
  });
  await sleep(500);
  const netAfter = performance.getEntriesByType("resource").filter((e) =>
    String(e.name).includes("example.com")
  );
  report.F.httpsImage = {
    loadState: BlytzEditor.getLoadState(),
    canPersist: BlytzEditor.canPersist(),
    persistBlock: BlytzEditor.getPersistBlockReason(),
    objectCount: BlytzEditor.getCanvasJSON().canvas.objects.length,
    types: BlytzEditor.getCanvasJSON().canvas.objects.map((o) => o.type),
    srcPrefix: (BlytzEditor.getCanvasJSON().canvas.objects[0] && BlytzEditor.getCanvasJSON().canvas.objects[0].src || "").slice(0, 40),
    exampleComRequests: netAfter.map((e) => e.name),
    parseInput: BlytzCanvas.parseInput({
      schema_version: 1,
      width: 800,
      height: 800,
      canvas: {
        version: fabric.version,
        objects: [{ type: "Image", src: "https://example.com/x.png" }],
      },
    }),
  };

  await loadAndWait({
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: fabric.version,
      objects: [{ type: "evil", left: 1, top: 1, width: 10, height: 10, fill: "#000" }],
    },
  });
  report.F.evilType = {
    loadState: BlytzEditor.getLoadState(),
    canPersist: BlytzEditor.canPersist(),
    persistBlock: BlytzEditor.getPersistBlockReason(),
    objects: BlytzEditor.getCanvasJSON().canvas.objects,
    parseInput: BlytzCanvas.parseInput({
      schema_version: 1,
      width: 800,
      height: 800,
      canvas: { version: fabric.version, objects: [{ type: "evil" }] },
    }),
  };

  unsub();
  report.ok = true;
  window.__V3A__ = report;
  return report;
})();
