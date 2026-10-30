/**
 * Blytz Capstone — garment + Front/Back console checks (Task 17 C/D subset).
 * Paste after gate.js. Prints PASS/FAIL per check.
 */
async function blytzGarmentChecks() {
  if (!window.__blytzGate || !window.__blytzGate.ok) {
    console.error("FAIL gate: run await blytzGate({expect:...}) first");
    return { ok: false, reason: "gate" };
  }
  var results = [];
  function check(name, cond, detail) {
    var pass = !!cond;
    results.push({ name: name, pass: pass, detail: detail });
    console.log((pass ? "PASS" : "FAIL") + " " + name + (detail != null ? " — " + detail : ""));
  }

  check("BlytzGarments", !!(window.BlytzGarments && BlytzGarments.renderGarmentLayer));
  check("getActiveView", typeof BlytzEditor.getActiveView === "function");
  check("setActiveView", typeof BlytzEditor.setActiveView === "function");
  check("getActiveCanvasJSON", typeof BlytzEditor.getActiveCanvasJSON === "function");

  var layer = document.getElementById("editor-garment-layer");
  var wrap = document.getElementById("editor-canvas-wrap");
  check("layer-exists", !!layer);
  if (layer && wrap) {
    var lb = layer.getBoundingClientRect();
    var wb = wrap.getBoundingClientRect();
    check(
      "layer-box-matches-wrap",
      Math.abs(lb.width - wb.width) <= 1 && Math.abs(lb.height - wb.height) <= 1,
      "layer=" + Math.round(lb.width) + "x" + Math.round(lb.height) + " wrap=" + Math.round(wb.width) + "x" + Math.round(wb.height)
    );
  }

  if (!window.__cHook) {
    window.__cHook = true;
    window.__commits = [];
    BlytzEditor.onCommittedChange(function () {
      window.__commits.push(1);
    });
  }

  BlytzEditor.setGarmentState({ template: "tee", color: "white" });
  await BlytzEditor.setActiveView("front");
  BlytzCanvas.commitEdit(
    "clear",
    function () {
      var c = BlytzCanvas.getFabricCanvas();
      c.getObjects().slice().forEach(function (o) {
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

  BlytzCanvas.addText(function () {
    return BlytzEditor.getCanvasJSON();
  });
  await new Promise(function (r) {
    setTimeout(r, 80);
  });
  var t = BlytzCanvas.getFabricCanvas().getActiveObject();
  if (t && t.isEditing) t.exitEditing();
  await new Promise(function (r) {
    setTimeout(r, 40);
  });
  BlytzCanvas.insertElement(
    "front-rect",
    function (p) {
      return BlytzEditorTools.fabricObjectFromShape("rect", p);
    },
    function () {
      return BlytzEditor.getCanvasJSON();
    },
    "Rectangle"
  );
  var frontBefore = BlytzEditor.getCanvasJSON();
  check("envelope-has-views-back", !!(frontBefore.views && frontBefore.views.back));
  check("active-is-front", BlytzEditor.getActiveView() === "front");

  window.__commits.length = 0;
  var sw = await BlytzEditor.setActiveView("back");
  check("switch-ok", sw && sw.ok, sw && sw.reason);
  check("switch-0-commits", window.__commits.length === 0, window.__commits.length);
  check("active-is-back", BlytzEditor.getActiveView() === "back");

  BlytzCanvas.insertElement(
    "back-ellipse",
    function (p) {
      return BlytzEditorTools.fabricObjectFromShape("ellipse", p);
    },
    function () {
      return BlytzEditor.getCanvasJSON();
    },
    "Ellipse"
  );
  var mid = BlytzEditor.getCanvasJSON();
  check(
    "both-views-populated",
    mid.canvas.objects.length >= 2 && mid.views.back.objects.length >= 1,
    "front=" + mid.canvas.objects.length + " back=" + mid.views.back.objects.length
  );

  window.__commits.length = 0;
  await BlytzEditor.setActiveView("front");
  check("return-front-0-commits", window.__commits.length === 0);
  var frontAfter = BlytzEditor.getCanvasJSON();
  check(
    "front-intact",
    JSON.stringify(frontAfter.canvas.objects.map(function (o) {
      return o.blytzId;
    })) ===
      JSON.stringify(frontBefore.canvas.objects.map(function (o) {
        return o.blytzId;
      }))
  );

  var fill = BlytzCanvas.defaultContrastFill();
  check("contrast-white-dark", fill === "#111111", fill);
  BlytzEditor.setGarmentState({ color: "black" });
  fill = BlytzCanvas.defaultContrastFill();
  check("contrast-black-light", fill === "#ffffff", fill);

  var toggle = document.getElementById("editor-view-toggle-btn");
  check("view-toggle-present", !!toggle);

  var ok = results.every(function (r) {
    return r.pass;
  });
  console.log(ok ? "ALL PASS" : "SOME FAILED", results.length);
  return { ok: ok, results: results };
}
console.log("[blytzGarmentChecks] ready — run: await blytzGarmentChecks()");
