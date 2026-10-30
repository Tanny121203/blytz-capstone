/**
 * Blytz Capstone — garment + Front/Back + preview PNG console checks.
 * Paste after gate.js. Prints PASS/FAIL per check.
 *
 * Covers: every garment/view loads, UNDER+OVER layers, OVER pointer-events,
 * getPreviewPNG composites (no CSS var(), expected size, under 5 MB), and a
 * sampled-pixel check that mock-ups are not a blank background.
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
  check(
    "export-helpers",
    !!(
      BlytzGarments.resolveSvgCssVars &&
      BlytzGarments.getExportLayerMarkups &&
      BlytzGarments.SVG_VAR_TRIM
    )
  );
  check("getActiveView", typeof BlytzEditor.getActiveView === "function");
  check("setActiveView", typeof BlytzEditor.setActiveView === "function");
  check("getActiveCanvasJSON", typeof BlytzEditor.getActiveCanvasJSON === "function");
  check("getPreviewPNG", typeof BlytzEditor.getPreviewPNG === "function");

  var layer = document.getElementById("editor-garment-layer");
  var overlay = document.getElementById("editor-garment-overlay");
  var wrap = document.getElementById("editor-canvas-wrap");
  check("layer-exists", !!layer);
  check("overlay-exists", !!overlay);
  if (overlay) {
    var pe =
      typeof getComputedStyle === "function"
        ? getComputedStyle(overlay).pointerEvents
        : overlay.style.pointerEvents;
    check("overlay-pointer-events-none", pe === "none", pe);
  }
  if (layer && wrap) {
    var lb = layer.getBoundingClientRect();
    var wb = wrap.getBoundingClientRect();
    check(
      "layer-box-matches-wrap",
      Math.abs(lb.width - wb.width) <= 1 && Math.abs(lb.height - wb.height) <= 1,
      "layer=" + Math.round(lb.width) + "x" + Math.round(lb.height) + " wrap=" + Math.round(wb.width) + "x" + Math.round(wb.height)
    );
  }
  if (overlay && wrap) {
    var ob = overlay.getBoundingClientRect();
    var wb2 = wrap.getBoundingClientRect();
    check(
      "overlay-box-matches-wrap",
      Math.abs(ob.width - wb2.width) <= 1 && Math.abs(ob.height - wb2.height) <= 1,
      "overlay=" + Math.round(ob.width) + "x" + Math.round(ob.height)
    );
  }

  async function settleGarment() {
    await new Promise(function (r) {
      setTimeout(r, 160);
    });
  }

  function dataUrlByteLength(dataUrl) {
    if (!dataUrl || typeof dataUrl !== "string") return 0;
    var comma = dataUrl.indexOf(",");
    var b64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
    return Math.floor((b64.length * 3) / 4);
  }

  function loadImg(url) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        resolve(img);
      };
      img.onerror = function () {
        reject(new Error("img load failed"));
      };
      img.src = url;
    });
  }

  /** Sample center region; blank white background fails. */
  async function pngShowsNonBlankGarment(dataUrl) {
    var img = await loadImg(dataUrl);
    var c = document.createElement("canvas");
    c.width = img.naturalWidth || img.width;
    c.height = img.naturalHeight || img.height;
    var ctx = c.getContext("2d");
    ctx.drawImage(img, 0, 0);
    var w = c.width;
    var h = c.height;
    var samples = [
      [Math.floor(w * 0.5), Math.floor(h * 0.35)],
      [Math.floor(w * 0.5), Math.floor(h * 0.5)],
      [Math.floor(w * 0.35), Math.floor(h * 0.45)],
      [Math.floor(w * 0.65), Math.floor(h * 0.45)],
    ];
    var nonWhite = 0;
    for (var i = 0; i < samples.length; i++) {
      var px = ctx.getImageData(samples[i][0], samples[i][1], 1, 1).data;
      if (!(px[0] > 250 && px[1] > 250 && px[2] > 250 && px[3] > 200)) {
        nonWhite += 1;
      }
    }
    return nonWhite >= 2;
  }

  if (!window.__cHook) {
    window.__cHook = true;
    window.__commits = [];
    BlytzEditor.onCommittedChange(function () {
      window.__commits.push(1);
    });
  }

  BlytzEditor.setGarmentState({ template: "tee", color: "white" });
  await settleGarment();
  await BlytzEditor.setActiveView("front");
  await settleGarment();
  check(
    "css-vars-on-wrap",
    !!(wrap && wrap.style.getPropertyValue("--garment")),
    wrap && wrap.style.getPropertyValue("--garment")
  );
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

  // --- Every garment × view: layers + export markups (no var() ) ---
  var garmentIds = ["tee", "polo", "hoodie", "jersey"];
  var viewIds = ["front", "back"];
  var colorIds = ["white", "black", "navy", "red"];
  var g;
  var v;
  for (g = 0; g < garmentIds.length; g++) {
    for (v = 0; v < viewIds.length; v++) {
      var gid = garmentIds[g];
      var vid = viewIds[v];
      BlytzEditor.setGarmentState({ template: gid, color: "navy" });
      await BlytzEditor.setActiveView(vid);
      await settleGarment();
      var underEl = document.getElementById("editor-garment-layer");
      var overEl = document.getElementById("editor-garment-overlay");
      check(
        "layers-" + gid + "-" + vid,
        !!(underEl && overEl),
        underEl && overEl ? "ok" : "missing"
      );
      if (overEl) {
        var pe2 =
          typeof getComputedStyle === "function"
            ? getComputedStyle(overEl).pointerEvents
            : overEl.style.pointerEvents;
        check("over-pe-" + gid + "-" + vid, pe2 === "none", pe2);
      }
      try {
        var markups = await BlytzGarments.getExportLayerMarkups(gid, "navy", vid);
        var joined = (markups.under || "") + (markups.over || "");
        check(
          "export-no-var-" + gid + "-" + vid,
          joined.indexOf("var(") < 0,
          joined.indexOf("var(") >= 0 ? "var( remains" : "baked"
        );
        check(
          "export-has-under-over-" + gid + "-" + vid,
          !!(markups.under && markups.over && markups.under.length > 100)
        );
      } catch (err) {
        check("export-no-var-" + gid + "-" + vid, false, String(err && err.message));
      }
    }
  }

  // --- getPreviewPNG for every garment/view (+ color samples) ---
  await BlytzEditor.setActiveView("front");
  await settleGarment();
  window.__commits.length = 0;
  var previewCombos = [];
  for (g = 0; g < garmentIds.length; g++) {
    for (v = 0; v < viewIds.length; v++) {
      previewCombos.push({ template: garmentIds[g], view: viewIds[v], color: "white" });
      previewCombos.push({ template: garmentIds[g], view: viewIds[v], color: "black" });
    }
  }
  // A few extra colors on tee only (keeps runtime reasonable).
  previewCombos.push({ template: "tee", view: "front", color: "navy" });
  previewCombos.push({ template: "tee", view: "back", color: "red" });

  var activeBeforePreviews = BlytzEditor.getActiveView();
  for (var p = 0; p < previewCombos.length; p++) {
    var combo = previewCombos[p];
    BlytzEditor.setGarmentState({ template: combo.template, color: combo.color });
    await settleGarment();
    var label = combo.template + "-" + combo.view + "-" + combo.color;
    try {
      var url = await BlytzEditor.getPreviewPNG({
        view: combo.view,
        includeGarment: true,
      });
      check(
        "preview-png-" + label,
        typeof url === "string" && url.indexOf("data:image/png") === 0,
        url ? "len=" + url.length : "null"
      );
      var bytes = dataUrlByteLength(url);
      check(
        "preview-size-cap-" + label,
        bytes > 500 && bytes <= 5 * 1024 * 1024,
        bytes + " bytes"
      );
      var img2 = await loadImg(url);
      check(
        "preview-dims-" + label,
        (img2.naturalWidth || img2.width) === 800 &&
          (img2.naturalHeight || img2.height) === 800,
        (img2.naturalWidth || img2.width) + "x" + (img2.naturalHeight || img2.height)
      );
      var showsGarment = await pngShowsNonBlankGarment(url);
      check("preview-shows-garment-" + label, showsGarment);
    } catch (previewErr) {
      check("preview-png-" + label, false, String(previewErr && previewErr.message));
    }
  }
  check(
    "preview-no-live-view-change",
    BlytzEditor.getActiveView() === activeBeforePreviews,
    BlytzEditor.getActiveView()
  );
  check(
    "preview-0-commits",
    window.__commits.length === 0,
    window.__commits.length
  );

  // resolveSvgCssVars unit checks (exact strings)
  try {
    var sample =
      'fill="' +
      BlytzGarments.SVG_VAR_TRIM +
      '" stroke="' +
      BlytzGarments.SVG_VAR_GARMENT +
      '" d="' +
      BlytzGarments.SVG_VAR_STRING +
      '"';
    var resolved = BlytzGarments.resolveSvgCssVars(sample, {
      garment: "#111111",
      trim: "#ffffff",
      string: "#e9e5da",
    });
    check(
      "resolve-vars-order",
      resolved.indexOf("var(") < 0 &&
        resolved.indexOf("#ffffff") >= 0 &&
        resolved.indexOf("#111111") >= 0,
      resolved
    );
  } catch (resolveErr) {
    check("resolve-vars-order", false, String(resolveErr && resolveErr.message));
  }

  var ok = results.every(function (r) {
    return r.pass;
  });
  console.log(ok ? "ALL PASS" : "SOME FAILED", results.length);
  return { ok: ok, results: results };
}
console.log("[blytzGarmentChecks] ready — run: await blytzGarmentChecks()");
