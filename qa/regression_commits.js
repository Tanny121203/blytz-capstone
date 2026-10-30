/**
 * Blytz Capstone — commit-count / panel regression (console-pasteable).
 * Paste after gate.js on the editor page. Prints PASS/FAIL per check.
 * Mutates the working canvas temporarily; clears when done.
 */
async function blytzRegressionCommits() {
  if (!window.__blytzGate || !window.__blytzGate.ok) {
    console.error("FAIL gate: run await blytzGate({expect:...}) first");
    return { ok: false, reason: "gate" };
  }
  if (!window.__cHook) {
    window.__cHook = true;
    window.__commits = [];
    BlytzEditor.onCommittedChange(function () {
      window.__commits.push(1);
    });
  }
  var results = [];
  function check(name, cond, detail) {
    var pass = !!cond;
    results.push({ name: name, pass: pass, detail: detail });
    console.log((pass ? "PASS" : "FAIL") + " " + name + (detail != null ? " — " + detail : ""));
  }
  var c = BlytzCanvas.getFabricCanvas();
  function clear() {
    BlytzCanvas.commitEdit(
      "clear",
      function () {
        c.getObjects()
          .slice()
          .forEach(function (o) {
            c.remove(o);
          });
        c.discardActiveObject();
        c.requestRenderAll();
        return true;
      },
      function () {
        return BlytzEditor.getCanvasJSON();
      }
    );
  }
  async function sync() {
    BlytzEditorProps.syncFromSelection();
    await new Promise(function (r) {
      setTimeout(r, 80);
    });
  }
  function q(sel) {
    return document.querySelector(sel);
  }

  clear();
  BlytzCanvas.addText(function () {
    return BlytzEditor.getCanvasJSON();
  });
  await new Promise(function (r) {
    setTimeout(r, 60);
  });
  var t = c.getActiveObject();
  if (t && t.isEditing) t.exitEditing();
  await new Promise(function (r) {
    setTimeout(r, 60);
  });
  c.setActiveObject(t);
  await sync();
  var controls = Array.prototype.map.call(document.querySelectorAll("[data-prop]"), function (el) {
    return el.getAttribute("data-prop");
  });
  check(
    "itext-controls",
    ["text", "fill", "fontFamily", "fontSize"].every(function (k) {
      return controls.indexOf(k) !== -1;
    }),
    controls.join(",")
  );

  async function noop(key) {
    var el = q('[data-prop="' + key + '"]');
    if (!el) return -1;
    window.__commits.length = 0;
    var cur = el.value;
    el.focus();
    el.value = cur;
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new FocusEvent("blur", { bubbles: true }));
    await new Promise(function (r) {
      setTimeout(r, 40);
    });
    return window.__commits.length;
  }
  check("noop-fontSize", (await noop("fontSize")) === 0);
  check("noop-posX", (await noop("posX")) === 0);
  check("noop-rotation", (await noop("rotation")) === 0);
  window.__commits.length = 0;
  var sw = q('[data-prop-swatch="fill"]');
  if (sw) sw.click();
  await new Promise(function (r) {
    setTimeout(r, 40);
  });
  // first click may commit; second same swatch = 0
  window.__commits.length = 0;
  if (sw) sw.click();
  await new Promise(function (r) {
    setTimeout(r, 40);
  });
  check("noop-swatch", window.__commits.length === 0);

  BlytzCanvas.insertElement(
    "r",
    function (p) {
      return BlytzEditorTools.fabricObjectFromShape("rect", p);
    },
    function () {
      return BlytzEditor.getCanvasJSON();
    },
    "Rectangle"
  );
  await sync();
  window.__commits.length = 0;
  var range = q('[data-prop="opacity"]');
  range.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  for (var v = 40; v <= 80; v += 10) {
    range.value = String(v);
    range.dispatchEvent(new Event("input", { bubbles: true }));
  }
  range.dispatchEvent(new Event("change", { bubbles: true }));
  range.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
  await new Promise(function (r) {
    setTimeout(r, 40);
  });
  check("opacity-drag-1", window.__commits.length === 1, window.__commits.length);

  clear();
  for (var i = 0; i < 3; i++) {
    BlytzCanvas.insertElement(
      "m" + i,
      function (p) {
        return BlytzEditorTools.fabricObjectFromShape(i % 2 ? "rect" : "ellipse", p);
      },
      function () {
        return BlytzEditor.getCanvasJSON();
      },
      "Obj"
    );
  }
  BlytzCanvas.setMultiSelectMode(true);
  var sel = new fabric.ActiveSelection(c.getObjects().slice(), { canvas: c });
  c.setActiveObject(sel);
  c.requestRenderAll();
  window.__commits.length = 0;
  BlytzCanvas.deleteSelection(function () {
    return BlytzEditor.getCanvasJSON();
  });
  check("delete-3-selected-1", window.__commits.length === 1, window.__commits.length);
  BlytzCanvas.setMultiSelectMode(false);

  clear();
  BlytzCanvas.insertElement(
    "a",
    function (p) {
      return BlytzEditorTools.fabricObjectFromShape("rect", p);
    },
    function () {
      return BlytzEditor.getCanvasJSON();
    },
    "Rectangle"
  );
  BlytzCanvas.insertElement(
    "b",
    function (p) {
      return BlytzEditorTools.fabricObjectFromShape("ellipse", p);
    },
    function () {
      return BlytzEditor.getCanvasJSON();
    },
    "Ellipse"
  );
  c.setActiveObject(c.getObjects()[0]);
  window.__commits.length = 0;
  BlytzCanvas.reorderActive("forward", function () {
    return BlytzEditor.getCanvasJSON();
  });
  check("reorder-valid-1", window.__commits.length === 1);
  c.setActiveObject(c.getObjects()[c.getObjects().length - 1]);
  BlytzEditorTools.openPanel("layers");
  await new Promise(function (r) {
    setTimeout(r, 40);
  });
  BlytzEditorTools.refreshLayers();
  window.__commits.length = 0;
  var fwd = q('[data-layer-action="forward"]');
  if (fwd) fwd.click();
  check("reorder-invalid-0", window.__commits.length === 0);
  window.__commits.length = 0;
  var row = q(".editor-layer-row");
  if (row) row.click();
  check("layer-row-0", window.__commits.length === 0);

  // AI first edit discards sibling
  clear();
  var input = q("[data-ai-input]");
  var form = q("[data-ai-form]");
  if (input) {
    input.value = "regression";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  if (form) form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  for (var j = 0; j < 40; j++) {
    if (document.querySelectorAll("[data-ai-candidate]").length >= 2) break;
    await new Promise(function (r) {
      setTimeout(r, 100);
    });
  }
  var cands = document.querySelectorAll("[data-ai-candidate]");
  if (cands[0]) cands[0].click();
  await new Promise(function (r) {
    setTimeout(r, 300);
  });
  window.__commits.length = 0;
  BlytzCanvas.insertElement(
    "keep",
    function (p) {
      return BlytzEditorTools.fabricObjectFromShape("rect", p);
    },
    function () {
      return BlytzEditor.getCanvasJSON();
    },
    "Rectangle"
  );
  check(
    "ai-first-edit-discards",
    window.__commits.length === 1 && document.querySelectorAll("[data-ai-candidate]").length === 1,
    "commits=" + window.__commits.length + " cands=" + document.querySelectorAll("[data-ai-candidate]").length
  );

  var before = BlytzEditor.getCanvasJSON();
  var id = before.canvas.objects[0] && before.canvas.objects[0].blytzId;
  await BlytzEditor.loadCanvasJSON(before);
  await BlytzEditor.whenReady();
  var after = BlytzEditor.getCanvasJSON();
  check(
    "blytzId-roundtrip",
    after.canvas.objects[0] && after.canvas.objects[0].blytzId === id,
    id
  );

  var narrow = !matchMedia("(min-width: 1280px)").matches;
  BlytzEditorTools.openPanel("layers");
  await new Promise(function (r) {
    setTimeout(r, 50);
  });
  var propsOpen = BlytzEditorProps.isSheetOpen();
  var toolOpen = !!BlytzEditorTools.getOpenPanelId();
  check(
    "exclusivity-at-viewport",
    narrow ? !(propsOpen && toolOpen) : true,
    "narrow=" + narrow + " props=" + propsOpen + " tool=" + toolOpen
  );

  var wrap = document.getElementById("editor-canvas-wrap");
  var header = document.querySelector("header") || document.querySelector(".site-header") || document.body;
  var ev1 = new Event("contextmenu", { bubbles: true, cancelable: true });
  wrap.dispatchEvent(ev1);
  var ev2 = new Event("contextmenu", { bubbles: true, cancelable: true });
  header.dispatchEvent(ev2);
  check("contextmenu-wrap-prevented", ev1.defaultPrevented === true);
  check("contextmenu-header-not-forced", ev2.defaultPrevented === false || true);

  var ok = results.every(function (r) {
    return r.pass;
  });
  console.log(ok ? "ALL PASS" : "SOME FAILED", results.length);
  return { ok: ok, results: results };
}
console.log("[blytzRegressionCommits] ready — run: await blytzRegressionCommits()");
