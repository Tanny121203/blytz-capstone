/**
 * Fabric.js workspace for the Blytz design editor.
 * Logical size: 800×800 (provisional working canvas, not production print size).
 * Public API lives on window.BlytzEditor (see editor_contract.js).
 */
(function (global) {
  "use strict";

  var fabricVersionOk = !!(
    global.fabric &&
    String(global.fabric.version) === "6.6.1"
  );
  if (global.fabric && !fabricVersionOk) {
    console.warn(
      "BlytzCanvas: Fabric " +
        String(global.fabric.version) +
        " detected; multi-select workaround and several behaviors were verified only against 6.6.1."
    );
  }

  var LOGICAL_SIZE = 800;
  var SCHEMA_VERSION = 1;
  /** Max UTF-8 bytes for serialized canvas_json (whole envelope) in Save/Submit. */
  var MAX_CANVAS_JSON_BYTES = 2 * 1024 * 1024;
  /** Soft budget for image inserts (fraction of MAX_CANVAS_JSON_BYTES). */
  var IMAGE_INSERT_BUDGET_RATIO = 0.8;
  /** Input file size limit before decode (bytes). Replaces former MAX_IMAGE_BYTES. */
  var IMAGE_INPUT_LIMIT_BYTES = 8 * 1024 * 1024;
  /** Longest edge after downscale (px). Keep older phones smooth (≤2000). */
  var IMAGE_MAX_EDGE = 2000;
  /** Target encoded size after downscale (bytes). */
  var IMAGE_TARGET_BYTES = 300 * 1024;
  var IMAGE_QUALITY_STEPS = [0.85, 0.75, 0.6, 0.5];
  var IMAGE_EDGE_STEPS = [2000, 1600, 1200, 1000, 800];
  /** Reject decoded images with more pixels than this. */
  var IMAGE_MAX_PIXELS = 40000000;
  var ALLOWED_IMAGE_TYPES = {
    "image/png": true,
    "image/jpeg": true,
    "image/jpg": true,
    "image/webp": true,
  };
  /** Web-safe fonts for text tools / later properties panel. */
  var ALLOWED_FONTS = [
    "Arial",
    "Verdana",
    "Georgia",
    "Times New Roman",
    "Courier New",
    "Impact",
  ];
  var DEFAULT_SHAPE_FILL = "#1a1a1a";
  var DEFAULT_SHAPE_MAX_EDGE = 200;
  var INSERT_CASCADE_STEP = 24;
  var INSERT_CASCADE_MAX_STEPS = 5;

  /**
   * Types accepted by validateCanvasJSON (suggestions / preview / apply).
   * Case-insensitive. Groups not allowed yet.
   * Found in product code today: IText, Rect (AI mock); IText (addText); Image (addImage).
   */
  var ALLOWED_OBJECT_TYPES = {
    rect: true,
    ellipse: true,
    circle: true,
    line: true,
    polygon: true,
    path: true,
    text: true,
    itext: true,
    textbox: true,
    image: true,
  };

  var ALLOWED_IMAGE_SRC_PREFIXES = [
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/webp;base64,",
  ];

  /** Extra Fabric props to serialize (visible is a Fabric built-in). */
  var SERIALIZE_PROPS = [
    "selectable",
    "evented",
    "blytzId",
    "blytzName",
    "blytzCurve",
    "blytzLocked",
  ];
  /** Stage B: curved-text metadata + geometry clamps (see apps/designs/text_curve.py). */
  var CURVE_AMOUNT_MIN = 0;
  var CURVE_AMOUNT_MAX = 1;
  var CURVE_BULGE_FACTOR = 0.45;
  var CURVE_META_VERSION = 1;
  /** Color swatches for the properties panel (native picker + presets). */
  var COLOR_PRESETS = [
    "#000000",
    "#ffffff",
    "#e11d48",
    "#f97316",
    "#eab308",
    "#16a34a",
    "#2563eb",
    "#7c3aed",
  ];
  /** Clamp limits for property edits. */
  var PROP_LIMITS = {
    opacityMin: 0,
    opacityMax: 1,
    rotationMin: 0,
    rotationMax: 359,
    strokeWidthMin: 0,
    strokeWidthMax: 50,
    fontSizeMin: 8,
    fontSizeMax: 300,
    sizeMin: 8,
    sizeMax: 1600,
    posMin: -400,
    posMax: 1200,
    textMin: 1,
    textMax: 200,
    /** Layer rename (blytzName) max length after trim. */
    layerNameMax: 60,
    /** Fabric charSpacing is 1/1000 em of fontSize. */
    charSpacingMin: -200,
    charSpacingMax: 800,
    /** Fabric lineHeight is a line-box multiplier (default ~1.16). */
    lineHeightMin: 0.8,
    lineHeightMax: 2.5,
  };

  var TEXT_ALIGN_VALUES = ["left", "center", "right"];

  var fabricCanvas = null;
  var getJSONRef = null;
  var loadGeneration = 0;
  var suppressCommit = false;
  var lastLoadError = "";
  var resizeObserver = null;
  var lastAppliedDisplaySize = 0;
  var resizeApplyScheduled = false;
  var toolsWired = false;
  var eventsBound = false;
  var blytzIdSeq = 0;
  var multiSelectMode = false;
  var multiSelectPointerWired = false;
  var contextMenuWired = false;
  var touchHandlesApplied = false;
  var insertCascadeStep = 0;
  var textAtEditStart = null;
  /** Optional UI message sink (panel live region); falls back to tool feedback. */
  var messageSink = null;

  /** B1 two-view engine: live Fabric = active view; inactive snapshots in viewStore. */
  var activeView = "front";
  var viewStore = { back: null };
  var viewChangeListeners = [];
  /** VIEW_SWITCH_DURING_AI_PREVIEW switch (prompt): blocked while AI candidates pending. */
  var VIEW_SWITCH_DURING_AI_PREVIEW = "blocked";
  var garmentState = { template: "tee", color: "black" };
  var garmentChangeListeners = [];

  /** Internal hooks for history / chrome listeners. */
  var beforeCommitHooks = [];
  var afterCommitHooks = [];

  /** Stage 1: non-blocking print-area overflow warning (DOM only; never Fabric). */
  var PRINT_OVERFLOW_EPS = 1e-6;
  var printOverflowRaf = 0;
  var printOverflowWired = false;
  var lastPrintOverflowState = {
    overflow: false,
    defined: false,
    reason: "uninitialized",
    count: 0,
  };

  /** Undo / redo stack (full envelope snapshots). Additive; does not change JSON schema. */
  var HISTORY_MAX = 40;
  var historyStack = [];
  /** Parallel to historyStack: active garment view at each snapshot ("front"|"back"). */
  var historyActiveViews = [];
  var historyIndex = -1;
  var historyApplying = false;
  var historySeeded = false;
  var historyUiListeners = [];

  /** Two-finger pinch-zoom / pan of the Fabric viewport. */
  var gesturePointers = new Map();
  var gestureLastDist = 0;
  var gestureLastCenter = null;
  var gestureActive = false;
  var gesturesWired = false;
  /**
   * Option A viewport zoom: CSS transform on #editor-artboard-scene only.
   * Fabric viewportTransform stays identity. Twin: apps/designs/canvas_zoom.py.
   */
  var ZOOM_MIN = 0.35;
  var ZOOM_MAX = 4;
  var ZOOM_STEP_FACTOR = 1.1;
  var sceneZoom = 1;
  var scenePanX = 0;
  var scenePanY = 0;
  var zoomUiListeners = [];
  var zoomChromeWired = false;
  /** Desktop Space / middle-button scene pan (Option A CSS pan). */
  var scenePanWired = false;
  var spacePanHeld = false;
  var scenePanDrag = null;

  function fabricNS() {
    return global.fabric;
  }

  function utf8ByteLength(str) {
    if (typeof TextEncoder !== "undefined") {
      return new TextEncoder().encode(str).length;
    }
    return unescape(encodeURIComponent(str)).length;
  }

  function setToolFeedback(msg) {
    document.querySelectorAll("[data-editor-tool-feedback]").forEach(function (el) {
      el.textContent = msg || "";
    });
    var status = document.querySelector("[data-editor-status]");
    if (status && msg) status.textContent = msg;
    if (typeof messageSink === "function") {
      try {
        messageSink(msg || "");
      } catch (err) {
        /* ignore sink errors */
      }
    }
  }

  function setMessageSink(fn) {
    messageSink = typeof fn === "function" ? fn : null;
  }

  function nextInsertCenter() {
    var offset = (insertCascadeStep % (INSERT_CASCADE_MAX_STEPS + 1)) * INSERT_CASCADE_STEP;
    insertCascadeStep += 1;
    if (insertCascadeStep > INSERT_CASCADE_MAX_STEPS) insertCascadeStep = 0;
    var half = DEFAULT_SHAPE_MAX_EDGE / 2;
    var cx = Math.min(LOGICAL_SIZE - half, Math.max(half, LOGICAL_SIZE / 2 + offset));
    var cy = Math.min(LOGICAL_SIZE - half, Math.max(half, LOGICAL_SIZE / 2 + offset));
    return { left: cx, top: cy };
  }

  function emptyFabricCanvasObject() {
    return { version: (fabricNS() && fabricNS().version) || "6.6.1", objects: [] };
  }

  function emptyEnvelope() {
    return {
      schema_version: SCHEMA_VERSION,
      width: LOGICAL_SIZE,
      height: LOGICAL_SIZE,
      canvas: emptyFabricCanvasObject(),
      views: { back: emptyFabricCanvasObject() },
    };
  }

  function cloneFabricPayload(payload) {
    return JSON.parse(JSON.stringify(payload || emptyFabricCanvasObject()));
  }

  function snapshotLiveCanvas() {
    if (!fabricCanvas) return emptyFabricCanvasObject();
    return fabricCanvas.toObject(SERIALIZE_PROPS);
  }

  function forceTransparentBackground() {
    if (!fabricCanvas) return;
    fabricCanvas.backgroundColor = "";
    if (typeof fabricCanvas.setBackgroundColor === "function") {
      try {
        fabricCanvas.setBackgroundColor("", fabricCanvas.requestRenderAll.bind(fabricCanvas));
      } catch (err) {
        fabricCanvas.backgroundColor = "";
      }
    }
    sanitizeCanvasDom();
    fabricCanvas.requestRenderAll();
  }

  function defaultContrastFill() {
    var g = global.BlytzGarments;
    if (g && typeof g.contrastColor === "function" && typeof g.colorById === "function") {
      var c = g.colorById(garmentState.color);
      return g.contrastColor(c && c.hex ? c.hex : "#ffffff");
    }
    return "#111111";
  }

  function refreshGarmentLayer() {
    var g = global.BlytzGarments;
    var done = function (value) {
      schedulePrintOverflowCheck();
      return value;
    };
    if (g && typeof g.renderGarmentLayer === "function") {
      try {
        var result = g.renderGarmentLayer(
          garmentState.template,
          garmentState.color,
          activeView
        );
        return result && typeof result.then === "function"
          ? result.then(done, function (err) {
              schedulePrintOverflowCheck();
              throw err;
            })
          : Promise.resolve(done(result));
      } catch (err) {
        console.warn("BlytzCanvas: garment layer render failed", err);
        schedulePrintOverflowCheck();
        return Promise.resolve(null);
      }
    }
    schedulePrintOverflowCheck();
    return Promise.resolve(null);
  }

  /**
   * Axis-aligned containment. Callers must pass transformed bounds
   * (Fabric getBoundingRect) for rotated/scaled objects.
   * Edges may touch (boundary = inside). Must match print_area_check.py.
   */
  function printAreaContainsRect(area, rect, eps) {
    if (eps == null) eps = PRINT_OVERFLOW_EPS;
    if (!area || !rect) return false;
    var ax = Number(area.x);
    var ay = Number(area.y);
    var aw = Number(area.w != null ? area.w : area.width);
    var ah = Number(area.h != null ? area.h : area.height);
    var left = Number(rect.left != null ? rect.left : rect.x);
    var top = Number(rect.top != null ? rect.top : rect.y);
    var width = Number(rect.width != null ? rect.width : rect.w);
    var height = Number(rect.height != null ? rect.height : rect.h);
    if (!(aw > 0) || !(ah > 0) || !(width > 0) || !(height > 0)) return false;
    if (isNaN(ax) || isNaN(ay) || isNaN(left) || isNaN(top)) return false;
    return (
      left >= ax - eps &&
      top >= ay - eps &&
      left + width <= ax + aw + eps &&
      top + height <= ay + ah + eps
    );
  }

  /**
   * True when any artwork rect is not fully inside at least one print area.
   * Multiple areas are OR'd. Empty areas → false (caller treats as undefined).
   */
  function artworkOverflowsPrintAreas(areas, rects, eps) {
    if (!areas || !areas.length) return false;
    var list = rects || [];
    var i;
    var j;
    for (i = 0; i < list.length; i++) {
      var rect = list[i];
      if (!rect) continue;
      var contained = false;
      for (j = 0; j < areas.length; j++) {
        if (printAreaContainsRect(areas[j], rect, eps)) {
          contained = true;
          break;
        }
      }
      if (!contained) return true;
    }
    return false;
  }

  function evaluatePrintOverflow(areasResult, rects) {
    areasResult = areasResult || {};
    if (!areasResult.ok) {
      return {
        overflow: false,
        defined: false,
        reason: areasResult.reason || "no_print_areas",
        count: 0,
      };
    }
    var areas = areasResult.areas || [];
    var list = rects || [];
    var overflow = artworkOverflowsPrintAreas(areas, list);
    return {
      overflow: overflow,
      defined: true,
      reason: overflow ? "overflow" : "ok",
      count: list.length,
    };
  }

  /**
   * Transformed AABB for each canvas object in logical 800×800 space.
   * Fabric 6 getBoundingRect() uses getCoords() (object transform included).
   * Does not mutate objects. ActiveSelection is not on getObjects().
   */
  function collectArtworkBounds(canvas) {
    if (!canvas || typeof canvas.getObjects !== "function") return [];
    var objects = canvas.getObjects();
    var rects = [];
    var i;
    for (i = 0; i < objects.length; i++) {
      var obj = objects[i];
      if (!obj || typeof obj.getBoundingRect !== "function") continue;
      var br;
      try {
        // Fabric 6: no absolute flag; extra args are ignored if present.
        br = obj.getBoundingRect();
      } catch (err) {
        continue;
      }
      if (!br) continue;
      var width = Number(br.width);
      var height = Number(br.height);
      if (!(width > 0) || !(height > 0)) continue;
      rects.push({
        left: Number(br.left),
        top: Number(br.top),
        width: width,
        height: height,
      });
    }
    return rects;
  }

  function evaluateCurrentPrintOverflow() {
    var g = global.BlytzGarments;
    if (!g || typeof g.getPrintAreas !== "function") {
      return {
        overflow: false,
        defined: false,
        reason: "no_print_api",
        count: 0,
      };
    }
    var areasResult = g.getPrintAreas(garmentState.template, activeView);
    var rects = collectArtworkBounds(fabricCanvas);
    return evaluatePrintOverflow(areasResult, rects);
  }

  var PRINT_OVERFLOW_MSG =
    "Artwork extends outside the printable area. Nothing was moved — you can still edit and save, but parts outside the guide may not print.";

  function updatePrintOverflowDom(state) {
    var next = state || {
      overflow: false,
      defined: false,
      reason: "undefined",
      count: 0,
    };
    var el = document.getElementById("editor-print-overflow-warning");
    // Skip no-op DOM writes so show/hide churn cannot poke layout mid-drag.
    if (
      lastPrintOverflowState &&
      lastPrintOverflowState.overflow === next.overflow &&
      lastPrintOverflowState.defined === next.defined &&
      lastPrintOverflowState.reason === next.reason
    ) {
      lastPrintOverflowState = next;
      return;
    }
    lastPrintOverflowState = next;
    if (!el) return;
    if (!next.defined) {
      el.hidden = true;
      el.setAttribute("aria-hidden", "true");
      el.textContent = "";
      el.dataset.reason = next.reason || "undefined";
      el.dataset.overflow = "0";
      return;
    }
    if (next.overflow) {
      el.hidden = false;
      el.setAttribute("aria-hidden", "false");
      el.dataset.reason = "overflow";
      el.dataset.overflow = "1";
      if (el.textContent !== PRINT_OVERFLOW_MSG) {
        el.textContent = PRINT_OVERFLOW_MSG;
      }
      return;
    }
    el.hidden = true;
    el.setAttribute("aria-hidden", "true");
    el.textContent = "";
    el.dataset.reason = "ok";
    el.dataset.overflow = "0";
  }

  function applyPrintOverflowWarning() {
    updatePrintOverflowDom(evaluateCurrentPrintOverflow());
  }

  function schedulePrintOverflowCheck() {
    if (typeof global.requestAnimationFrame !== "function") {
      applyPrintOverflowWarning();
      return;
    }
    if (printOverflowRaf) return;
    printOverflowRaf = global.requestAnimationFrame(function () {
      printOverflowRaf = 0;
      applyPrintOverflowWarning();
    });
  }

  function wirePrintOverflowChecks() {
    if (printOverflowWired || !fabricCanvas) return;
    printOverflowWired = true;
    fabricCanvas.on("object:moving", schedulePrintOverflowCheck);
    fabricCanvas.on("object:scaling", schedulePrintOverflowCheck);
    fabricCanvas.on("object:rotating", schedulePrintOverflowCheck);
    fabricCanvas.on("object:skewing", schedulePrintOverflowCheck);
    afterCommitHooks.push(function () {
      schedulePrintOverflowCheck();
    });
    schedulePrintOverflowCheck();
  }

  function getPrintOverflowState() {
    return {
      overflow: !!lastPrintOverflowState.overflow,
      defined: !!lastPrintOverflowState.defined,
      reason: lastPrintOverflowState.reason || "",
      count: lastPrintOverflowState.count || 0,
    };
  }

  function aiCandidatesPending() {
    var ai = global.BlytzAIChat;
    if (!ai || typeof ai.getState !== "function") return false;
    var st = ai.getState();
    return !!(st && st.candidateCount > 0 && !st.committed);
  }

  function isLegacyEmpty(data) {
    if (!data || typeof data !== "object" || Array.isArray(data)) return true;
    if (Object.prototype.hasOwnProperty.call(data, "schema_version")) return false;
    var objects = data.objects;
    if (objects == null) return true;
    return Array.isArray(objects) && objects.length === 0;
  }

  function isBlytzV1(data) {
    return (
      data &&
      typeof data === "object" &&
      data.schema_version === SCHEMA_VERSION &&
      data.canvas &&
      typeof data.canvas === "object" &&
      !Array.isArray(data.canvas)
    );
  }

  function isRawFabricCanvas(data) {
    return (
      data &&
      typeof data === "object" &&
      typeof data.version === "string" &&
      Array.isArray(data.objects)
    );
  }

  function isUnsupportedLegacy(data) {
    if (!data || typeof data !== "object") return false;
    if (Object.prototype.hasOwnProperty.call(data, "schema_version")) return false;
    if (isRawFabricCanvas(data)) return false;
    return Array.isArray(data.objects) && data.objects.length > 0;
  }

  function isUnknownSchemaVersion(data) {
    return (
      data &&
      typeof data === "object" &&
      Object.prototype.hasOwnProperty.call(data, "schema_version") &&
      data.schema_version !== SCHEMA_VERSION
    );
  }

  /**
   * Normalize incoming design JSON.
   * @returns {{
   *   ok: boolean,
   *   blockPersist: boolean,
   *   message: string,
   *   kind: string,
   *   envelope: object,
   *   fabricPayload: object
   * }}
   */
  function parseInput(json) {
    lastLoadError = "";
    if (typeof json === "string") {
      try {
        json = JSON.parse(json);
      } catch (e) {
        lastLoadError =
          "This design could not be read (invalid JSON). Saving is blocked so your stored design is not overwritten. Reload the page or go back.";
        return {
          ok: false,
          blockPersist: true,
          message: lastLoadError,
          kind: "malformed",
          envelope: emptyEnvelope(),
          fabricPayload: emptyFabricCanvasObject(),
        };
      }
    }
    if (!json || typeof json !== "object" || Array.isArray(json)) {
      return {
        ok: true,
        blockPersist: false,
        message: "",
        kind: "empty",
        envelope: emptyEnvelope(),
        fabricPayload: emptyFabricCanvasObject(),
      };
    }
    if (isUnknownSchemaVersion(json)) {
      lastLoadError =
        "This design uses an unsupported canvas schema version (" +
        String(json.schema_version) +
        "). Saving is blocked so the original is not overwritten. Reload or go back.";
      return {
        ok: false,
        blockPersist: true,
        message: lastLoadError,
        kind: "unsupported_schema",
        envelope: emptyEnvelope(),
        fabricPayload: emptyFabricCanvasObject(),
      };
    }
    if (isBlytzV1(json)) {
      var envelopeV1 = {
        schema_version: SCHEMA_VERSION,
        width: typeof json.width === "number" ? json.width : LOGICAL_SIZE,
        height: typeof json.height === "number" ? json.height : LOGICAL_SIZE,
        canvas: json.canvas,
      };
      // Additive views key (B1): carry through; do not drop unknown-to-legacy keys here.
      if (Object.prototype.hasOwnProperty.call(json, "views")) {
        envelopeV1.views = json.views;
      }
      return {
        ok: true,
        blockPersist: false,
        message: "",
        kind: "blytz_v1",
        envelope: envelopeV1,
        fabricPayload: json.canvas,
      };
    }
    if (isLegacyEmpty(json)) {
      return {
        ok: true,
        blockPersist: false,
        message: "",
        kind: "legacy_empty",
        envelope: emptyEnvelope(),
        fabricPayload: emptyFabricCanvasObject(),
      };
    }
    if (isRawFabricCanvas(json)) {
      return {
        ok: true,
        blockPersist: false,
        message: "",
        kind: "raw_fabric",
        envelope: {
          schema_version: SCHEMA_VERSION,
          width: LOGICAL_SIZE,
          height: LOGICAL_SIZE,
          canvas: json,
        },
        fabricPayload: json,
      };
    }
    if (isUnsupportedLegacy(json)) {
      lastLoadError =
        "This design uses an unsupported legacy canvas format. Saving is blocked so the original is not overwritten. Reload or go back.";
      return {
        ok: false,
        blockPersist: true,
        message: lastLoadError,
        kind: "unsupported_legacy",
        envelope: emptyEnvelope(),
        fabricPayload: emptyFabricCanvasObject(),
      };
    }
    lastLoadError =
      "Unrecognized canvas data. Saving is blocked so the original is not overwritten. Reload or go back.";
    return {
      ok: false,
      blockPersist: true,
      message: lastLoadError,
      kind: "unrecognized",
      envelope: emptyEnvelope(),
      fabricPayload: emptyFabricCanvasObject(),
    };
  }

  function imageSrcAllowed(src) {
    if (typeof src !== "string" || !src) return false;
    var lower = src.toLowerCase();
    for (var i = 0; i < ALLOWED_IMAGE_SRC_PREFIXES.length; i++) {
      if (lower.indexOf(ALLOWED_IMAGE_SRC_PREFIXES[i]) === 0) return true;
    }
    return false;
  }

  /**
   * Suggestion allowlist — delegates to scanCanvasPayload (shared safety rules).
   * Must stay identical to apps/designs/canvas_safety.py.
   */
  function validateObjectsAllowlist(objects) {
    if (!Array.isArray(objects)) {
      return { ok: false, error: "Suggestion canvas.objects must be an array." };
    }
    var scanned = scanCanvasPayload({
      schema_version: SCHEMA_VERSION,
      canvas: { objects: objects },
    });
    if (!scanned.ok) {
      return {
        ok: false,
        error: (scanned.reason || "Suggestion failed safety checks.") + " Please retry.",
      };
    }
    return { ok: true };
  }

  function runHooks(hooks, label, snapshot) {
    if (!hooks || !hooks.length) return;
    for (var i = 0; i < hooks.length; i++) {
      try {
        hooks[i](label, snapshot);
      } catch (err) {
        console.error("BlytzCanvas commit hook error", err);
      }
    }
  }

  function syncHistoryUi() {
    historyUiListeners.forEach(function (cb) {
      try {
        cb({ canUndo: canUndo(), canRedo: canRedo() });
      } catch (err) {
        /* ignore */
      }
    });
    document.querySelectorAll("[data-editor-undo]").forEach(function (btn) {
      btn.disabled = !canUndo();
    });
    document.querySelectorAll("[data-editor-redo]").forEach(function (btn) {
      btn.disabled = !canRedo();
    });
  }

  function canUndo() {
    return historyIndex > 0;
  }

  function canRedo() {
    return historyIndex >= 0 && historyIndex < historyStack.length - 1;
  }

  function currentHistoryView() {
    return activeView === "back" ? "back" : "front";
  }

  function pushHistorySnapshot(snapshot) {
    if (historyApplying || !snapshot) return;
    var serialized;
    try {
      serialized = JSON.stringify(snapshot);
    } catch (err) {
      return;
    }
    if (
      historyIndex >= 0 &&
      historyStack[historyIndex] === serialized
    ) {
      return;
    }
    historyStack = historyStack.slice(0, historyIndex + 1);
    historyActiveViews = historyActiveViews.slice(0, historyIndex + 1);
    historyStack.push(serialized);
    historyActiveViews.push(currentHistoryView());
    if (historyStack.length > HISTORY_MAX) {
      historyStack.shift();
      historyActiveViews.shift();
    }
    historyIndex = historyStack.length - 1;
    historySeeded = true;
    syncHistoryUi();
  }

  function seedHistory(snapshot) {
    if (historySeeded || !snapshot) return;
    historyStack = [JSON.stringify(snapshot)];
    historyActiveViews = [currentHistoryView()];
    historyIndex = 0;
    historySeeded = true;
    syncHistoryUi();
  }

  function restoreHistoryAt(index) {
    if (index < 0 || index >= historyStack.length) return Promise.resolve(false);
    var envelope;
    try {
      envelope = JSON.parse(historyStack[index]);
    } catch (err) {
      return Promise.resolve(false);
    }
    var preferredView =
      historyActiveViews[index] === "back" ? "back" : "front";
    historyApplying = true;
    historyIndex = index;
    syncHistoryUi();
    var prevSuppress = suppressCommit;
    suppressCommit = true;
    ensureCanvas(getJSONRef);
    var loadPromise =
      typeof loadAllViewsFromEnvelope === "function"
        ? loadAllViewsFromEnvelope(envelope, getJSONRef, preferredView)
        : loadFabricPayload(envelope && envelope.canvas, getJSONRef);
    return Promise.resolve(loadPromise)
      .catch(function () {
        return null;
      })
      .then(function () {
        suppressCommit = prevSuppress;
        historyApplying = false;
        syncHistoryUi();
        setToolFeedback(index < historyStack.length - 1 ? "Undone." : "Redone.");
        return true;
      });
  }

  function undo() {
    if (!canUndo()) return Promise.resolve(false);
    return restoreHistoryAt(historyIndex - 1);
  }

  function redo() {
    if (!canRedo()) return Promise.resolve(false);
    return restoreHistoryAt(historyIndex + 1);
  }

  function onHistoryChange(cb) {
    if (typeof cb === "function") historyUiListeners.push(cb);
    return function () {
      historyUiListeners = historyUiListeners.filter(function (fn) {
        return fn !== cb;
      });
    };
  }

  function notifyCommitted(getJSON, label) {
    if (suppressCommit) return;
    var listeners = global.BlytzEditor && global.BlytzEditor._commitListeners;
    var snapshot = typeof getJSON === "function" ? getJSON() : null;
    runHooks(beforeCommitHooks, label || "commit", snapshot);
    if (listeners && listeners.length) {
      listeners.forEach(function (cb) {
        try {
          cb(snapshot);
        } catch (err) {
          console.error("BlytzEditor onCommittedChange error", err);
        }
      });
    }
    if (!historyApplying && snapshot) {
      if (!historySeeded) seedHistory(snapshot);
      else pushHistorySnapshot(snapshot);
    }
    runHooks(afterCommitHooks, label || "commit", snapshot);
  }

  /**
   * Central mutation pathway: suppress per-event noise, then one notifyCommitted.
   * applyFn may return false to skip the commit notification.
   */
  function commitEdit(label, applyFn, getJSON) {
    var jsonFn = getJSON || getJSONRef;
    var prev = suppressCommit;
    suppressCommit = true;
    var changed = false;
    try {
      var result = applyFn();
      changed = result !== false;
    } finally {
      suppressCommit = prev;
    }
    if (changed) {
      notifyCommitted(jsonFn, label || "edit");
    }
    return changed;
  }

  var textEditDirty = false;
  /** Ignore object:modified shortly after text:editing:exited (Fabric often double-fires). */
  var suppressModifiedUntil = 0;

  function newBlytzId() {
    blytzIdSeq += 1;
    return (
      "b" +
      blytzIdSeq.toString(36) +
      "_" +
      Math.random().toString(36).slice(2, 8)
    );
  }

  function ensureBlytzIds(canvas) {
    if (!canvas) return;
    var seen = Object.create(null);
    var objects = canvas.getObjects();
    for (var i = 0; i < objects.length; i++) {
      var obj = objects[i];
      var id = obj && obj.blytzId;
      if (typeof id !== "string" || !id || seen[id]) {
        id = newBlytzId();
        obj.blytzId = id;
      }
      seen[id] = true;
    }
  }

  function assignBlytzId(obj) {
    if (!obj) return;
    if (typeof obj.blytzId !== "string" || !obj.blytzId) {
      obj.blytzId = newBlytzId();
    }
  }

  /** Always mint a new id (duplicates must not keep the source id). */
  function forceBlytzId(obj) {
    if (!obj) return;
    obj.blytzId = newBlytzId();
  }

  function assignBlytzName(obj, name) {
    if (!obj || typeof name !== "string" || !name) return;
    if (typeof obj.blytzName !== "string" || !obj.blytzName) {
      obj.blytzName = name;
    }
  }

  /**
   * Layer label for a duplicated object. Keeps names distinct without renaming the source.
   */
  function duplicateLayerName(source) {
    var base = "";
    if (source && typeof source.blytzName === "string" && source.blytzName) {
      base = source.blytzName;
    } else {
      var tk = typeKey(source);
      if (tk === "itext" || tk === "text" || tk === "textbox") {
        var text = source && typeof source.text === "string" ? source.text : "";
        base = text ? text.slice(0, 20) : "Text";
      } else if (tk === "image") base = "Image";
      else if (tk === "rect") base = "Rectangle";
      else if (tk === "ellipse" || tk === "circle") base = "Ellipse";
      else if (tk === "line") base = "Line";
      else if (tk === "path") base = "Path";
      else if (tk === "polygon") base = "Polygon";
      else base = "Object";
    }
    if (/\scopy(?:\s+\d+)?$/i.test(base)) return base;
    return base + " copy";
  }

  function isObjectLocked(obj) {
    return !!(obj && obj.blytzLocked);
  }

  /** Normalize + validate a layer rename. Returns trimmed name or null if rejected. */
  function normalizeLayerName(raw) {
    if (typeof raw !== "string") return null;
    var trimmed = raw.trim();
    if (!trimmed) return null;
    var max =
      PROP_LIMITS.layerNameMax != null ? PROP_LIMITS.layerNameMax : 60;
    if (trimmed.length > max) trimmed = trimmed.slice(0, max);
    return trimmed;
  }

  /**
   * Canvas interaction flags derived from blytzLocked.
   * Locked objects stay visible in JSON + layer list; layer panel may still
   * setActiveObject for management (rename / unlock / duplicate) even when
   * selectable/evented are false — canvas pointer hits will not select them.
   */
  function applyLockInteraction(obj) {
    if (!obj) return;
    if (obj.blytzLocked) {
      obj.set({
        selectable: false,
        evented: false,
        lockMovementX: true,
        lockMovementY: true,
        lockScalingX: true,
        lockScalingY: true,
        lockRotation: true,
        hasControls: false,
      });
    } else {
      obj.set({
        selectable: true,
        evented: true,
        lockMovementX: false,
        lockMovementY: false,
        lockScalingX: false,
        lockScalingY: false,
        lockRotation: false,
        hasControls: true,
      });
    }
    if (typeof obj.setCoords === "function") obj.setCoords();
  }

  function applyLockStateToCanvas(canvas) {
    if (!canvas) return;
    var objects = canvas.getObjects();
    for (var i = 0; i < objects.length; i++) {
      if (objects[i] && objects[i].blytzLocked) {
        applyLockInteraction(objects[i]);
      }
    }
  }

  function findObjectByBlytzId(id) {
    var canvas = fabricCanvas;
    if (!canvas || typeof id !== "string" || !id) return null;
    var objects = canvas.getObjects();
    for (var i = 0; i < objects.length; i++) {
      if (objects[i] && objects[i].blytzId === id) return objects[i];
    }
    return null;
  }

  /**
   * Rename via blytzName only (id / geometry / visibility / lock unchanged).
   * Rejects empty/whitespace. No-op (no history) when unchanged.
   */
  function renameObjectById(id, rawName, getJSON) {
    if (!persistAllowed()) return false;
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var obj = findObjectByBlytzId(id);
    if (!obj) {
      setToolFeedback("Select a layer to rename.");
      return false;
    }
    var next = normalizeLayerName(rawName);
    if (next == null) {
      setToolFeedback("Name cannot be empty.");
      return false;
    }
    if (obj.blytzName === next) return false;
    return commitEdit(
      "rename",
      function () {
        obj.blytzName = next;
        setToolFeedback("Renamed.");
        return true;
      },
      getJSON
    );
  }

  /**
   * Hide/show via Fabric visible. Hidden objects remain in JSON + layer list;
   * canvas hit-testing skips them. Layer panel can still select/show.
   * Hiding a selected object clears canvas selection (no stale Properties).
   */
  function setObjectVisibleById(id, visible, getJSON) {
    if (!persistAllowed()) return false;
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var obj = findObjectByBlytzId(id);
    if (!obj) return false;
    var next = !!visible;
    if (!!obj.visible === next) return false;
    return commitEdit(
      next ? "show" : "hide",
      function () {
        obj.visible = next;
        if (!next) {
          var active = canvas.getActiveObject();
          if (active === obj) {
            canvas.discardActiveObject();
          } else if (active && isActiveSelection(active)) {
            var members = active.getObjects ? active.getObjects() : [];
            for (var i = 0; i < members.length; i++) {
              if (members[i] === obj) {
                canvas.discardActiveObject();
                break;
              }
            }
          }
        }
        if (typeof obj.setCoords === "function") obj.setCoords();
        canvas.requestRenderAll();
        setToolFeedback(next ? "Layer shown." : "Layer hidden.");
        return true;
      },
      getJSON
    );
  }

  function setObjectLockedById(id, locked, getJSON) {
    if (!persistAllowed()) return false;
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var obj = findObjectByBlytzId(id);
    if (!obj) return false;
    var next = !!locked;
    if (!!obj.blytzLocked === next) return false;
    return commitEdit(
      next ? "lock" : "unlock",
      function () {
        obj.blytzLocked = next;
        applyLockInteraction(obj);
        if (next) {
          var active = canvas.getActiveObject();
          // Keep management selection from the layer panel; clear only if the
          // object was canvas-selected and we want to drop transform handles.
          // Layer panel re-selects after toggle when needed.
          if (active === obj) {
            // Re-apply so hasControls stays false while still active for rename.
            applyLockInteraction(obj);
          } else if (active && isActiveSelection(active)) {
            var members = active.getObjects ? active.getObjects() : [];
            for (var i = 0; i < members.length; i++) {
              if (members[i] === obj) {
                canvas.discardActiveObject();
                break;
              }
            }
          }
        }
        canvas.requestRenderAll();
        setToolFeedback(next ? "Layer locked." : "Layer unlocked.");
        return true;
      },
      getJSON
    );
  }

  /**
   * Layer-panel selection: works for locked (selectable false) and hidden objects.
   * This is management selection — canvas pointer hits still respect lock/hide.
   */
  function selectObjectById(id) {
    var canvas = fabricCanvas;
    if (!canvas) return false;
    var obj = findObjectByBlytzId(id);
    if (!obj) return false;
    canvas.setActiveObject(obj);
    canvas.requestRenderAll();
    return true;
  }

  /** Run applyFn without firing commit notifications (live property preview). */
  function runSilent(applyFn) {
    var prev = suppressCommit;
    suppressCommit = true;
    try {
      return applyFn();
    } finally {
      suppressCommit = prev;
    }
  }

  /**
   * Normalize Fabric type strings for branching (e.g. "i-text" → "itext").
   * Does not alter serialized type values on disk / in JSON.
   */
  function typeKey(typeOrObj) {
    var raw = typeOrObj;
    if (typeOrObj && typeof typeOrObj === "object") {
      raw = typeOrObj.type;
    }
    return String(raw || "")
      .toLowerCase()
      .replace(/[^a-z]/g, "");
  }

  function isActiveSelection(obj) {
    if (!obj) return false;
    return typeKey(obj) === "activeselection";
  }

  function isTextObject(obj) {
    var k = typeKey(obj);
    return k === "itext" || k === "text" || k === "textbox";
  }

  function clampCurveAmount(value) {
    var n = Number(value);
    if (typeof n !== "number" || isNaN(n)) return null;
    return Math.min(CURVE_AMOUNT_MAX, Math.max(CURVE_AMOUNT_MIN, n));
  }

  function normalizeCurveDirection(value) {
    return String(value || "up").toLowerCase() === "down" ? "down" : "up";
  }

  function textHasMultipleLines(obj) {
    var t = obj && obj.text != null ? String(obj.text) : "";
    return t.indexOf("\n") >= 0 || t.indexOf("\r") >= 0;
  }

  /**
   * Quadratic arc path `d` for Fabric.Path from measured text width + amount.
   * Returns null when amount is effectively straight.
   */
  function buildArcPathD(width, amount, direction) {
    var w = Number(width);
    var a = clampCurveAmount(amount);
    if (!(w > 0) || a == null || a < 0.001) return null;
    var bulge = a * w * CURVE_BULGE_FACTOR;
    var cy = normalizeCurveDirection(direction) === "down" ? bulge : -bulge;
    return "M 0 0 Q " + w / 2 + " " + cy + " " + w + " 0";
  }

  function measureTextPathWidth(obj) {
    if (!obj) return 0;
    var w = Number(obj.width);
    if (w > 0) return w;
    try {
      if (typeof obj.calcTextWidth === "function") {
        w = Number(obj.calcTextWidth());
        if (w > 0) return w;
      }
    } catch (err) {
      /* ignore */
    }
    var sx = Number(obj.scaleX) || 1;
    var sw =
      typeof obj.getScaledWidth === "function" ? Number(obj.getScaledWidth()) : 0;
    if (sw > 0 && sx > 0) return sw / sx;
    return Math.max(
      String(obj.text || "").length * (Number(obj.fontSize) || 16) * 0.5,
      1
    );
  }

  function clearCurveOnObject(obj) {
    if (!obj) return false;
    obj.set({
      path: null,
      pathSide: undefined,
      pathStartOffset: undefined,
      pathAlign: undefined,
    });
    try {
      delete obj.blytzCurve;
    } catch (err) {
      obj.blytzCurve = undefined;
    }
    if (typeof obj.initDimensions === "function") obj.initDimensions();
    obj.setCoords();
    return true;
  }

  /**
   * Shared mutator used by commit (applyTextCurve) and silent preview.
   * amount ~0 clears the curve. Does not notify history.
   */
  function setCurveOnObject(obj, amount, direction) {
    var fabric = fabricNS();
    if (!obj || !fabric || !fabric.Path) return false;
    var a = clampCurveAmount(amount);
    if (a == null) return false;
    var dir = normalizeCurveDirection(direction);
    if (a < 0.001) {
      return clearCurveOnObject(obj);
    }
    if (obj.path) {
      obj.set("path", null);
      if (typeof obj.initDimensions === "function") obj.initDimensions();
    }
    var width = measureTextPathWidth(obj);
    var d = buildArcPathD(width, a, dir);
    if (!d) {
      clearCurveOnObject(obj);
      return true;
    }
    var path = new fabric.Path(d, {
      visible: false,
      fill: "",
      stroke: "",
      strokeWidth: 1,
    });
    obj.set({
      path: path,
      pathSide: "left",
      pathStartOffset: 0,
      pathAlign: "center",
    });
    obj.blytzCurve = {
      amount: a,
      direction: dir,
      version: CURVE_META_VERSION,
    };
    if (typeof obj.initDimensions === "function") obj.initDimensions();
    obj.setCoords();
    return true;
  }

  /**
   * Silent preview helper for Properties UI. No history entry.
   * opts: { amount: 0..1, direction: "up"|"down", enabled?: boolean }
   */
  function previewTextCurveOnObject(obj, opts) {
    opts = opts || {};
    if (!obj || !isTextObject(obj) || textHasMultipleLines(obj)) return false;
    var canvas = fabricCanvas;
    if (!canvas) return false;
    var enabled = opts.enabled !== false;
    var amount = enabled ? clampCurveAmount(opts.amount) : 0;
    if (amount == null) amount = 0;
    var direction = normalizeCurveDirection(opts.direction);
    return runSilent(function () {
      setCurveOnObject(obj, amount, direction);
      canvas.requestRenderAll();
      return true;
    });
  }

  /**
   * Stage B/C API: curve the active single-line text object (one history entry).
   * opts: { amount: 0..1, direction: "up"|"down" }. amount ~0 clears the curve.
   */
  function applyTextCurve(opts, getJSON) {
    opts = opts || {};
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var obj = canvas.getActiveObject && canvas.getActiveObject();
    if (!obj || isActiveSelection(obj) || !isTextObject(obj)) {
      setToolFeedback("Select a single text object to curve.");
      return false;
    }
    if (isObjectLocked(obj)) {
      setToolFeedback("Unlock the layer to edit curve.");
      return false;
    }
    if (textHasMultipleLines(obj)) {
      setToolFeedback("Curved text supports single-line text only.");
      return false;
    }
    var amount = clampCurveAmount(opts.amount);
    if (amount == null) {
      setToolFeedback("Invalid curve amount.");
      return false;
    }
    var direction = normalizeCurveDirection(opts.direction);
    var jsonFn = getJSON || getJSONRef;
    return commitEdit(
      amount < 0.001 ? "text-curve-clear" : "text-curve",
      function () {
        setCurveOnObject(obj, amount, direction);
        canvas.requestRenderAll();
        setToolFeedback(
          amount < 0.001
            ? "Curve cleared."
            : "Curve " + direction + " (" + Math.round(amount * 100) + "%)."
        );
        return true;
      },
      jsonFn
    );
  }

  function clearTextCurve(getJSON) {
    return applyTextCurve({ amount: 0, direction: "up" }, getJSON);
  }

  /**
   * Shared canvas safety scan (client). Must stay identical to
   * apps/designs/canvas_safety.py — keep both rule sets in sync.
   * Walks envelopes / Fabric canvases; never modifies values.
   * @returns {{ok: boolean, reason: string, path: string}}
   */
  function scanCanvasPayload(envelopeOrCanvas) {
    var MAX_DEPTH = 20;
    var SAFE = ALLOWED_OBJECT_TYPES;
    var URL_KEY = {
      src: true,
      source: true,
      url: true,
      href: true,
      "xlink:href": true,
    };

    function fail(reason, path) {
      return { ok: false, reason: reason || "rejected", path: path || "" };
    }

    function ok() {
      return { ok: true, reason: "", path: "" };
    }

    function dataUrlOk(s) {
      if (typeof s !== "string" || !s) return false;
      var lower = s.toLowerCase();
      for (var i = 0; i < ALLOWED_IMAGE_SRC_PREFIXES.length; i++) {
        if (lower.indexOf(ALLOWED_IMAGE_SRC_PREFIXES[i]) === 0) return true;
      }
      return false;
    }

    function scanUrlKeys(node, path, depth) {
      if (depth > MAX_DEPTH) return fail("Exceeded maximum nesting depth.", path);
      if (!node || typeof node !== "object") return ok();
      if (Array.isArray(node)) {
        for (var i = 0; i < node.length; i++) {
          var ra = scanUrlKeys(node[i], path + "[" + i + "]", depth + 1);
          if (!ra.ok) return ra;
        }
        return ok();
      }
      var keys = Object.keys(node);
      for (var k = 0; k < keys.length; k++) {
        var key = keys[k];
        var val = node[key];
        var keyLower = String(key).toLowerCase();
        if (key === "text") {
          continue;
        }
        if (URL_KEY[key] || URL_KEY[keyLower] || keyLower === "xlink:href") {
          if (typeof val === "string" && !dataUrlOk(val)) {
            return fail(
              "External or unsafe image source is not allowed.",
              path + "." + key
            );
          }
        }
        if (val && typeof val === "object") {
          var rb = scanUrlKeys(val, path + "." + key, depth + 1);
          if (!rb.ok) return rb;
        }
      }
      return ok();
    }

    function scanFabricObject(obj, path, depth) {
      if (depth > MAX_DEPTH) return fail("Exceeded maximum nesting depth.", path);
      if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
        return fail("Invalid canvas object.", path);
      }
      var tk = typeKey(obj);
      if (!SAFE[tk]) {
        return fail(
          "Unsupported object type (“" + String(obj.type || "unknown") + "”).",
          path + ".type"
        );
      }
      if (obj.fill && typeof obj.fill === "object" && !Array.isArray(obj.fill)) {
        if (Object.prototype.hasOwnProperty.call(obj.fill, "source")) {
          return fail("Pattern fills are not allowed.", path + ".fill");
        }
      }
      if (obj.stroke && typeof obj.stroke === "object" && !Array.isArray(obj.stroke)) {
        if (Object.prototype.hasOwnProperty.call(obj.stroke, "source")) {
          return fail("Pattern strokes are not allowed.", path + ".stroke");
        }
      }
      if (obj.backgroundImage != null) {
        return fail("backgroundImage is not allowed.", path + ".backgroundImage");
      }
      if (obj.overlayImage != null) {
        return fail("overlayImage is not allowed.", path + ".overlayImage");
      }
      if (obj.objects != null) {
        if (!Array.isArray(obj.objects)) {
          return fail("objects must be an array.", path + ".objects");
        }
        for (var i = 0; i < obj.objects.length; i++) {
          var ro = scanFabricObject(
            obj.objects[i],
            path + ".objects[" + i + "]",
            depth + 1
          );
          if (!ro.ok) return ro;
        }
      }
      if (obj.clipPath != null) {
        var rc = scanFabricObject(obj.clipPath, path + ".clipPath", depth + 1);
        if (!rc.ok) return rc;
      }
      // Text-on-path: typed Path nested under "path". Geometry arrays on Path stay unscanned here.
      var nestedPath = obj.path;
      if (nestedPath && typeof nestedPath === "object" && !Array.isArray(nestedPath)) {
        if (typeKey(nestedPath) !== "path") {
          return fail(
            "Unsupported nested path object (“" +
              String(nestedPath.type || "unknown") +
              "”).",
            path + ".path.type"
          );
        }
        if (nestedPath.objects != null) {
          return fail(
            "Nested path objects cannot contain objects.",
            path + ".path.objects"
          );
        }
        var rp = scanFabricObject(nestedPath, path + ".path", depth + 1);
        if (!rp.ok) return rp;
      }
      return scanUrlKeys(obj, path, depth);
    }

    function scanCanvasRoot(canvas, path, depth) {
      if (depth > MAX_DEPTH) return fail("Exceeded maximum nesting depth.", path);
      if (!canvas || typeof canvas !== "object" || Array.isArray(canvas)) {
        return fail("Invalid canvas payload.", path);
      }
      if (canvas.backgroundImage != null) {
        return fail("backgroundImage is not allowed.", path + ".backgroundImage");
      }
      if (canvas.overlayImage != null) {
        return fail("overlayImage is not allowed.", path + ".overlayImage");
      }
      if (canvas.objects != null) {
        if (!Array.isArray(canvas.objects)) {
          return fail("canvas.objects must be an array.", path + ".objects");
        }
        for (var i = 0; i < canvas.objects.length; i++) {
          var ro = scanFabricObject(
            canvas.objects[i],
            path + ".objects[" + i + "]",
            depth + 1
          );
          if (!ro.ok) return ro;
        }
      }
      return scanUrlKeys(canvas, path, depth);
    }

    if (!envelopeOrCanvas || typeof envelopeOrCanvas !== "object") {
      return fail("Invalid payload.", "");
    }

    // Blytz envelope (schema_version 1 or has canvas key).
    if (
      Object.prototype.hasOwnProperty.call(envelopeOrCanvas, "schema_version") ||
      Object.prototype.hasOwnProperty.call(envelopeOrCanvas, "canvas")
    ) {
      if (envelopeOrCanvas.canvas != null) {
        var rCanvas = scanCanvasRoot(envelopeOrCanvas.canvas, "canvas", 0);
        if (!rCanvas.ok) return rCanvas;
      }
      if (envelopeOrCanvas.views != null) {
        var views = envelopeOrCanvas.views;
        if (typeof views !== "object" || Array.isArray(views)) {
          return fail("Invalid views object.", "views");
        }
        var vkeys = Object.keys(views);
        for (var vi = 0; vi < vkeys.length; vi++) {
          var vk = vkeys[vi];
          if (vk === "front") {
            return fail("views.front is not allowed.", "views.front");
          }
          if (vk !== "back") {
            return fail("Unknown views key.", "views." + vk);
          }
          var back = views.back;
          if (!back || typeof back !== "object" || Array.isArray(back)) {
            return fail("Invalid views.back payload.", "views.back");
          }
          if (!Array.isArray(back.objects)) {
            return fail("views.back.objects must be an array.", "views.back.objects");
          }
          var rb = scanCanvasRoot(back, "views.back", 0);
          if (!rb.ok) return rb;
        }
      }
      return ok();
    }

    // Raw Fabric canvas object.
    return scanCanvasRoot(envelopeOrCanvas, "canvas", 0);
  }

  function buildEnvelopeFromCanvas() {
    // B1: canvas is ALWAYS front; views.back always present.
    var frontPayload;
    var backPayload;
    if (!fabricCanvas) {
      frontPayload = emptyFabricCanvasObject();
      backPayload = viewStore.back
        ? cloneFabricPayload(viewStore.back)
        : emptyFabricCanvasObject();
    } else if (activeView === "front") {
      frontPayload = snapshotLiveCanvas();
      backPayload = viewStore.back
        ? cloneFabricPayload(viewStore.back)
        : emptyFabricCanvasObject();
    } else {
      frontPayload = viewStore.front
        ? cloneFabricPayload(viewStore.front)
        : emptyFabricCanvasObject();
      backPayload = snapshotLiveCanvas();
    }
    return {
      schema_version: SCHEMA_VERSION,
      width: LOGICAL_SIZE,
      height: LOGICAL_SIZE,
      canvas: frontPayload,
      views: { back: backPayload },
    };
  }

  function getActiveCanvasJSON() {
    var live = fabricCanvas ? snapshotLiveCanvas() : emptyFabricCanvasObject();
    return {
      schema_version: SCHEMA_VERSION,
      width: LOGICAL_SIZE,
      height: LOGICAL_SIZE,
      canvas: live,
    };
  }

  function getActiveView() {
    return activeView;
  }

  /**
   * Stage O.1: write the inactive view's Fabric payload into viewStore
   * (does not switch the live view). Used when AI dual-side commits the other side.
   */
  function setStoredViewPayload(viewId, fabricPayload) {
    if (viewId !== "front" && viewId !== "back") {
      return { ok: false, reason: "Unknown view." };
    }
    if (viewId === activeView) {
      return { ok: false, reason: "Refuse to overwrite the live view via store." };
    }
    var payload =
      fabricPayload && typeof fabricPayload === "object"
        ? cloneFabricPayload(fabricPayload)
        : emptyFabricCanvasObject();
    if (viewId === "front") {
      viewStore.front = payload;
    } else {
      viewStore.back = payload;
    }
    return { ok: true };
  }

  function onViewChange(cb) {
    if (typeof cb === "function") viewChangeListeners.push(cb);
    return function unsubscribe() {
      var idx = viewChangeListeners.indexOf(cb);
      if (idx >= 0) viewChangeListeners.splice(idx, 1);
    };
  }

  function fireViewChange() {
    var id = activeView;
    viewChangeListeners.slice().forEach(function (cb) {
      try {
        cb(id);
      } catch (err) {
        console.error(err);
      }
    });
  }

  /**
   * Replace ALL views from a saved envelope (page load / restore).
   * Envelope canvas is always FRONT; views.back is BACK.
   * preferredView ("front"|"back") selects which side is live after load.
   * Page load omits preferredView → front. Undo/redo may restore Back.
   */
  function loadAllViewsFromEnvelope(envelope, getJSON, preferredView) {
    if (getJSON) getJSONRef = getJSON;
    var front =
      envelope && envelope.canvas
        ? cloneFabricPayload(envelope.canvas)
        : emptyFabricCanvasObject();
    var back =
      envelope &&
      envelope.views &&
      envelope.views.back &&
      typeof envelope.views.back === "object"
        ? cloneFabricPayload(envelope.views.back)
        : emptyFabricCanvasObject();
    var target = preferredView === "back" ? "back" : "front";
    var livePayload = target === "back" ? back : front;
    viewStore =
      target === "back" ? { front: front } : { back: back };
    activeView = target;
    return loadFabricPayload(livePayload, getJSONRef).then(function () {
      forceTransparentBackground();
      refreshGarmentLayer();
      fireViewChange();
    });
  }

  function setActiveView(id) {
    if (id !== "front" && id !== "back") {
      return Promise.resolve({ ok: false, reason: "Unknown view." });
    }
    if (id === activeView) {
      return Promise.resolve({ ok: true, reason: "same" });
    }
    if (!fabricCanvas) {
      return Promise.resolve({ ok: false, reason: "Canvas is not ready." });
    }
    // Discard in-progress curve preview so live snapshot is never a leaked preview.
    if (
      global.BlytzEditorProps &&
      typeof global.BlytzEditorProps.discardCurvePreview === "function"
    ) {
      global.BlytzEditorProps.discardCurvePreview();
    }
    if (suppressCommit) {
      return Promise.resolve({ ok: false, reason: "Canvas is loading." });
    }
    if (
      VIEW_SWITCH_DURING_AI_PREVIEW === "blocked" &&
      aiCandidatesPending()
    ) {
      return Promise.resolve({
        ok: false,
        reason: "Choose an AI suggestion or edit the design first",
      });
    }

    var prevView = activeView;
    // Snapshot inactive store for restore (only the inactive key is populated).
    var savedInactive =
      prevView === "front"
        ? { back: viewStore.back ? cloneFabricPayload(viewStore.back) : emptyFabricCanvasObject() }
        : { front: viewStore.front ? cloneFabricPayload(viewStore.front) : emptyFabricCanvasObject() };

    var active = fabricCanvas.getActiveObject();
    if (active && active.isEditing && typeof active.exitEditing === "function") {
      active.exitEditing();
    }
    fabricCanvas.discardActiveObject();
    fabricCanvas.requestRenderAll();

    var liveSnap = snapshotLiveCanvas();
    var loadPayload;
    if (prevView === "front" && id === "back") {
      // Inactive store becomes front; load previous back (or empty).
      loadPayload = savedInactive.back || emptyFabricCanvasObject();
      viewStore = { front: liveSnap };
    } else {
      loadPayload = savedInactive.front || emptyFabricCanvasObject();
      viewStore = { back: liveSnap };
    }

    return loadFabricPayload(loadPayload, getJSONRef)
      .then(function () {
        if (lastLoadError) throw new Error(lastLoadError);
        forceTransparentBackground();
        activeView = id;
        return refreshGarmentLayer().then(function () {
          if (
            global.BlytzEditorTools &&
            typeof global.BlytzEditorTools.refreshLayers === "function"
          ) {
            global.BlytzEditorTools.refreshLayers();
          }
          if (global.BlytzEditorProps) {
            if (typeof global.BlytzEditorProps.closeSheet === "function") {
              global.BlytzEditorProps.closeSheet();
            }
            if (typeof global.BlytzEditorProps.syncFromSelection === "function") {
              global.BlytzEditorProps.syncFromSelection();
            }
          }
          var pill = document.getElementById("editor-props-pill");
          if (pill) {
            pill.hidden = true;
            pill.setAttribute("aria-expanded", "false");
          }
          fireViewChange();
          return { ok: true };
        });
      })
      .catch(function (err) {
        viewStore = savedInactive;
        activeView = prevView;
        return loadFabricPayload(liveSnap, getJSONRef)
          .catch(function () {})
          .then(function () {
            forceTransparentBackground();
            refreshGarmentLayer();
            setToolFeedback(
              "Could not switch garment view. Your previous view was restored."
            );
            return {
              ok: false,
              reason: (err && err.message) || "View switch failed.",
            };
          });
      });
  }

  function getGarmentState() {
    return { template: garmentState.template, color: garmentState.color };
  }

  function setGarmentState(next) {
    next = next || {};
    var g = global.BlytzGarments;
    var template = next.template;
    var color = next.color;
    if (template != null) {
      if (g && typeof g.normalizeGarmentId === "function") {
        template = g.normalizeGarmentId(template);
      }
      if (!g || !g.garmentById || !g.garmentById(template)) {
        return { ok: false, reason: "Unknown garment template." };
      }
    }
    if (color != null) {
      var knownColor =
        g &&
        g.GARMENT_COLORS &&
        g.GARMENT_COLORS.some(function (c) {
          return c.id === color;
        });
      if (!knownColor) {
        return { ok: false, reason: "Unknown garment color." };
      }
    }
    var changed = false;
    if (template != null && template !== garmentState.template) {
      garmentState.template = template;
      changed = true;
    }
    if (color != null && color !== garmentState.color) {
      garmentState.color = color;
      changed = true;
    }
    if (!changed) return { ok: true, reason: "same" };
    refreshGarmentLayer();
    schedulePrintOverflowCheck();
    garmentChangeListeners.slice().forEach(function (cb) {
      try {
        cb(getGarmentState());
      } catch (err) {
        console.error(err);
      }
    });
    return { ok: true };
  }

  function onGarmentChange(cb) {
    if (typeof cb === "function") garmentChangeListeners.push(cb);
    return function unsubscribe() {
      var idx = garmentChangeListeners.indexOf(cb);
      if (idx >= 0) garmentChangeListeners.splice(idx, 1);
    };
  }

  function initGarmentFromPage() {
    var page = document.querySelector("[data-editor-page]");
    if (!page) return;
    var g = global.BlytzGarments;
    var t = page.getAttribute("data-garment-template") || "tee";
    var c = page.getAttribute("data-garment-color") || "white";
    // Aliases + unknown legacy values → canonical / tee (editor only until save).
    if (g && typeof g.normalizeGarmentId === "function") {
      t = g.normalizeGarmentId(t);
    }
    if (!g || !g.garmentById || !g.garmentById(t)) t = "tee";
    if (g && g.colorById) {
      var col = g.colorById(c);
      var known =
        g.GARMENT_COLORS &&
        g.GARMENT_COLORS.some(function (x) {
          return x.id === c;
        });
      if (!known && String(c).charAt(0) !== "#") c = "white";
      else if (col && col.id) c = col.id === "grey" ? "gray" : col.id;
    } else {
      c = "white";
    }
    garmentState = { template: t, color: c };
    refreshGarmentLayer();
  }

  function sanitizeCanvasDom() {
    if (!fabricCanvas) return;
    var lower = fabricCanvas.lowerCanvasEl;
    var upper = fabricCanvas.upperCanvasEl;
    [lower, upper].forEach(function (el) {
      if (!el) return;
      el.classList.remove(
        "bg-canvas",
        "border",
        "border-border",
        "shadow-sm",
        "rounded-md",
        "max-w-full",
        "block"
      );
      el.style.backgroundColor = "transparent";
    });
    if (lower) {
      lower.style.position = "absolute";
      lower.style.left = "0px";
      lower.style.top = "0px";
    }
  }

  /**
   * Size the displayed artboard from a height-locked workspace (#editor-root),
   * not from #editor-canvas-host (which previously grew with AI panel content).
   * Logical canvas remains LOGICAL_SIZE; object bounds never drive this value.
   */
  function availableDisplaySize() {
    var root = document.getElementById("editor-root");
    var host = document.getElementById("editor-canvas-host");
    var box = root || host;
    var availW = box ? box.clientWidth : window.innerWidth - 32;
    var availH = box ? box.clientHeight : window.innerHeight - 160;

    // Prefer host padding when measuring inside the canvas column.
    var padTarget = host || box;
    if (padTarget && typeof global.getComputedStyle === "function") {
      var cs = global.getComputedStyle(padTarget);
      availW -=
        (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
      availH -=
        (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
    }
    // Caption under the wrap consumes vertical space inside the host.
    if (host && host.querySelector(":scope > p")) {
      availH = Math.max(180, availH - 40);
    }
    // Cap by root height so AI-driven page growth cannot enlarge the artboard.
    if (root && root.clientHeight > 0) {
      availH = Math.min(availH, root.clientHeight - 48);
    }
    var side = Math.min(availW, availH, LOGICAL_SIZE);
    return Math.max(220, Math.floor(side));
  }

  /** Clamp viewport zoom (mirrors canvas_zoom.clamp_zoom). */
  function clampZoom(value) {
    var z = Number(value);
    if (!isFinite(z)) z = 1;
    return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
  }

  /** Multiplicative ± step (mirrors canvas_zoom.next_zoom_step). */
  function nextZoomStep(current, direction) {
    var z = clampZoom(current);
    if (direction > 0) return clampZoom(z * ZOOM_STEP_FACTOR);
    if (direction < 0) return clampZoom(z / ZOOM_STEP_FACTOR);
    return z;
  }

  /**
   * Ensure #editor-artboard-scene exists and holds Fabric + garments.
   * Print-overflow warning stays a sibling of the scene inside the wrap.
   */
  function ensureArtboardScene() {
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return null;
    var scene = document.getElementById("editor-artboard-scene");
    var warning = document.getElementById("editor-print-overflow-warning");
    if (!scene) {
      scene = document.createElement("div");
      scene.id = "editor-artboard-scene";
      scene.className = "editor-artboard-scene";
      wrap.insertBefore(scene, warning || wrap.firstChild);
    }
    // Move stray Fabric wrapper / canvas into the scene (not the warning).
    if (fabricCanvas && fabricCanvas.wrapperEl) {
      var wrapper = fabricCanvas.wrapperEl;
      if (wrapper.parentNode !== scene) {
        scene.appendChild(wrapper);
      }
    } else {
      var canvasEl = document.getElementById("blytz-fabric-canvas");
      if (canvasEl && canvasEl.parentNode !== scene) {
        scene.appendChild(canvasEl);
      }
    }
    ["editor-garment-layer", "editor-garment-overlay"].forEach(function (id) {
      var layer = document.getElementById(id);
      if (layer && layer.parentNode !== scene) {
        if (id === "editor-garment-layer") {
          scene.insertBefore(layer, scene.firstChild);
        } else {
          scene.appendChild(layer);
        }
      }
    });
    if (scene.parentNode !== wrap) {
      wrap.insertBefore(scene, warning || null);
    }
    // Keep overlay above Fabric after moves.
    var over = document.getElementById("editor-garment-overlay");
    if (over && over.parentNode === scene) {
      scene.appendChild(over);
    }
    return scene;
  }

  function ensureFabricViewportIdentity() {
    if (!fabricCanvas) return;
    if (typeof fabricCanvas.setViewportTransform === "function") {
      var vpt = fabricCanvas.viewportTransform;
      if (
        !vpt ||
        vpt[0] !== 1 ||
        vpt[1] !== 0 ||
        vpt[2] !== 0 ||
        vpt[3] !== 1 ||
        vpt[4] !== 0 ||
        vpt[5] !== 0
      ) {
        fabricCanvas.setViewportTransform([1, 0, 0, 1, 0, 0]);
      }
    } else if (typeof fabricCanvas.setZoom === "function") {
      fabricCanvas.setZoom(1);
    }
  }

  /** Apply CSS scene transform (garment + Fabric). Not a commitEdit. */
  function applySceneTransform() {
    var scene = ensureArtboardScene();
    if (!scene) return;
    ensureFabricViewportIdentity();
    scene.style.transformOrigin = "0 0";
    scene.style.transform =
      "translate(" +
      scenePanX +
      "px, " +
      scenePanY +
      "px) scale(" +
      sceneZoom +
      ")";
    if (fabricCanvas) fabricCanvas.requestRenderAll();
    notifyZoomUi();
  }

  /**
   * Zoom about wrap-local point (mirrors canvas_zoom.scene_zoom_to_point).
   * wrap_xy = scale * scene_xy + pan
   */
  function sceneZoomToPoint(nextZoom, pointX, pointY) {
    var s0 = sceneZoom > 0 ? sceneZoom : 1;
    var s1 = clampZoom(nextZoom);
    var sx = (pointX - scenePanX) / s0;
    var sy = (pointY - scenePanY) / s0;
    sceneZoom = s1;
    scenePanX = pointX - s1 * sx;
    scenePanY = pointY - s1 * sy;
    applySceneTransform();
  }

  function getZoom() {
    return clampZoom(sceneZoom);
  }

  /**
   * Legacy no-op name kept for garment refresh hooks.
   * Garments live inside #editor-artboard-scene so they co-scale automatically.
   */
  function syncGarmentViewport() {
    ensureArtboardScene();
    ensureFabricViewportIdentity();
  }

  function notifyZoomUi() {
    var z = getZoom();
    var label = Math.round(z * 100) + "%";
    var atMin = z <= ZOOM_MIN + 1e-6;
    var atMax = z >= ZOOM_MAX - 1e-6;
    var pctBtn = document.querySelector("[data-editor-zoom-reset]");
    if (pctBtn) pctBtn.textContent = label;
    document.querySelectorAll("[data-editor-zoom-out]").forEach(function (btn) {
      btn.disabled = atMin;
    });
    document.querySelectorAll("[data-editor-zoom-in]").forEach(function (btn) {
      btn.disabled = atMax;
    });
    zoomUiListeners.slice().forEach(function (cb) {
      try {
        cb(z);
      } catch (err) {
        console.error(err);
      }
    });
  }

  function onZoomChange(cb) {
    if (typeof cb === "function") zoomUiListeners.push(cb);
    return function unsubscribe() {
      var idx = zoomUiListeners.indexOf(cb);
      if (idx >= 0) zoomUiListeners.splice(idx, 1);
    };
  }

  function wrapLocalPointFromClient(clientX, clientY) {
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return { x: 0, y: 0 };
    var rect = wrap.getBoundingClientRect();
    var cs =
      typeof global.getComputedStyle === "function"
        ? global.getComputedStyle(wrap)
        : null;
    var bl = cs ? parseFloat(cs.borderLeftWidth) || 0 : 0;
    var bt = cs ? parseFloat(cs.borderTopWidth) || 0 : 0;
    return {
      x: clientX - rect.left - bl,
      y: clientY - rect.top - bt,
    };
  }

  function wrapCenterPoint() {
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) {
      return { x: LOGICAL_SIZE / 2, y: LOGICAL_SIZE / 2 };
    }
    return {
      x: (wrap.clientWidth || 0) / 2,
      y: (wrap.clientHeight || 0) / 2,
    };
  }

  /**
   * Viewport-only zoom via scene CSS. Does not commitEdit / change object coords.
   * @param {number} nextZoom
   * @param {{x:number,y:number}|null|undefined} point — wrap-local CSS px; default center
   */
  function setZoomLevel(nextZoom, point) {
    ensureArtboardScene();
    var pt = point && isFinite(point.x) && isFinite(point.y) ? point : wrapCenterPoint();
    sceneZoomToPoint(nextZoom, pt.x, pt.y);
    return true;
  }

  function zoomBy(factor, point) {
    var f = Number(factor);
    if (!isFinite(f) || f <= 0) return false;
    return setZoomLevel(getZoom() * f, point);
  }

  /** Reset scene to 100% / identity pan. Not a history step. */
  function resetZoom() {
    sceneZoom = 1;
    scenePanX = 0;
    scenePanY = 0;
    applySceneTransform();
    return true;
  }

  function panSceneBy(dx, dy) {
    scenePanX += dx;
    scenePanY += dy;
    applySceneTransform();
  }

  function applyResponsiveSize() {
    if (!fabricCanvas) return;
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return;
    var css = availableDisplaySize();
    // Skip no-op updates to avoid ResizeObserver feedback loops.
    if (css === lastAppliedDisplaySize && wrap.style.width === css + "px") {
      return;
    }
    lastAppliedDisplaySize = css;
    // Logical coordinates stay 800×800. CSS size is display-only; never rewrite object coords.
    // Policy: reset scene zoom on CSS resize. Front/Back does not call this — zoom preserved.
    ensureArtboardScene();
    ensureFabricViewportIdentity();
    sceneZoom = 1;
    scenePanX = 0;
    scenePanY = 0;
    fabricCanvas.setDimensions(
      { width: LOGICAL_SIZE, height: LOGICAL_SIZE },
      { backstoreOnly: true }
    );
    // content-box: wrap content == Fabric CSS size; border sits outside so pointer maps stay aligned.
    wrap.style.boxSizing = "content-box";
    wrap.style.width = css + "px";
    wrap.style.height = css + "px";
    fabricCanvas.setDimensions({ width: css, height: css }, { cssOnly: true });
    sanitizeCanvasDom();
    applySceneTransform();
    fabricCanvas.requestRenderAll();
  }

  function scheduleResponsiveSize() {
    if (resizeApplyScheduled) return;
    resizeApplyScheduled = true;
    var run = function () {
      resizeApplyScheduled = false;
      applyResponsiveSize();
    };
    if (typeof global.requestAnimationFrame === "function") {
      global.requestAnimationFrame(run);
    } else {
      global.setTimeout(run, 0);
    }
  }

  function applyTouchFriendlyHandles() {
    if (touchHandlesApplied) return;
    var fabric = fabricNS();
    if (!fabric || !fabric.FabricObject || !fabric.FabricObject.ownDefaults) return;
    var coarse =
      typeof global.matchMedia === "function" &&
      global.matchMedia("(pointer: coarse)").matches;
    if (!coarse) return;
    touchHandlesApplied = true;
    fabric.FabricObject.ownDefaults.cornerSize = 16;
    fabric.FabricObject.ownDefaults.touchCornerSize = 36;
    fabric.FabricObject.ownDefaults.cornerStyle = "circle";
  }

  function prefersSheetTextEdit() {
    return (
      typeof global.matchMedia === "function" &&
      (global.matchMedia("(max-width: 767px)").matches ||
        global.matchMedia("(pointer: coarse)").matches)
    );
  }

  function wireCanvasGestures() {
    if (gesturesWired) return;
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return;
    gesturesWired = true;
    wrap.style.touchAction = "none";

    function pointerCount() {
      return gesturePointers.size;
    }

    function centerOfPointers() {
      var sx = 0;
      var sy = 0;
      var n = 0;
      gesturePointers.forEach(function (p) {
        sx += p.x;
        sy += p.y;
        n += 1;
      });
      if (!n) return null;
      return { x: sx / n, y: sy / n };
    }

    function distOfPointers() {
      if (gesturePointers.size < 2) return 0;
      var pts = [];
      gesturePointers.forEach(function (p) {
        pts.push(p);
      });
      var dx = pts[0].x - pts[1].x;
      var dy = pts[0].y - pts[1].y;
      return Math.sqrt(dx * dx + dy * dy) || 1;
    }

    wrap.addEventListener(
      "pointerdown",
      function (e) {
        if (!fabricCanvas) return;
        gesturePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pointerCount() >= 2) {
          gestureActive = true;
          gestureLastDist = distOfPointers();
          gestureLastCenter = centerOfPointers();
          fabricCanvas.selection = false;
          fabricCanvas.discardActiveObject();
          fabricCanvas.requestRenderAll();
          try {
            wrap.setPointerCapture(e.pointerId);
          } catch (err) {
            /* ignore */
          }
        }
      },
      { passive: true }
    );

    wrap.addEventListener(
      "pointermove",
      function (e) {
        if (!gesturePointers.has(e.pointerId)) return;
        gesturePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (!gestureActive || pointerCount() < 2 || !fabricCanvas) return;
        e.preventDefault();
        var dist = distOfPointers();
        var center = centerOfPointers();
        if (!center || !gestureLastDist) {
          gestureLastDist = dist;
          gestureLastCenter = center;
          return;
        }
        var factor = dist / gestureLastDist;
        var local = wrapLocalPointFromClient(center.x, center.y);
        setZoomLevel(getZoom() * factor, local);
        if (gestureLastCenter) {
          panSceneBy(
            center.x - gestureLastCenter.x,
            center.y - gestureLastCenter.y
          );
        }
        gestureLastDist = dist;
        gestureLastCenter = center;
      },
      { passive: false }
    );

    function endPointer(e) {
      gesturePointers.delete(e.pointerId);
      if (pointerCount() < 2) {
        gestureActive = false;
        gestureLastDist = 0;
        gestureLastCenter = null;
        if (fabricCanvas) {
          fabricCanvas.selection = true;
        }
      }
    }
    wrap.addEventListener("pointerup", endPointer);
    wrap.addEventListener("pointercancel", endPointer);
    wrap.addEventListener("pointerleave", endPointer);

    // Ctrl/Cmd + wheel: zoom toward pointer (desktop). Only while over the wrap.
    wrap.addEventListener(
      "wheel",
      function (e) {
        if (!fabricCanvas) return;
        if (!(e.ctrlKey || e.metaKey)) return;
        e.preventDefault();
        var pt = wrapLocalPointFromClient(e.clientX, e.clientY);
        var direction = e.deltaY < 0 ? 1 : -1;
        setZoomLevel(nextZoomStep(getZoom(), direction), pt);
      },
      { passive: false }
    );
  }

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function canScenePan() {
    return getZoom() > 1.001;
  }

  function syncScenePanCursor() {
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return;
    wrap.classList.toggle("is-scene-pan-ready", !!spacePanHeld && canScenePan());
    wrap.classList.toggle("is-scene-panning", !!(scenePanDrag && scenePanDrag.active));
  }

  function endScenePanDrag() {
    if (!scenePanDrag) return;
    scenePanDrag = null;
    if (fabricCanvas) {
      fabricCanvas.selection = true;
      fabricCanvas.skipTargetFind = false;
    }
    syncScenePanCursor();
  }

  /**
   * Desktop pan when zoomed: Space+drag or middle-mouse drag on the wrap.
   * Calls panSceneBy only — Fabric VPT stays identity; not a commitEdit.
   */
  function wireScenePan() {
    if (scenePanWired) return;
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return;
    scenePanWired = true;

    document.addEventListener("keydown", function (e) {
      if (e.code !== "Space" && e.key !== " ") return;
      if (e.repeat) return;
      if (isTypingTarget(e.target)) return;
      var root = document.getElementById("editor-root");
      if (root && e.target && e.target !== document.body && !root.contains(e.target)) {
        return;
      }
      spacePanHeld = true;
      // Avoid page scroll while using Space as a pan modifier in the editor.
      if (canScenePan()) e.preventDefault();
      syncScenePanCursor();
    });

    document.addEventListener("keyup", function (e) {
      if (e.code !== "Space" && e.key !== " ") return;
      spacePanHeld = false;
      if (scenePanDrag && scenePanDrag.via === "space") {
        endScenePanDrag();
      } else {
        syncScenePanCursor();
      }
    });

    window.addEventListener("blur", function () {
      spacePanHeld = false;
      endScenePanDrag();
    });

    // Capture so Fabric does not start a selection/move while panning.
    wrap.addEventListener(
      "pointerdown",
      function (e) {
        if (!fabricCanvas) return;
        if (gestureActive || gesturePointers.size >= 2) return;
        var middle = e.button === 1;
        var space = spacePanHeld && (e.button === 0 || e.button == null);
        if (!middle && !space) return;
        if (!canScenePan()) return;
        e.preventDefault();
        e.stopPropagation();
        scenePanDrag = {
          active: true,
          via: middle ? "middle" : "space",
          pointerId: e.pointerId,
          lastX: e.clientX,
          lastY: e.clientY,
        };
        fabricCanvas.selection = false;
        fabricCanvas.skipTargetFind = true;
        fabricCanvas.discardActiveObject();
        fabricCanvas.requestRenderAll();
        try {
          wrap.setPointerCapture(e.pointerId);
        } catch (err) {
          /* ignore */
        }
        syncScenePanCursor();
      },
      true
    );

    wrap.addEventListener(
      "pointermove",
      function (e) {
        if (!scenePanDrag || !scenePanDrag.active) return;
        if (e.pointerId !== scenePanDrag.pointerId) return;
        e.preventDefault();
        e.stopPropagation();
        var dx = e.clientX - scenePanDrag.lastX;
        var dy = e.clientY - scenePanDrag.lastY;
        scenePanDrag.lastX = e.clientX;
        scenePanDrag.lastY = e.clientY;
        if (dx || dy) panSceneBy(dx, dy);
      },
      true
    );

    function endPanPointer(e) {
      if (!scenePanDrag || !scenePanDrag.active) return;
      if (e.pointerId != null && e.pointerId !== scenePanDrag.pointerId) return;
      endScenePanDrag();
    }
    wrap.addEventListener("pointerup", endPanPointer, true);
    wrap.addEventListener("pointercancel", endPanPointer, true);

    // Middle-click often opens autoscroll — block it on the artboard.
    wrap.addEventListener("auxclick", function (e) {
      if (e.button === 1) e.preventDefault();
    });
  }

  /** Wire − / % / + chrome + optional Ctrl/Cmd+= − 0 when focus is in the editor. */
  function wireZoomChrome() {
    if (zoomChromeWired) return;
    zoomChromeWired = true;
    document.addEventListener("click", function (e) {
      var out = e.target.closest("[data-editor-zoom-out]");
      var inn = e.target.closest("[data-editor-zoom-in]");
      var reset = e.target.closest("[data-editor-zoom-reset]");
      if (!out && !inn && !reset) return;
      e.preventDefault();
      if (out && !out.disabled) {
        setZoomLevel(nextZoomStep(getZoom(), -1));
      } else if (inn && !inn.disabled) {
        setZoomLevel(nextZoomStep(getZoom(), 1));
      } else if (reset) {
        resetZoom();
      }
    });
    document.addEventListener("keydown", function (e) {
      if (!(e.ctrlKey || e.metaKey)) return;
      var root = document.getElementById("editor-root");
      if (!root) return;
      var t = e.target;
      var tag = (t && t.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (t && t.isContentEditable) return;
      // Only intercept when focus is inside the editor shell (avoid fighting browser zoom elsewhere).
      if (t !== document.body && t !== document.documentElement && !root.contains(t)) {
        return;
      }
      var key = e.key;
      if (key === "=" || key === "+") {
        e.preventDefault();
        setZoomLevel(nextZoomStep(getZoom(), 1));
      } else if (key === "-" || key === "_") {
        e.preventDefault();
        setZoomLevel(nextZoomStep(getZoom(), -1));
      } else if (key === "0") {
        e.preventDefault();
        resetZoom();
      }
    });
    notifyZoomUi();
  }

  function syncMultiSelectUi() {
    document.querySelectorAll("[data-editor-action='multi-select']").forEach(function (btn) {
      btn.setAttribute("aria-pressed", multiSelectMode ? "true" : "false");
      btn.classList.toggle("is-active", multiSelectMode);
    });
    document.querySelectorAll("[data-editor-action='select']").forEach(function (btn) {
      btn.setAttribute("aria-pressed", multiSelectMode ? "false" : "true");
      btn.classList.toggle("is-active", !multiSelectMode);
    });
  }

  function setMultiSelectMode(on) {
    multiSelectMode = !!on;
    if (fabricCanvas) {
      // Touch multi-select workaround verified against Fabric 6.6.1 only.
      // Public Fabric 6 API: selectionKey may be a key name or array of key names.
      // When multi-select mode is on, pointer events get e.blytzMultiSelect = true
      // so taps toggle membership like Shift+click.
      fabricCanvas.selectionKey = multiSelectMode
        ? ["shiftKey", "blytzMultiSelect"]
        : "shiftKey";
    }
    syncMultiSelectUi();
    setToolFeedback(
      multiSelectMode
        ? "Multi-select on — tap objects to add or remove."
        : "Select tool"
    );
  }

  function wireMultiSelectPointer() {
    if (multiSelectPointerWired) return;
    multiSelectPointerWired = true;
    var mark = function (e) {
      if (multiSelectMode) {
        try {
          e.blytzMultiSelect = true;
        } catch (err) {
          /* ignore */
        }
      }
    };
    // Capture on wrap so Fabric's handlers see the flag.
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return;
    ["pointerdown", "mousedown", "touchstart"].forEach(function (type) {
      wrap.addEventListener(type, mark, true);
    });
  }

  function wireContextMenuSuppression() {
    if (contextMenuWired) return;
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return;
    contextMenuWired = true;
    // Casual-copy deterrent only (not DRM): block browser context menu and
    // native image drag on the artboard wrapper. No custom menu yet.
    wrap.addEventListener("contextmenu", function (e) {
      e.preventDefault();
    });
    wrap.addEventListener("dragstart", function (e) {
      e.preventDefault();
    });
  }

  function bindCanvasEvents(getJSON) {
    if (!fabricCanvas || eventsBound) return;
    eventsBound = true;
    getJSONRef = getJSON;

    // Native drag / scale / rotate: one object:modified per gesture → one commit.
    fabricCanvas.on("object:modified", function () {
      if (Date.now() < suppressModifiedUntil) return;
      notifyCommitted(getJSON, "object:modified");
    });

    // Commit on editing exit only when the string actually changed.
    fabricCanvas.on("text:editing:entered", function (opt) {
      var t = opt && opt.target;
      textAtEditStart = t && typeof t.text === "string" ? t.text : null;
      textEditDirty = false;
    });
    fabricCanvas.on("text:changed", function () {
      textEditDirty = true;
    });
    fabricCanvas.on("text:editing:exited", function (opt) {
      var t = opt && opt.target;
      var start = textAtEditStart;
      textAtEditStart = null;
      var changed =
        !!t &&
        typeof t.text === "string" &&
        start !== null &&
        t.text !== start;
      textEditDirty = false;
      if (!changed) return;
      // Fabric often also fires object:modified after exit — suppress briefly.
      suppressModifiedUntil = Date.now() + 200;
      notifyCommitted(getJSON, "text:editing:exited");
    });

    // Selection changes must never commit.
    // object:added / object:removed intentionally do not notify; mutations go
    // through commitEdit (or loadFabricPayload with suppressCommit).
  }

  function ensureCanvas(getJSON) {
    if (getJSON) getJSONRef = getJSON;
    if (fabricCanvas) return fabricCanvas;
    var fabric = fabricNS();
    if (!fabric || !fabric.Canvas) {
      console.error("Fabric.js is not loaded");
      return null;
    }
    var el = document.getElementById("blytz-fabric-canvas");
    if (!el) {
      console.error("Missing #blytz-fabric-canvas");
      return null;
    }
    applyTouchFriendlyHandles();
    ensureArtboardScene();
    fabricCanvas = new fabric.Canvas(el, {
      preserveObjectStacking: true,
      selection: true,
      backgroundColor: "",
      selectionKey: "shiftKey",
      allowTouchScrolling: false,
    });
    ensureArtboardScene();
    ensureFabricViewportIdentity();
    fabricCanvas.setDimensions({ width: LOGICAL_SIZE, height: LOGICAL_SIZE });
    sanitizeCanvasDom();
    forceTransparentBackground();
    bindCanvasEvents(getJSONRef);
    wirePrintOverflowChecks();
    applyResponsiveSize();
    wireMultiSelectPointer();
    wireContextMenuSuppression();
    wireCanvasGestures();
    wireScenePan();
    wireZoomChrome();
    syncMultiSelectUi();
    initGarmentFromPage();
    applySceneTransform();
    if (typeof ResizeObserver !== "undefined" && !resizeObserver) {
      // Observe the height-locked workspace root, not the wrap (avoids feedback).
      var workspace = document.getElementById("editor-root");
      if (workspace) {
        resizeObserver = new ResizeObserver(function () {
          scheduleResponsiveSize();
        });
        resizeObserver.observe(workspace);
      }
    }
    global.addEventListener("resize", scheduleResponsiveSize);
    global.addEventListener("orientationchange", function () {
      // Keep selection + unsaved edits; only reflow display size.
      scheduleResponsiveSize();
      applyTouchFriendlyHandles();
    });
    var root = document.getElementById("editor-root");
    if (root) root.dataset.loaded = "1";
    return fabricCanvas;
  }

  function loadFabricPayload(payload, getJSON) {
    if (getJSON) getJSONRef = getJSON;
    var canvas = ensureCanvas(getJSONRef);
    if (!canvas) {
      return Promise.reject(new Error("Canvas unavailable"));
    }
    var gen = ++loadGeneration;
    suppressCommit = true;
    lastLoadError = "";
    return canvas
      .loadFromJSON(payload || emptyFabricCanvasObject())
      .then(function () {
        if (gen !== loadGeneration) return;
        // Assign missing/duplicate blytzIds with commits suppressed (not a user edit).
        ensureBlytzIds(canvas);
        // Re-apply lock interaction so load cannot leave locked objects editable.
        applyLockStateToCanvas(canvas);
        // Old designs may serialize background "#ffffff"; force transparent so garment shows.
        forceTransparentBackground();
        applyResponsiveSize();
        canvas.discardActiveObject();
        canvas.requestRenderAll();
      })
      .catch(function (err) {
        console.error("Failed to load canvas JSON", err);
        lastLoadError =
          "Could not load this design onto the canvas. Saving is blocked so the original is not overwritten. Reload or go back.";
        canvas.clear();
        forceTransparentBackground();
        canvas.requestRenderAll();
        throw err;
      })
      .finally(function () {
        if (gen === loadGeneration) {
          suppressCommit = false;
          schedulePrintOverflowCheck();
        }
      });
  }

  function persistAllowed() {
    var editor = global.BlytzEditor;
    return !!(editor && typeof editor.canPersist === "function" && editor.canPersist());
  }

  /**
   * Insert text. On phones / coarse pointers, skip Fabric enterEditing so the
   * on-screen keyboard does not cover the canvas — text is edited in the Text sheet.
   * @param {Function} getJSON
   * @param {{text?: string, skipEditing?: boolean}|undefined} opts
   */
  function addText(getJSON, opts) {
    opts = opts || {};
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return;
    }
    var fabric = fabricNS();
    var canvas = ensureCanvas(getJSON);
    if (!canvas || !fabric) return;
    var entered = false;
    var skipEditing =
      opts.skipEditing === true ||
      (opts.skipEditing !== false && prefersSheetTextEdit());
    var initialText =
      typeof opts.text === "string" && opts.text.length ? opts.text : "Your text";
    commitEdit(
      "add-text",
      function () {
        var text = new fabric.IText(initialText, {
          fontSize: 48,
          fill: defaultContrastFill(),
          fontFamily: ALLOWED_FONTS[0],
          originX: "left",
          originY: "top",
        });
        assignBlytzId(text);
        assignBlytzName(text, "Text");
        canvas.add(text);
        if (typeof text.initDimensions === "function") text.initDimensions();
        text.setCoords();
        var w = text.getScaledWidth();
        var h = text.getScaledHeight();
        // Visually center using left/top origin (same origin family as AI mocks).
        text.set({
          left: LOGICAL_SIZE / 2 - w / 2,
          top: LOGICAL_SIZE / 2 - h / 2,
        });
        canvas.setActiveObject(text);
        canvas.requestRenderAll();
        setToolFeedback("Text added.");
        return true;
      },
      getJSON
    );
    if (skipEditing) return false;
    // Enter editing after the insert commit so typing can produce a second commit.
    var active = canvas.getActiveObject();
    if (active && typeof active.enterEditing === "function") {
      active.enterEditing();
      if (typeof active.selectAll === "function") active.selectAll();
      canvas.requestRenderAll();
      entered = true;
    }
    return entered;
  }

  function copyCurveMeta(source, cloned) {
    if (!source || !cloned || !source.blytzCurve || cloned.blytzCurve) return;
    try {
      cloned.blytzCurve = JSON.parse(JSON.stringify(source.blytzCurve));
    } catch (err) {
      cloned.blytzCurve = {
        amount: source.blytzCurve.amount,
        direction: source.blytzCurve.direction,
        version: source.blytzCurve.version,
      };
    }
  }

  function finalizeDuplicatedClone(cloned, source) {
    if (!cloned || !source) return null;
    // Clone retains the source blytzId; always mint a fresh one.
    forceBlytzId(cloned);
    cloned.blytzName = duplicateLayerName(source);
    copyCurveMeta(source, cloned);
    // Prefer a usable clone: visible + unlocked; leave the source unchanged.
    cloned.visible = true;
    cloned.blytzLocked = false;
    applyLockInteraction(cloned);
    cloned.set({
      left: (source.left || 0) + 24,
      top: (source.top || 0) + 24,
    });
    if (typeof cloned.setCoords === "function") cloned.setCoords();
    return cloned;
  }

  function duplicateActive(getJSON) {
    if (!persistAllowed()) return Promise.resolve(false);
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return Promise.resolve(false);
    var active = canvas.getActiveObject();
    if (!active) {
      setToolFeedback("Select an object to duplicate.");
      return Promise.resolve(false);
    }
    var jsonFn = getJSON || getJSONRef;
    var fabric = fabricNS();

    // Stage F: multi-selection → one commit, fresh id/name per clone.
    if (isActiveSelection(active)) {
      var sources = active.getObjects().slice();
      if (sources.length < 1) {
        setToolFeedback("Select an object to duplicate.");
        return Promise.resolve(false);
      }
      var cloneJobs = sources.map(function (src) {
        if (!src || typeof src.clone !== "function") {
          return Promise.resolve(null);
        }
        return Promise.resolve(src.clone(SERIALIZE_PROPS)).then(function (cloned) {
          return { source: src, cloned: cloned };
        });
      });
      return Promise.all(cloneJobs).then(function (pairs) {
        var ready = [];
        var i;
        for (i = 0; i < pairs.length; i++) {
          if (!pairs[i] || !pairs[i].cloned) {
            setToolFeedback("Could not duplicate selection.");
            return false;
          }
          ready.push(pairs[i]);
        }
        return commitEdit(
          "duplicate-selection",
          function () {
            var clones = [];
            for (i = 0; i < ready.length; i++) {
              var finalized = finalizeDuplicatedClone(
                ready[i].cloned,
                ready[i].source
              );
              if (!finalized) return false;
              canvas.add(finalized);
              clones.push(finalized);
            }
            if (clones.length > 1 && fabric && fabric.ActiveSelection) {
              try {
                var sel = new fabric.ActiveSelection(clones, { canvas: canvas });
                canvas.setActiveObject(sel);
              } catch (err) {
                canvas.setActiveObject(clones[0]);
              }
            } else if (clones[0]) {
              canvas.setActiveObject(clones[0]);
            }
            canvas.requestRenderAll();
            setToolFeedback("Duplicated " + clones.length + " objects.");
            return true;
          },
          jsonFn
        );
      });
    }

    var clonedResult =
      typeof active.clone === "function"
        ? active.clone(SERIALIZE_PROPS)
        : null;
    return Promise.resolve(clonedResult).then(function (cloned) {
      if (!cloned) {
        setToolFeedback("Could not duplicate.");
        return false;
      }
      return commitEdit(
        "duplicate",
        function () {
          if (!finalizeDuplicatedClone(cloned, active)) return false;
          canvas.add(cloned);
          canvas.setActiveObject(cloned);
          canvas.requestRenderAll();
          setToolFeedback("Duplicated.");
          return true;
        },
        jsonFn
      );
    });
  }

  /**
   * Discard the active selection/object without committing history or dirtying
   * the design. Safe no-op when nothing is selected.
   */
  function clearSelection() {
    var canvas = fabricCanvas;
    if (!canvas) return false;
    if (!canvas.getActiveObject()) return false;
    canvas.discardActiveObject();
    canvas.requestRenderAll();
    return true;
  }

  function deleteSelection(getJSON) {
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return;
    var active = canvas.getActiveObjects();
    if (!active || !active.length) {
      setToolFeedback("Select an object to delete.");
      return;
    }
    commitEdit(
      "delete",
      function () {
        active.forEach(function (obj) {
          canvas.remove(obj);
        });
        canvas.discardActiveObject();
        canvas.requestRenderAll();
        setToolFeedback("Deleted.");
        return true;
      },
      getJSON
    );
  }

  /**
   * UTF-8 byte length of the full persist envelope (both views once Task 12 lands).
   * Image budget / 100% probe must use this helper so size policy stays in one place.
   */
  function measureEnvelopeBytes() {
    return utf8ByteLength(JSON.stringify(buildEnvelopeFromCanvas()));
  }

  function setImagePickerBusy(busy) {
    var btn = document.querySelector("[data-panel-choose-image]");
    if (btn) {
      btn.disabled = !!busy;
      if (busy) btn.setAttribute("aria-busy", "true");
      else btn.removeAttribute("aria-busy");
    }
  }

  function fileToDataURL(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () {
        reject(new Error("read"));
      };
      reader.onload = function () {
        resolve(reader.result);
      };
      reader.readAsDataURL(file);
    });
  }

  function decodeImageFile(file) {
    // Animated WebP is flattened to its first frame (createImageBitmap / Image decode).
    if (typeof createImageBitmap === "function") {
      return createImageBitmap(file, { imageOrientation: "from-image" }).catch(
        function () {
          return decodeImageFileViaElement(file);
        }
      );
    }
    return decodeImageFileViaElement(file);
  }

  function decodeImageFileViaElement(file) {
    return fileToDataURL(file).then(function (url) {
      return new Promise(function (resolve, reject) {
        var img = new Image();
        img.onload = function () {
          resolve(img);
        };
        img.onerror = function () {
          reject(new Error("decode"));
        };
        img.src = url;
      });
    });
  }

  function canvasHasAlpha(ctx, w, h) {
    try {
      var data = ctx.getImageData(0, 0, w, h).data;
      for (var i = 3; i < data.length; i += 4) {
        if (data[i] < 255) return true;
      }
    } catch (err) {
      return true;
    }
    return false;
  }

  function blobToDataURL(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () {
        reject(new Error("read-blob"));
      };
      reader.onload = function () {
        resolve(reader.result);
      };
      reader.readAsDataURL(blob);
    });
  }

  function encodeCanvas(canvasEl, mime, quality) {
    return new Promise(function (resolve) {
      if (canvasEl.toBlob) {
        canvasEl.toBlob(
          function (blob) {
            resolve(blob || null);
          },
          mime,
          quality
        );
      } else {
        try {
          var url = canvasEl.toDataURL(mime, quality);
          var bin = atob(url.split(",")[1] || "");
          var arr = new Uint8Array(bin.length);
          for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
          resolve(new Blob([arr], { type: mime }));
        } catch (err) {
          resolve(null);
        }
      }
    });
  }

  /**
   * Downscale / re-encode pipeline. Returns {ok, dataUrl, width, height, mime, bytes, keptOriginal}.
   * @param {File} file
   * @param {*} bitmap decoded image
   * @param {{forceReencode?: boolean}|undefined} opts
   *   forceReencode: skip keptOriginal short-circuit (used when original would blow envelope budget).
   *   Never stores a second copy of the image — either original OR re-encoded src.
   */
  function processImageForInsert(file, bitmap, opts) {
    opts = opts || {};
    var forceReencode = !!opts.forceReencode;
    var srcW = bitmap.width || 0;
    var srcH = bitmap.height || 0;
    if (!(srcW > 0) || !(srcH > 0)) {
      return Promise.resolve({ ok: false, reason: "corrupt" });
    }
    if (srcW * srcH > IMAGE_MAX_PIXELS) {
      return Promise.resolve({ ok: false, reason: "pixels" });
    }
    var maxEdge = Math.max(srcW, srcH);
    if (
      !forceReencode &&
      maxEdge <= IMAGE_MAX_EDGE &&
      file.size <= IMAGE_TARGET_BYTES
    ) {
      return fileToDataURL(file).then(function (dataUrl) {
        return {
          ok: true,
          dataUrl: dataUrl,
          width: srcW,
          height: srcH,
          mime: file.type || "image/png",
          bytes: file.size,
          keptOriginal: true,
        };
      });
    }

    function drawAt(edge) {
      var scale = Math.min(1, edge / maxEdge);
      var w = Math.max(1, Math.round(srcW * scale));
      var h = Math.max(1, Math.round(srcH * scale));
      var el = document.createElement("canvas");
      el.width = w;
      el.height = h;
      var ctx = el.getContext("2d");
      ctx.drawImage(bitmap, 0, 0, w, h);
      return { el: el, w: w, h: h, hasAlpha: canvasHasAlpha(ctx, w, h) };
    }

    function tryEncode(drawn) {
      var order = [];
      // Prefer webp; fall back based on alpha if browser returns a different type.
      order.push({ mime: "image/webp", qualities: IMAGE_QUALITY_STEPS.slice() });
      if (drawn.hasAlpha) {
        order.push({ mime: "image/png", qualities: [undefined] });
      } else {
        order.push({ mime: "image/jpeg", qualities: IMAGE_QUALITY_STEPS.slice() });
      }
      var chain = Promise.resolve(null);
      order.forEach(function (entry) {
        entry.qualities.forEach(function (q) {
          chain = chain.then(function (best) {
            if (best) return best;
            return encodeCanvas(drawn.el, entry.mime, q).then(function (blob) {
              if (!blob) return null;
              var outType = blob.type || entry.mime;
              if (entry.mime === "image/webp" && outType.indexOf("webp") === -1) {
                return null;
              }
              if (blob.size <= IMAGE_TARGET_BYTES) {
                return blobToDataURL(blob).then(function (dataUrl) {
                  return {
                    ok: true,
                    dataUrl: dataUrl,
                    width: drawn.w,
                    height: drawn.h,
                    mime: outType,
                    bytes: blob.size,
                    keptOriginal: false,
                  };
                });
              }
              return null;
            });
          });
        });
      });
      return chain;
    }

    var edgeChain = Promise.resolve(null);
    IMAGE_EDGE_STEPS.forEach(function (edge) {
      edgeChain = edgeChain.then(function (best) {
        if (best) return best;
        if (edge > maxEdge && edge !== IMAGE_EDGE_STEPS[0]) {
          // Skip upsizing; still allow first step when already large.
        }
        var drawn = drawAt(Math.min(edge, maxEdge));
        return tryEncode(drawn);
      });
    });
    return edgeChain.then(function (result) {
      if (result) return result;
      return { ok: false, reason: "too-detailed" };
    });
  }

  function addImageFromFile(file, getJSON) {
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return Promise.resolve({ ok: false, reason: "not-ready" });
    }
    var fabric = fabricNS();
    var canvas = ensureCanvas(getJSON);
    if (!canvas || !fabric) {
      return Promise.resolve({ ok: false, reason: "no-canvas" });
    }
    // Cancelled file picker: silent no-op, no commit.
    if (!file) {
      return Promise.resolve({ ok: false, reason: "cancelled" });
    }
    if (!ALLOWED_IMAGE_TYPES[file.type]) {
      setToolFeedback("Image must be PNG, JPG, or WebP.");
      return Promise.resolve({ ok: false, reason: "type" });
    }
    if (file.size > IMAGE_INPUT_LIMIT_BYTES) {
      setToolFeedback(
        "Image must be " +
          Math.round(IMAGE_INPUT_LIMIT_BYTES / (1024 * 1024)) +
          " MB or smaller."
      );
      return Promise.resolve({ ok: false, reason: "size" });
    }

    setImagePickerBusy(true);
    setToolFeedback("Processing image...");

    return decodeImageFile(file)
      .catch(function () {
        return Promise.reject(new Error("decode"));
      })
      .then(function (bitmap) {
        function closeBitmap() {
          if (bitmap && typeof bitmap.close === "function") {
            try {
              bitmap.close();
            } catch (err) {
              /* ignore */
            }
          }
        }
        return processImageForInsert(file, bitmap).then(function (processed) {
          // keptOriginal embeds the full data URL. If that alone would exceed the
          // remaining soft insert budget, re-encode instead of keeping the original.
          // Never serializes original + re-encoded together.
          if (processed && processed.ok && processed.keptOriginal) {
            var current = measureEnvelopeBytes();
            var budget = Math.floor(
              MAX_CANVAS_JSON_BYTES * IMAGE_INSERT_BUDGET_RATIO
            );
            var room = Math.max(0, budget - current);
            var srcBytes = utf8ByteLength(processed.dataUrl || "");
            // Small margin for Fabric object wrapper fields around the src string.
            if (srcBytes + 2048 > room) {
              return processImageForInsert(file, bitmap, {
                forceReencode: true,
              }).then(function (reenc) {
                closeBitmap();
                return reenc;
              });
            }
          }
          closeBitmap();
          return processed;
        });
      })
      .then(function (processed) {
        if (!processed || !processed.ok) {
          if (processed && processed.reason === "pixels") {
            setToolFeedback(
              "This image is too large (too many pixels) to add. Try a smaller image."
            );
          } else if (processed && processed.reason === "too-detailed") {
            setToolFeedback(
              "This image is too detailed to add. Try a smaller image."
            );
          } else {
            setToolFeedback(
              "That image file could not be decoded. Try a different PNG, JPG, or WebP."
            );
          }
          return { ok: false, reason: (processed && processed.reason) || "corrupt" };
        }
        var fromURL =
          fabric.FabricImage && fabric.FabricImage.fromURL
            ? fabric.FabricImage.fromURL.bind(fabric.FabricImage)
            : fabric.Image && fabric.Image.fromURL
              ? fabric.Image.fromURL.bind(fabric.Image)
              : null;
        if (!fromURL) {
          setToolFeedback("Image import is unavailable.");
          return { ok: false, reason: "api" };
        }
        return fromURL(processed.dataUrl, { crossOrigin: "anonymous" }).then(
          function (img) {
            if (!img || !(img.width > 0) || !(img.height > 0)) {
              setToolFeedback(
                "That image file could not be decoded. Try a different PNG, JPG, or WebP."
              );
              return { ok: false, reason: "corrupt" };
            }
            var inserted = commitEdit(
              "add-image",
              function () {
                var displayMax = 400;
                var scale = Math.min(
                  1,
                  displayMax / Math.max(img.width || 1, img.height || 1)
                );
                var pos = nextInsertCenter();
                img.set({
                  left: pos.left,
                  top: pos.top,
                  originX: "center",
                  originY: "center",
                  scaleX: scale,
                  scaleY: scale,
                });
                assignBlytzId(img);
                assignBlytzName(img, "Image");
                canvas.add(img);
                canvas.setActiveObject(img);
                canvas.requestRenderAll();
                var bytes = measureEnvelopeBytes();
                var budget = Math.floor(
                  MAX_CANVAS_JSON_BYTES * IMAGE_INSERT_BUDGET_RATIO
                );
                if (bytes > budget) {
                  canvas.remove(img);
                  canvas.requestRenderAll();
                  setToolFeedback(
                    "Not enough room left in this design to add this image. Try a smaller image or remove one."
                  );
                  return false;
                }
                if (bytes > MAX_CANVAS_JSON_BYTES) {
                  canvas.remove(img);
                  canvas.requestRenderAll();
                  setToolFeedback(
                    "Design would exceed the save size limit after adding this image. Try a smaller file or fewer images."
                  );
                  return false;
                }
                setToolFeedback("Image added.");
                return true;
              },
              getJSON
            );
            return {
              ok: !!inserted,
              reason: inserted ? "ok" : "budget",
              processed: processed,
            };
          }
        );
      })
      .catch(function (err) {
        if (err && err.message === "decode") {
          setToolFeedback(
            "That image file could not be decoded. Try a different PNG, JPG, or WebP."
          );
          return { ok: false, reason: "corrupt" };
        }
        setToolFeedback("Could not read that image file.");
        return { ok: false, reason: "read" };
      })
      .finally(function () {
        setImagePickerBusy(false);
      });
  }

  function triggerImagePicker() {
    var fileInput = document.querySelector("[data-editor-image-input]");
    if (fileInput) fileInput.click();
  }

  /**
   * Insert a Fabric object built by factory({left, top}) via commitEdit.
   * factory receives cascade center; must return a fabric object (not a Group).
   * Optional defaultName sets blytzName when the factory did not.
   */
  function insertElement(label, factory, getJSON, defaultName) {
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    return commitEdit(
      label || "insert-element",
      function () {
        var pos = nextInsertCenter();
        var obj = factory(pos);
        if (!obj) return false;
        assignBlytzId(obj);
        if (defaultName) assignBlytzName(obj, defaultName);
        canvas.add(obj);
        canvas.setActiveObject(obj);
        canvas.requestRenderAll();
                if (measureEnvelopeBytes() > MAX_CANVAS_JSON_BYTES) {
          canvas.remove(obj);
          canvas.requestRenderAll();
          setToolFeedback(
            "Design would exceed the save size limit. Remove something and try again."
          );
          return false;
        }
        return true;
      },
      getJSON
    );
  }

  /** Stage 2 / F: align / distribute / center / flip (logical canvas or selection AABB — not print areas). */
  var ALIGN_DIRECTIONS = {
    left: true,
    hcenter: true,
    right: true,
    top: true,
    vcenter: true,
    bottom: true,
  };

  /**
   * Stage F locked policy for composition ops (align / distribute / center / flip):
   * reject the entire op if any selected member is locked — no silent skips.
   */
  function selectionHasLockedMembers(active) {
    if (!active) return false;
    if (isActiveSelection(active) && active.getObjects) {
      var members = active.getObjects();
      var i;
      for (i = 0; i < members.length; i++) {
        if (isObjectLocked(members[i])) return true;
      }
      return false;
    }
    return isObjectLocked(active);
  }

  function rejectLockedComposition() {
    setToolFeedback("Unlock locked layers before aligning or distributing.");
    return false;
  }

  function readObjectAabb(obj) {
    if (!obj || typeof obj.getBoundingRect !== "function") return null;
    var br;
    try {
      br = obj.getBoundingRect();
    } catch (err) {
      return null;
    }
    if (!br) return null;
    var width = Number(br.width);
    var height = Number(br.height);
    if (!(width > 0) || !(height > 0)) return null;
    return {
      left: Number(br.left),
      top: Number(br.top),
      width: width,
      height: height,
    };
  }

  function unionAabb(rects) {
    var left = Infinity;
    var top = Infinity;
    var right = -Infinity;
    var bottom = -Infinity;
    var count = 0;
    var i;
    for (i = 0; i < (rects || []).length; i++) {
      var r = rects[i];
      if (!r || !(r.width > 0) || !(r.height > 0)) continue;
      count += 1;
      left = Math.min(left, r.left);
      top = Math.min(top, r.top);
      right = Math.max(right, r.left + r.width);
      bottom = Math.max(bottom, r.top + r.height);
    }
    if (!count) return null;
    return {
      left: left,
      top: top,
      width: right - left,
      height: bottom - top,
    };
  }

  /** Mirror apps/designs/align_flip.py aabb_delta_align. */
  function aabbDeltaAlign(rect, direction, box) {
    if (!rect || !box || !ALIGN_DIRECTIONS[direction]) {
      return { dx: 0, dy: 0 };
    }
    var dx = 0;
    var dy = 0;
    if (direction === "left") dx = box.left - rect.left;
    else if (direction === "hcenter") {
      dx = box.left + box.width / 2 - (rect.left + rect.width / 2);
    } else if (direction === "right") {
      dx = box.left + box.width - (rect.left + rect.width);
    } else if (direction === "top") dy = box.top - rect.top;
    else if (direction === "vcenter") {
      dy = box.top + box.height / 2 - (rect.top + rect.height / 2);
    } else if (direction === "bottom") {
      dy = box.top + box.height - (rect.top + rect.height);
    }
    return { dx: dx, dy: dy };
  }

  /**
   * Mirror apps/designs/align_flip.py distribute_rects.
   * Equal edge-to-edge gaps along transformed AABBs; first/last stay fixed.
   * Returns [{index, dx, dy}, ...] for objects that need a translate, or null.
   */
  function distributeAabbDeltas(aabbs, axis) {
    if (axis !== "horizontal" && axis !== "vertical") return null;
    var indexed = [];
    var i;
    for (i = 0; i < (aabbs || []).length; i++) {
      var r = aabbs[i];
      if (!r || !(r.width > 0) || !(r.height > 0)) continue;
      indexed.push({ index: i, rect: r });
    }
    var n = indexed.length;
    if (n < 3) return null;
    var horizontal = axis === "horizontal";
    indexed.sort(function (a, b) {
      var ka = horizontal ? a.rect.left : a.rect.top;
      var kb = horizontal ? b.rect.left : b.rect.top;
      if (ka !== kb) return ka - kb;
      return a.index - b.index;
    });
    var sizes = indexed.map(function (item) {
      return horizontal ? item.rect.width : item.rect.height;
    });
    var first = indexed[0].rect;
    var last = indexed[n - 1].rect;
    var firstEdge = horizontal ? first.left : first.top;
    var lastEdge = horizontal
      ? last.left + last.width
      : last.top + last.height;
    var span = lastEdge - firstEdge;
    var sumSizes = 0;
    for (i = 0; i < sizes.length; i++) sumSizes += sizes[i];
    var gap = (span - sumSizes) / (n - 1);
    var targets = [firstEdge];
    var cursor = firstEdge + sizes[0] + gap;
    for (i = 1; i < n - 1; i++) {
      targets.push(cursor);
      cursor = cursor + sizes[i] + gap;
    }
    targets.push(horizontal ? last.left : last.top);
    var deltas = [];
    for (i = 0; i < n; i++) {
      var cur = indexed[i].rect;
      var dx = 0;
      var dy = 0;
      if (horizontal) dx = targets[i] - cur.left;
      else dy = targets[i] - cur.top;
      if (dx || dy) {
        deltas.push({ index: indexed[i].index, dx: dx, dy: dy });
      }
    }
    return deltas;
  }

  function canvasAabbBox() {
    return { left: 0, top: 0, width: LOGICAL_SIZE, height: LOGICAL_SIZE };
  }

  function translateObjectBy(obj, dx, dy) {
    if (!obj || (!dx && !dy)) return;
    obj.set({
      left: (obj.left || 0) + dx,
      top: (obj.top || 0) + dy,
    });
    if (typeof obj.setCoords === "function") obj.setCoords();
  }

  /**
   * Exit ActiveSelection so object left/top are canvas-absolute, run fn(objects),
   * then restore multi-selection when needed. Avoids selection-local coord bugs.
   */
  function withAbsoluteSelectionObjects(canvas, fn) {
    var fabric = fabricNS();
    var active = canvas.getActiveObject();
    if (!active) return false;
    var wasMulti = isActiveSelection(active);
    var objects = wasMulti
      ? active.getObjects().slice()
      : [active];
    if (!objects.length) return false;
    // Capture canvas-space AABBs before discard (getBoundingRect is absolute).
    var aabbs = [];
    var i;
    for (i = 0; i < objects.length; i++) {
      aabbs.push(readObjectAabb(objects[i]));
    }
    if (wasMulti) {
      canvas.discardActiveObject();
    }
    var changed = fn(objects, aabbs, wasMulti);
    if (wasMulti && objects.length > 1 && fabric && fabric.ActiveSelection) {
      try {
        var sel = new fabric.ActiveSelection(objects, { canvas: canvas });
        canvas.setActiveObject(sel);
      } catch (err) {
        console.warn("BlytzCanvas: could not restore multi-selection", err);
      }
    } else if (!wasMulti && objects[0]) {
      canvas.setActiveObject(objects[0]);
    }
    canvas.requestRenderAll();
    return changed !== false;
  }

  /**
   * Align selection to the logical canvas (single or multi as a group of individuals
   * each aligned to the canvas box — for multi prefer centerOnCanvas for group move).
   * mode "canvas": each object aligns to LOGICAL_SIZE box.
   * mode "selection": each object aligns to the union AABB (multi only; single is no-op).
   * Locked policy: reject whole op if any member is locked.
   */
  function alignActive(direction, mode, getJSON) {
    if (!ALIGN_DIRECTIONS[direction]) return false;
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var active = canvas.getActiveObject();
    if (!active) {
      setToolFeedback("Select an object to align.");
      return false;
    }
    if (selectionHasLockedMembers(active)) return rejectLockedComposition();
    var useSelection = mode === "selection";
    if (useSelection && !isActiveSelection(active)) {
      setToolFeedback("Select multiple objects to align together.");
      return false;
    }
    var label =
      (useSelection ? "align-selection-" : "align-canvas-") + direction;
    return commitEdit(
      label,
      function () {
        return withAbsoluteSelectionObjects(canvas, function (objects, aabbs) {
          var box = useSelection
            ? unionAabb(aabbs)
            : canvasAabbBox();
          if (!box) return false;
          var moved = false;
          var i;
          for (i = 0; i < objects.length; i++) {
            var rect = aabbs[i];
            if (!rect) continue;
            var d = aabbDeltaAlign(rect, direction, box);
            if (d.dx || d.dy) {
              translateObjectBy(objects[i], d.dx, d.dy);
              moved = true;
            }
          }
          return moved;
        });
      },
      getJSON
    );
  }

  /**
   * Stage F — distribute ≥3 selected objects evenly along axis using transformed
   * AABBs (equal edge gaps; first/last fixed). One undo step; locked → reject all.
   */
  function distributeActive(axis, getJSON) {
    if (axis !== "horizontal" && axis !== "vertical") return false;
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var active = canvas.getActiveObject();
    if (!active || !isActiveSelection(active)) {
      setToolFeedback("Select at least 3 objects to distribute.");
      return false;
    }
    if (selectionHasLockedMembers(active)) return rejectLockedComposition();
    var count =
      (active.getObjects && active.getObjects().length) || 0;
    if (count < 3) {
      setToolFeedback("Select at least 3 objects to distribute.");
      return false;
    }
    return commitEdit(
      "distribute-" + axis,
      function () {
        return withAbsoluteSelectionObjects(canvas, function (objects, aabbs) {
          var deltas = distributeAabbDeltas(aabbs, axis);
          if (!deltas || !deltas.length) return false;
          var i;
          var moved = false;
          for (i = 0; i < deltas.length; i++) {
            var d = deltas[i];
            if (!d || (!d.dx && !d.dy)) continue;
            translateObjectBy(objects[d.index], d.dx, d.dy);
            moved = true;
          }
          return moved;
        });
      },
      getJSON
    );
  }

  /**
   * Move the whole selection by one shared delta so its AABB centers on the
   * logical canvas (axis: horizontal | vertical | both). Preserves relative
   * arrangement for multi-select. Locked policy: reject whole op.
   */
  function centerOnCanvas(axis, getJSON) {
    if (axis !== "horizontal" && axis !== "vertical" && axis !== "both") {
      return false;
    }
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var active = canvas.getActiveObject();
    if (!active) {
      setToolFeedback("Select an object to center on the canvas.");
      return false;
    }
    if (selectionHasLockedMembers(active)) return rejectLockedComposition();
    return commitEdit(
      "center-canvas-" + axis,
      function () {
        return withAbsoluteSelectionObjects(canvas, function (objects, aabbs) {
          var box = unionAabb(aabbs);
          if (!box) return false;
          var canvasBox = canvasAabbBox();
          var dx = 0;
          var dy = 0;
          if (axis === "horizontal" || axis === "both") {
            dx = canvasBox.width / 2 - (box.left + box.width / 2);
          }
          if (axis === "vertical" || axis === "both") {
            dy = canvasBox.height / 2 - (box.top + box.height / 2);
          }
          if (!dx && !dy) return false;
          var i;
          for (i = 0; i < objects.length; i++) {
            translateObjectBy(objects[i], dx, dy);
          }
          return true;
        });
      },
      getJSON
    );
  }

  /**
   * Stage E — fit a single unlocked image inside the logical canvas (uniform scale,
   * preserve aspect, then center). Does NOT stretch-to-fill, reset rotation,
   * replace src, or switch Front/Back. Returns false for non-image / multi / locked.
   */
  function fitActiveWithinCanvas(getJSON) {
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var obj = canvas.getActiveObject();
    if (!obj || isActiveSelection(obj) || typeKey(obj) !== "image") {
      setToolFeedback("Select a single image to fit to the canvas.");
      return false;
    }
    if (isObjectLocked(obj)) {
      setToolFeedback("Unlock the image in Layers to edit it.");
      return false;
    }
    return commitEdit(
      "image-fit-canvas",
      function () {
        var id = obj.blytzId;
        var name = obj.blytzName;
        var src = obj.get && obj.get("src") != null ? obj.get("src") : obj.src;
        var sw = typeof obj.getScaledWidth === "function" ? obj.getScaledWidth() : 0;
        var sh = typeof obj.getScaledHeight === "function" ? obj.getScaledHeight() : 0;
        if (!(sw > 0) || !(sh > 0)) return false;
        var factor = Math.min(LOGICAL_SIZE / sw, LOGICAL_SIZE / sh);
        if (!isFinite(factor) || !(factor > 0)) return false;
        if (Math.abs(factor - 1) >= 0.0001) {
          obj.set({
            scaleX: (obj.scaleX == null ? 1 : obj.scaleX) * factor,
            scaleY: (obj.scaleY == null ? 1 : obj.scaleY) * factor,
          });
        }
        var fabric = fabricNS();
        var Point = fabric && (fabric.Point || fabric.point);
        var mid = Point
          ? new Point(LOGICAL_SIZE / 2, LOGICAL_SIZE / 2)
          : { x: LOGICAL_SIZE / 2, y: LOGICAL_SIZE / 2 };
        if (typeof obj.setPositionByOrigin === "function") {
          obj.setPositionByOrigin(mid, "center", "center");
        } else {
          obj.set({
            left: LOGICAL_SIZE / 2,
            top: LOGICAL_SIZE / 2,
            originX: "center",
            originY: "center",
          });
        }
        if (typeof obj.setCoords === "function") obj.setCoords();
        if (id != null) obj.blytzId = id;
        if (name != null) obj.blytzName = name;
        if (src != null) {
          if (typeof obj.set === "function") obj.set("src", src);
          else obj.src = src;
        }
        canvas.requestRenderAll();
        return true;
      },
      getJSON
    );
  }

  /**
   * Stage R.2 — replace the active image's src (e.g. after client BG removal).
   * Preserves blytzId / name / transform / opacity. One history step after load.
   * Returns a Promise<{ok, reason}>. Locked / non-image → resolved false.
   */
  function replaceActiveImageSrc(dataUrl, getJSON) {
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return Promise.resolve({ ok: false, reason: "not-ready" });
    }
    if (
      typeof dataUrl !== "string" ||
      dataUrl.indexOf("data:image/") !== 0
    ) {
      setToolFeedback("Background removal returned an invalid image.");
      return Promise.resolve({ ok: false, reason: "bad-url" });
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) {
      return Promise.resolve({ ok: false, reason: "no-canvas" });
    }
    var obj = canvas.getActiveObject();
    if (!obj || isActiveSelection(obj) || typeKey(obj) !== "image") {
      setToolFeedback("Select a single image to remove its background.");
      return Promise.resolve({ ok: false, reason: "selection" });
    }
    if (isObjectLocked(obj)) {
      setToolFeedback("Unlock the image in Layers to edit it.");
      return Promise.resolve({ ok: false, reason: "locked" });
    }

    var id = obj.blytzId;
    var name = obj.blytzName;
    var setSrc =
      typeof obj.setSrc === "function" ? obj.setSrc.bind(obj) : null;

    function afterLoaded() {
      var changed = commitEdit(
        "remove-bg",
        function () {
          if (id != null) obj.blytzId = id;
          if (name != null) obj.blytzName = name;
          if (typeof obj.setCoords === "function") obj.setCoords();
          canvas.requestRenderAll();
          return true;
        },
        getJSON
      );
      if (changed) setToolFeedback("Background removed.");
      return { ok: !!changed, reason: changed ? "ok" : "commit" };
    }

    if (setSrc) {
      return Promise.resolve(setSrc(dataUrl, { crossOrigin: "anonymous" }))
        .then(afterLoaded)
        .catch(function () {
          setToolFeedback("Could not apply the background-removed image.");
          return { ok: false, reason: "setSrc" };
        });
    }

    // Fallback: load via fromURL and copy element onto the existing object.
    var fabric = fabricNS();
    var fromURL =
      fabric && fabric.FabricImage && fabric.FabricImage.fromURL
        ? fabric.FabricImage.fromURL.bind(fabric.FabricImage)
        : fabric && fabric.Image && fabric.Image.fromURL
          ? fabric.Image.fromURL.bind(fabric.Image)
          : null;
    if (!fromURL) {
      setToolFeedback("Image update is unavailable.");
      return Promise.resolve({ ok: false, reason: "api" });
    }
    return fromURL(dataUrl, { crossOrigin: "anonymous" })
      .then(function (img) {
        if (!img) throw new Error("empty");
        if (typeof obj.setElement === "function" && img.getElement) {
          obj.setElement(img.getElement());
        } else if (typeof obj.set === "function") {
          obj.set("src", dataUrl);
        } else {
          obj.src = dataUrl;
        }
        if (img.width) obj.width = img.width;
        if (img.height) obj.height = img.height;
        return afterLoaded();
      })
      .catch(function () {
        setToolFeedback("Could not apply the background-removed image.");
        return { ok: false, reason: "fromURL" };
      });
  }

  /**
   * Stage E — set angle to 0 while preserving center point and unrelated props.
   * Image-only from Properties; rejects multi-select and locked objects.
   */
  function resetActiveRotation(getJSON) {
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var obj = canvas.getActiveObject();
    if (!obj || isActiveSelection(obj) || typeKey(obj) !== "image") {
      setToolFeedback("Select a single image to reset rotation.");
      return false;
    }
    if (isObjectLocked(obj)) {
      setToolFeedback("Unlock the image in Layers to edit it.");
      return false;
    }
    var cur = obj.angle || 0;
    if (Math.abs(cur) < 0.001) return false;
    return commitEdit(
      "image-reset-rotation",
      function () {
        var id = obj.blytzId;
        var name = obj.blytzName;
        var center =
          typeof obj.getCenterPoint === "function"
            ? obj.getCenterPoint()
            : { x: obj.left || 0, y: obj.top || 0 };
        obj.set("angle", 0);
        var fabric = fabricNS();
        var Point = fabric && (fabric.Point || fabric.point);
        var pt = Point ? new Point(center.x, center.y) : { x: center.x, y: center.y };
        if (typeof obj.setPositionByOrigin === "function") {
          obj.setPositionByOrigin(pt, "center", "center");
        }
        if (typeof obj.setCoords === "function") obj.setCoords();
        if (id != null) obj.blytzId = id;
        if (name != null) obj.blytzName = name;
        canvas.requestRenderAll();
        return true;
      },
      getJSON
    );
  }

  /**
   * Stage E — center a single unlocked image on the logical canvas (both axes).
   * Thin wrapper over centerOnCanvas("both") with image/lock gating + feedback.
   */
  function centerActiveImage(getJSON) {
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var obj = canvas.getActiveObject();
    if (!obj || isActiveSelection(obj) || typeKey(obj) !== "image") {
      setToolFeedback("Select a single image to center on the canvas.");
      return false;
    }
    if (isObjectLocked(obj)) {
      setToolFeedback("Unlock the image in Layers to edit it.");
      return false;
    }
    return centerOnCanvas("both", getJSON);
  }

  /**
   * Flip via Fabric flipX / flipY. Preserves blytzId / blytzName / object identity.
   * ActiveSelection: discard, flip each object, restore selection (safe for IDs).
   */
  function flipActive(axis, getJSON) {
    if (axis !== "horizontal" && axis !== "vertical") return false;
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var active = canvas.getActiveObject();
    if (!active) {
      setToolFeedback("Select an object to flip.");
      return false;
    }
    if (selectionHasLockedMembers(active)) return rejectLockedComposition();
    var prop = axis === "horizontal" ? "flipX" : "flipY";
    return commitEdit(
      "flip-" + axis,
      function () {
        return withAbsoluteSelectionObjects(canvas, function (objects) {
          var i;
          for (i = 0; i < objects.length; i++) {
            var obj = objects[i];
            if (!obj) continue;
            // Snapshot identity — flip must not mint new ids or rename layers.
            var id = obj.blytzId;
            var name = obj.blytzName;
            obj.set(prop, !obj.get(prop));
            if (typeof obj.setCoords === "function") obj.setCoords();
            if (id != null) obj.blytzId = id;
            if (name != null) obj.blytzName = name;
          }
          return true;
        });
      },
      getJSON
    );
  }

  /**
   * UC-06 rule-based auto-layout (deterministic; mirrors apps/designs/auto_layout.py).
   * Active view only. Skips locked (blytzLocked) and hidden (visible===false).
   * Images 1→center, 2→left-chest, 3→right-chest; extras unmoved. Texts under primary.
   * One commitEdit. Slots from primary print panel (id front|back), else largest area.
   */
  var AUTO_LAYOUT_TEXT_GAP = 16;
  var AUTO_LAYOUT_TEXT_STACK_GAP = 12;
  var AUTO_LAYOUT_CENTER_W_FRAC = 0.55;
  var AUTO_LAYOUT_CENTER_H_FRAC = 0.42;
  var AUTO_LAYOUT_CHEST_W_FRAC = 0.22;
  var AUTO_LAYOUT_CHEST_H_FRAC = 0.22;
  var AUTO_LAYOUT_CHEST_X_INSET = 0.06;
  var AUTO_LAYOUT_CHEST_Y_INSET = 0.1;
  var AUTO_LAYOUT_WORDMARK_W_FRAC = 0.7;
  var AUTO_LAYOUT_WORDMARK_H_FRAC = 0.18;

  function pickPrimaryPrintPanel(areas) {
    var list = Array.isArray(areas) ? areas : [];
    var i;
    var primaries = [];
    for (i = 0; i < list.length; i++) {
      var a = list[i];
      if (!a) continue;
      var id = String(a.id || "").toLowerCase();
      if (id === "front" || id === "back") primaries.push(a);
    }
    if (primaries.length) return primaries[0];
    var best = null;
    var bestArea = -1;
    for (i = 0; i < list.length; i++) {
      var area = list[i];
      if (!area) continue;
      var w = Number(area.w);
      var h = Number(area.h);
      if (!(w > 0) || !(h > 0)) continue;
      var size = w * h;
      if (size > bestArea) {
        bestArea = size;
        best = area;
      }
    }
    return best;
  }

  function getActivePrimaryPrintPanel() {
    var g = global.BlytzGarments;
    if (!g || typeof g.getPrintAreas !== "function") return null;
    var result = g.getPrintAreas(garmentState.template, activeView);
    if (!result || !result.ok || !result.areas || !result.areas.length) return null;
    return pickPrimaryPrintPanel(result.areas);
  }

  /** Mirror auto_layout.derive_slots */
  function deriveAutoLayoutSlots(panel) {
    if (!panel) return null;
    var x = Number(panel.x);
    var y = Number(panel.y);
    var w = Number(panel.w);
    var h = Number(panel.h);
    if (!(w > 0) || !(h > 0) || isNaN(x) || isNaN(y)) return null;
    var cx = x + w / 2;
    var cy = y + h / 2;
    var centerW = w * AUTO_LAYOUT_CENTER_W_FRAC;
    var centerH = h * AUTO_LAYOUT_CENTER_H_FRAC;
    var chestW = w * AUTO_LAYOUT_CHEST_W_FRAC;
    var chestH = h * AUTO_LAYOUT_CHEST_H_FRAC;
    var leftCx = x + w * AUTO_LAYOUT_CHEST_X_INSET + chestW / 2;
    var rightCx = x + w * (1 - AUTO_LAYOUT_CHEST_X_INSET) - chestW / 2;
    var chestCy = y + h * AUTO_LAYOUT_CHEST_Y_INSET + chestH / 2;
    return {
      center: {
        cx: cx,
        cy: y + h * 0.38,
        max_w: centerW,
        max_h: centerH,
      },
      left_chest: {
        cx: leftCx,
        cy: chestCy,
        max_w: chestW,
        max_h: chestH,
      },
      right_chest: {
        cx: rightCx,
        cy: chestCy,
        max_w: chestW,
        max_h: chestH,
      },
      wordmark: {
        cx: cx,
        cy: cy,
        max_w: w * AUTO_LAYOUT_WORDMARK_W_FRAC,
        max_h: h * AUTO_LAYOUT_WORDMARK_H_FRAC,
      },
      panel: { x: x, y: y, w: w, h: h },
    };
  }

  function autoLayoutScaleToFit(width, height, maxW, maxH, allowUpscale) {
    var w = Math.max(1e-6, Number(width) || 0);
    var h = Math.max(1e-6, Number(height) || 0);
    var mw = Math.max(1e-6, Number(maxW) || 0);
    var mh = Math.max(1e-6, Number(maxH) || 0);
    var factor = Math.min(mw / w, mh / h);
    if (!allowUpscale) factor = Math.min(1, factor);
    return factor > 0 ? factor : 1e-6;
  }

  function autoLayoutClampCenter(cx, cy, width, height, panel) {
    if (!panel) return { cx: cx, cy: cy };
    var halfW = Math.max(0, width / 2);
    var halfH = Math.max(0, height / 2);
    var minCx = panel.x + halfW;
    var maxCx = panel.x + panel.w - halfW;
    var minCy = panel.y + halfH;
    var maxCy = panel.y + panel.h - halfH;
    if (minCx > maxCx) cx = panel.x + panel.w / 2;
    else cx = Math.min(Math.max(cx, minCx), maxCx);
    if (minCy > maxCy) cy = panel.y + panel.h / 2;
    else cy = Math.min(Math.max(cy, minCy), maxCy);
    return { cx: cx, cy: cy };
  }

  /** Mirror auto_layout.plan_auto_layout — items already filtered for locked/hidden. */
  function planAutoLayout(items, panel) {
    var slots = deriveAutoLayoutSlots(panel);
    if (!slots) {
      return {
        ok: false,
        reason: "no_panel",
        placements: [],
        skipped_extra_images: 0,
        notes: "",
      };
    }
    var movable = [];
    var i;
    for (i = 0; i < (items || []).length; i++) {
      var raw = items[i];
      if (!raw) continue;
      if (raw.visible === false) continue;
      if (raw.locked || raw.blytzLocked) continue;
      var kind = String(raw.kind || raw.type || "").toLowerCase();
      var isImg = kind === "image";
      var isTxt = kind === "text" || kind === "itext" || kind === "textbox";
      if (!isImg && !isTxt) continue;
      var width = Number(raw.width);
      var height = Number(raw.height);
      if (!(width > 0) || !(height > 0)) continue;
      movable.push({
        id: raw.id != null && raw.id !== "" ? raw.id : i,
        kind: isImg ? "image" : "text",
        width: width,
        height: height,
        order: raw.order != null ? Number(raw.order) : i,
      });
    }
    if (!movable.length) {
      return {
        ok: false,
        reason: "empty",
        placements: [],
        skipped_extra_images: 0,
        notes: "",
      };
    }
    movable.sort(function (a, b) {
      if (a.order !== b.order) return a.order - b.order;
      return String(a.id).localeCompare(String(b.id));
    });
    var images = movable.filter(function (it) {
      return it.kind === "image";
    });
    var texts = movable.filter(function (it) {
      return it.kind === "text";
    });
    var placements = [];
    var panelN = slots.panel;
    var notes = "";
    var skippedExtra = Math.max(0, images.length - 3);
    var primaryBottom = null;
    var primaryCx = slots.center.cx;

    function placeInSlot(item, slot) {
      var factor = autoLayoutScaleToFit(
        item.width,
        item.height,
        slot.max_w,
        slot.max_h,
        true
      );
      var nw = item.width * factor;
      var nh = item.height * factor;
      var clamped = autoLayoutClampCenter(slot.cx, slot.cy, nw, nh, panelN);
      return {
        id: item.id,
        cx: clamped.cx,
        cy: clamped.cy,
        width: nw,
        height: nh,
        scale_factor: factor,
      };
    }

    if (images.length) {
      var slotKeys = ["center", "left_chest", "right_chest"];
      for (i = 0; i < Math.min(3, images.length); i++) {
        var pl = placeInSlot(images[i], slots[slotKeys[i]]);
        placements.push(pl);
        if (i === 0) {
          primaryBottom = pl.cy + pl.height / 2;
          primaryCx = pl.cx;
        }
      }
      if (skippedExtra) {
        notes = skippedExtra + " extra image(s) left unmoved.";
      }
    } else if (texts.length) {
      var first = texts[0];
      var wm = placeInSlot(first, slots.wordmark);
      placements.push(wm);
      primaryBottom = wm.cy + wm.height / 2;
      primaryCx = wm.cx;
      texts = texts.slice(1);
    }

    if (texts.length && primaryBottom != null) {
      var cursorTop = primaryBottom + AUTO_LAYOUT_TEXT_GAP;
      for (i = 0; i < texts.length; i++) {
        var t = texts[i];
        var tf = autoLayoutScaleToFit(
          t.width,
          t.height,
          panelN.w * 0.85,
          panelN.h * 0.12,
          true
        );
        var tw = t.width * tf;
        var th = t.height * tf;
        var tcy = cursorTop + th / 2;
        var tc = autoLayoutClampCenter(primaryCx, tcy, tw, th, panelN);
        placements.push({
          id: t.id,
          cx: tc.cx,
          cy: tc.cy,
          width: tw,
          height: th,
          scale_factor: tf,
        });
        cursorTop = tc.cy + th / 2 + AUTO_LAYOUT_TEXT_STACK_GAP;
      }
    }

    if (!placements.length) {
      return {
        ok: false,
        reason: "empty",
        placements: [],
        skipped_extra_images: skippedExtra,
        notes: notes,
      };
    }
    return {
      ok: true,
      reason: "ok",
      placements: placements,
      skipped_extra_images: skippedExtra,
      notes: notes,
    };
  }

  function collectAutoLayoutItems(canvas) {
    var objects = canvas && canvas.getObjects ? canvas.getObjects() : [];
    var items = [];
    var i;
    for (i = 0; i < objects.length; i++) {
      var obj = objects[i];
      if (!obj) continue;
      if (obj.visible === false) continue;
      if (isObjectLocked(obj)) continue;
      var tk = typeKey(obj);
      if (tk !== "image" && !isTextObject(obj)) continue;
      var sw =
        typeof obj.getScaledWidth === "function"
          ? obj.getScaledWidth()
          : Number(obj.width) * (obj.scaleX == null ? 1 : obj.scaleX);
      var sh =
        typeof obj.getScaledHeight === "function"
          ? obj.getScaledHeight()
          : Number(obj.height) * (obj.scaleY == null ? 1 : obj.scaleY);
      if (!(sw > 0) || !(sh > 0)) continue;
      items.push({
        id: obj.blytzId != null ? obj.blytzId : i,
        kind: tk === "image" ? "image" : "text",
        width: sw,
        height: sh,
        order: i,
        obj: obj,
      });
    }
    return items;
  }

  function canAutoLayout() {
    if (!persistAllowed()) return false;
    if (!fabricCanvas) return false;
    if (!getActivePrimaryPrintPanel()) return false;
    return collectAutoLayoutItems(fabricCanvas).length > 0;
  }

  function applyAutoLayoutPlacement(obj, placement) {
    if (!obj || !placement) return false;
    var id = obj.blytzId;
    var name = obj.blytzName;
    var factor = Number(placement.scale_factor);
    if (isFinite(factor) && factor > 0 && Math.abs(factor - 1) >= 0.0001) {
      obj.set({
        scaleX: (obj.scaleX == null ? 1 : obj.scaleX) * factor,
        scaleY: (obj.scaleY == null ? 1 : obj.scaleY) * factor,
      });
    }
    var fabric = fabricNS();
    var Point = fabric && (fabric.Point || fabric.point);
    var pt = Point
      ? new Point(placement.cx, placement.cy)
      : { x: placement.cx, y: placement.cy };
    if (typeof obj.setPositionByOrigin === "function") {
      obj.setPositionByOrigin(pt, "center", "center");
    } else {
      obj.set({
        left: placement.cx,
        top: placement.cy,
        originX: "center",
        originY: "center",
      });
    }
    if (typeof obj.setCoords === "function") obj.setCoords();
    if (id != null) obj.blytzId = id;
    if (name != null) obj.blytzName = name;
    return true;
  }

  function autoLayoutActive(getJSON) {
    if (!persistAllowed()) {
      setToolFeedback(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Editing is unavailable until the design finishes loading."
      );
      return false;
    }
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var panel = getActivePrimaryPrintPanel();
    if (!panel) {
      setToolFeedback("Print panel unavailable for auto layout.");
      return false;
    }
    var items = collectAutoLayoutItems(canvas);
    if (!items.length) {
      setToolFeedback("Nothing to layout — add unlocked images or text.");
      return false;
    }
    var plan = planAutoLayout(items, panel);
    if (!plan.ok || !plan.placements.length) {
      setToolFeedback(
        plan.reason === "empty"
          ? "Nothing to layout — add unlocked images or text."
          : "Auto layout could not place objects."
      );
      return false;
    }
    var byId = {};
    var i;
    for (i = 0; i < items.length; i++) {
      byId[String(items[i].id)] = items[i].obj;
    }
    var skippedLocked = 0;
    var allObjs = canvas.getObjects();
    for (i = 0; i < allObjs.length; i++) {
      var o = allObjs[i];
      if (!o) continue;
      var tk = typeKey(o);
      if (tk !== "image" && !isTextObject(o)) continue;
      if (o.visible === false) continue;
      if (isObjectLocked(o)) skippedLocked += 1;
    }
    return commitEdit(
      "auto-layout",
      function () {
        canvas.discardActiveObject();
        var moved = 0;
        for (i = 0; i < plan.placements.length; i++) {
          var pl = plan.placements[i];
          var target = byId[String(pl.id)];
          if (!target) continue;
          if (applyAutoLayoutPlacement(target, pl)) moved += 1;
        }
        if (!moved) return false;
        canvas.requestRenderAll();
        return true;
      },
      getJSON
    )
      ? (function () {
          var parts = ["Auto layout applied."];
          if (skippedLocked) {
            parts.push(skippedLocked + " locked skipped.");
          }
          if (plan.notes) parts.push(plan.notes);
          setToolFeedback(parts.join(" "));
          return true;
        })()
      : false;
  }

  /**
   * Stacking reorder via Fabric 6.6.1 canvas methods.
   * bringObjectForward/sendObjectBackwards with intersecting=false → one list step.
   */
  function reorderActive(action, getJSON) {
    if (!persistAllowed()) return false;
    var canvas = ensureCanvas(getJSON);
    if (!canvas) return false;
    var obj = canvas.getActiveObject();
    if (!obj || isActiveSelection(obj)) return false;
    return commitEdit(
      "reorder-" + action,
      function () {
        var moved = false;
        if (action === "forward") {
          moved = !!canvas.bringObjectForward(obj, false);
        } else if (action === "backward") {
          moved = !!canvas.sendObjectBackwards(obj, false);
        } else if (action === "front") {
          moved = !!canvas.bringObjectToFront(obj);
        } else if (action === "back") {
          moved = !!canvas.sendObjectToBack(obj);
        }
        if (!moved) return false;
        canvas.requestRenderAll();
        return true;
      },
      getJSON
    );
  }

  function canReorderActive(action) {
    var canvas = fabricCanvas;
    if (!canvas) return false;
    var obj = canvas.getActiveObject();
    if (!obj || isActiveSelection(obj)) return false;
    var idx = canvas.getObjects().indexOf(obj);
    if (idx < 0) return false;
    var last = canvas.getObjects().length - 1;
    if (action === "forward" || action === "front") return idx < last;
    if (action === "backward" || action === "back") return idx > 0;
    return false;
  }

  function wireTools(getJSON) {
    if (toolsWired) return;
    toolsWired = true;
    getJSONRef = getJSON;

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-editor-action]");
      if (!btn || btn.getAttribute("aria-disabled") === "true" || btn.disabled) {
        return;
      }
      var action = btn.getAttribute("data-editor-action");
      if (action === "add-text") {
        // Phone Text sheet is opened by editor_tools; desktop inserts immediately.
        if (prefersSheetTextEdit()) return;
        e.preventDefault();
        addText(getJSON);
      } else if (action === "delete") {
        e.preventDefault();
        deleteSelection(getJSON);
      } else if (action === "select") {
        e.preventDefault();
        setMultiSelectMode(false);
      } else       if (action === "multi-select") {
        e.preventDefault();
        setMultiSelectMode(!multiSelectMode);
      } else if (action === "auto-layout") {
        e.preventDefault();
        autoLayoutActive(getJSON);
      }
      // add-image / elements are handled by editor_tools.js (panel open).
    });

    document.querySelectorAll("[data-editor-image-input]").forEach(function (fileInput) {
      fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        // Cancelled picker → no file → silent.
        if (!file) {
          fileInput.value = "";
          return;
        }
        addImageFromFile(file, getJSON).then(function (result) {
          if (
            result &&
            result.ok &&
            global.BlytzEditorTools &&
            typeof global.BlytzEditorTools.onSuccessfulInsert === "function"
          ) {
            global.BlytzEditorTools.onSuccessfulInsert("upload");
          }
        });
        fileInput.value = "";
      });
    });

    document.addEventListener("keydown", function (e) {
      if (!fabricCanvas) return;
      var target = e.target;
      var tag = (target && target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (target && target.isContentEditable) return;
      // Escape clears selection without dirtying (skip when props sheet owns Escape).
      if (e.key === "Escape") {
        var props = global.BlytzEditorProps;
        if (props && typeof props.isSheetOpen === "function" && props.isSheetOpen()) {
          return;
        }
        var escActive = fabricCanvas.getActiveObject();
        if (!escActive || escActive.isEditing) return;
        e.preventDefault();
        clearSelection();
        return;
      }
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      var active = fabricCanvas.getActiveObject();
      if (!active) return;
      if (active.isEditing) return;
      e.preventDefault();
      deleteSelection(getJSON);
    });

    syncMultiSelectUi();
    wireContextMenuSuppression();
  }

  var api = {
    LOGICAL_SIZE: LOGICAL_SIZE,
    SCHEMA_VERSION: SCHEMA_VERSION,
    fabricVersionOk: fabricVersionOk,
    MAX_CANVAS_JSON_BYTES: MAX_CANVAS_JSON_BYTES,
    IMAGE_INSERT_BUDGET_RATIO: IMAGE_INSERT_BUDGET_RATIO,
    IMAGE_INPUT_LIMIT_BYTES: IMAGE_INPUT_LIMIT_BYTES,
    IMAGE_MAX_EDGE: IMAGE_MAX_EDGE,
    IMAGE_TARGET_BYTES: IMAGE_TARGET_BYTES,
    IMAGE_QUALITY_STEPS: IMAGE_QUALITY_STEPS,
    IMAGE_EDGE_STEPS: IMAGE_EDGE_STEPS,
    IMAGE_MAX_PIXELS: IMAGE_MAX_PIXELS,
    measureEnvelopeBytes: measureEnvelopeBytes,
    ALLOWED_FONTS: ALLOWED_FONTS,
    COLOR_PRESETS: COLOR_PRESETS,
    PROP_LIMITS: PROP_LIMITS,
    TEXT_ALIGN_VALUES: TEXT_ALIGN_VALUES,
    ALLOWED_IMAGE_TYPES: ALLOWED_IMAGE_TYPES,
    DEFAULT_SHAPE_FILL: DEFAULT_SHAPE_FILL,
    DEFAULT_SHAPE_MAX_EDGE: DEFAULT_SHAPE_MAX_EDGE,
    ALLOWED_OBJECT_TYPES: ALLOWED_OBJECT_TYPES,
    SERIALIZE_PROPS: SERIALIZE_PROPS,
    CURVE_AMOUNT_MIN: CURVE_AMOUNT_MIN,
    CURVE_AMOUNT_MAX: CURVE_AMOUNT_MAX,
    CURVE_BULGE_FACTOR: CURVE_BULGE_FACTOR,
    applyTextCurve: applyTextCurve,
    clearTextCurve: clearTextCurve,
    previewTextCurveOnObject: previewTextCurveOnObject,
    setCurveOnObject: setCurveOnObject,
    buildArcPathD: buildArcPathD,
    clampCurveAmount: clampCurveAmount,
    normalizeCurveDirection: normalizeCurveDirection,
    textHasMultipleLines: textHasMultipleLines,
    isTextObject: isTextObject,
    PRINT_OVERFLOW_EPS: PRINT_OVERFLOW_EPS,
    printAreaContainsRect: printAreaContainsRect,
    artworkOverflowsPrintAreas: artworkOverflowsPrintAreas,
    evaluatePrintOverflow: evaluatePrintOverflow,
    collectArtworkBounds: collectArtworkBounds,
    schedulePrintOverflowCheck: schedulePrintOverflowCheck,
    applyPrintOverflowWarning: applyPrintOverflowWarning,
    getPrintOverflowState: getPrintOverflowState,
    utf8ByteLength: utf8ByteLength,
    parseInput: parseInput,
    scanCanvasPayload: scanCanvasPayload,
    validateObjectsAllowlist: validateObjectsAllowlist,
    isLegacyEmpty: isLegacyEmpty,
    isBlytzV1: isBlytzV1,
    isUnsupportedLegacy: isUnsupportedLegacy,
    emptyEnvelope: emptyEnvelope,
    emptyFabricCanvasObject: emptyFabricCanvasObject,
    ensureCanvas: ensureCanvas,
    loadFabricPayload: loadFabricPayload,
    loadAllViewsFromEnvelope: loadAllViewsFromEnvelope,
    buildEnvelopeFromCanvas: buildEnvelopeFromCanvas,
    getActiveCanvasJSON: getActiveCanvasJSON,
    getActiveView: getActiveView,
    setStoredViewPayload: setStoredViewPayload,
    setActiveView: setActiveView,
    onViewChange: onViewChange,
    getGarmentState: getGarmentState,
    setGarmentState: setGarmentState,
    onGarmentChange: onGarmentChange,
    refreshGarmentLayer: refreshGarmentLayer,
    forceTransparentBackground: forceTransparentBackground,
    defaultContrastFill: defaultContrastFill,
    initGarmentFromPage: initGarmentFromPage,
    aiCandidatesPending: aiCandidatesPending,
    VIEW_SWITCH_DURING_AI_PREVIEW: VIEW_SWITCH_DURING_AI_PREVIEW,
    applyResponsiveSize: applyResponsiveSize,
    getZoom: getZoom,
    setZoomLevel: setZoomLevel,
    zoomBy: zoomBy,
    resetZoom: resetZoom,
    clampZoom: clampZoom,
    nextZoomStep: nextZoomStep,
    sceneZoomToPoint: sceneZoomToPoint,
    panSceneBy: panSceneBy,
    ensureArtboardScene: ensureArtboardScene,
    ensureFabricViewportIdentity: ensureFabricViewportIdentity,
    applySceneTransform: applySceneTransform,
    syncGarmentViewport: syncGarmentViewport,
    onZoomChange: onZoomChange,
    ZOOM_MIN: ZOOM_MIN,
    ZOOM_MAX: ZOOM_MAX,
    ZOOM_STEP_FACTOR: ZOOM_STEP_FACTOR,
    setToolFeedback: setToolFeedback,
    setMessageSink: setMessageSink,
    commitEdit: commitEdit,
    runSilent: runSilent,
    addText: addText,
    addImageFromFile: addImageFromFile,
    insertElement: insertElement,
    deleteSelection: deleteSelection,
    duplicateActive: duplicateActive,
    clearSelection: clearSelection,
    renameObjectById: renameObjectById,
    setObjectVisibleById: setObjectVisibleById,
    setObjectLockedById: setObjectLockedById,
    selectObjectById: selectObjectById,
    findObjectByBlytzId: findObjectByBlytzId,
    isObjectLocked: isObjectLocked,
    selectionHasLockedMembers: selectionHasLockedMembers,
    normalizeLayerName: normalizeLayerName,
    applyLockInteraction: applyLockInteraction,
    applyLockStateToCanvas: applyLockStateToCanvas,
    alignActive: alignActive,
    distributeActive: distributeActive,
    centerOnCanvas: centerOnCanvas,
    fitActiveWithinCanvas: fitActiveWithinCanvas,
    resetActiveRotation: resetActiveRotation,
    replaceActiveImageSrc: replaceActiveImageSrc,
    centerActiveImage: centerActiveImage,
    flipActive: flipActive,
    autoLayoutActive: autoLayoutActive,
    canAutoLayout: canAutoLayout,
    planAutoLayout: planAutoLayout,
    deriveAutoLayoutSlots: deriveAutoLayoutSlots,
    autoLayoutScaleToFit: autoLayoutScaleToFit,
    autoLayoutClampCenter: autoLayoutClampCenter,
    pickPrimaryPrintPanel: pickPrimaryPrintPanel,
    aabbDeltaAlign: aabbDeltaAlign,
    unionAabb: unionAabb,
    distributeAabbDeltas: distributeAabbDeltas,
    reorderActive: reorderActive,
    canReorderActive: canReorderActive,
    prefersSheetTextEdit: prefersSheetTextEdit,
    undo: undo,
    redo: redo,
    canUndo: canUndo,
    canRedo: canRedo,
    seedHistory: seedHistory,
    onHistoryChange: onHistoryChange,
    assignBlytzName: assignBlytzName,
    forceBlytzId: forceBlytzId,
    duplicateLayerName: duplicateLayerName,
    typeKey: typeKey,
    isActiveSelection: isActiveSelection,
    triggerImagePicker: triggerImagePicker,
    nextInsertCenter: nextInsertCenter,
    getLastLoadError: function () {
      return lastLoadError;
    },
    wireTools: wireTools,
    getFabricCanvas: function () {
      return fabricCanvas;
    },
    getMultiSelectMode: function () {
      return multiSelectMode;
    },
    setMultiSelectMode: setMultiSelectMode,
    /**
     * Capture a PNG data-URL of a view.
     * @param {{view?: string, includeGarment?: boolean}|undefined} opts
     * @returns {string|Promise<string>}
     */
    getPreviewPNG: getPreviewPNG,
    renderFrozenPreview: renderFrozenPreview,
  };

  var PREVIEW_MAX_BYTES = 5 * 1024 * 1024;

  function artworkDataURL() {
    if (!fabricCanvas) {
      return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
    }
    // Drop handles for a clean raster, then restore selection so Stage H
    // presentation previews do not clear the user's active object.
    var prior = fabricCanvas.getActiveObject();
    fabricCanvas.discardActiveObject();
    fabricCanvas.requestRenderAll();
    var url = fabricCanvas.toDataURL({
      format: "png",
      multiplier: 1,
      enableRetinaScaling: false,
    });
    if (prior) {
      try {
        fabricCanvas.setActiveObject(prior);
        fabricCanvas.requestRenderAll();
      } catch (err) {
        /* object may have been removed during an overlapping edit */
      }
    }
    return url;
  }

  /** Fabric payload for a view without switching the live canvas. */
  function fabricPayloadForView(viewId) {
    var id = viewId === "back" ? "back" : "front";
    if (id === activeView) {
      return snapshotLiveCanvas();
    }
    if (id === "front") {
      return viewStore.front
        ? cloneFabricPayload(viewStore.front)
        : emptyFabricCanvasObject();
    }
    return viewStore.back
      ? cloneFabricPayload(viewStore.back)
      : emptyFabricCanvasObject();
  }

  /**
   * Render a Fabric payload to a PNG data-URL on an offscreen StaticCanvas.
   * Does not mutate the live editor canvas or fire commits.
   * @param {object} payload
   * @param {{enforceObjectCount?: boolean}|undefined} opts
   */
  function artworkDataURLFromPayload(payload, opts) {
    opts = opts || {};
    return new Promise(function (resolve, reject) {
      var fabric = fabricNS();
      if (!fabric || typeof fabric.StaticCanvas !== "function") {
        reject(new Error("Fabric StaticCanvas is not available."));
        return;
      }
      var source = payload || emptyFabricCanvasObject();
      var expectedCount = Array.isArray(source.objects) ? source.objects.length : 0;
      var el = document.createElement("canvas");
      el.width = LOGICAL_SIZE;
      el.height = LOGICAL_SIZE;
      var sc = new fabric.StaticCanvas(el, {
        width: LOGICAL_SIZE,
        height: LOGICAL_SIZE,
        enableRetinaScaling: false,
        renderOnAddRemove: false,
      });
      var disposed = false;
      function disposeOnce() {
        if (disposed) return;
        disposed = true;
        try {
          sc.dispose();
        } catch (disposeErr) {
          /* ignore */
        }
      }
      sc.loadFromJSON(source)
        .then(function () {
          if (opts.enforceObjectCount) {
            var actual =
              sc.getObjects && typeof sc.getObjects === "function"
                ? sc.getObjects().length
                : 0;
            if (actual !== expectedCount) {
              disposeOnce();
              reject(new Error("Preview could not render every design object."));
              return;
            }
          }
          sc.backgroundColor = "";
          if (typeof sc.setBackgroundColor === "function") {
            try {
              sc.setBackgroundColor("");
            } catch (err) {
              sc.backgroundColor = "";
            }
          }
          sc.requestRenderAll();
          var url;
          try {
            url = sc.toDataURL({
              format: "png",
              multiplier: 1,
              enableRetinaScaling: false,
            });
          } catch (renderErr) {
            disposeOnce();
            reject(renderErr || new Error("Could not render artwork for preview."));
            return;
          }
          disposeOnce();
          resolve(url);
        })
        .catch(function (err) {
          disposeOnce();
          reject(err || new Error("Could not render artwork for preview."));
        });
    });
  }

  /** Front (`canvas`) or back (`views.back`) from a frozen envelope. No live-canvas read. */
  function fabricPayloadFromEnvelope(envelope, viewId) {
    var id = viewId === "back" ? "back" : "front";
    var payload = null;
    if (!envelope || typeof envelope !== "object") return null;
    if (id === "front") {
      payload = envelope.canvas;
    } else if (envelope.views && typeof envelope.views === "object") {
      payload = envelope.views.back;
    }
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.objects)) {
      return null;
    }
    return cloneFabricPayload(payload);
  }

  /**
   * Garment + artwork PNG for one view, rendered only from the given envelope
   * and garment snapshot. Does not read or mutate the live editor.
   * @param {{envelope: object, view: string, garment?: {template?: string, color?: string}}} opts
   * @returns {Promise<string>}
   */
  function renderFrozenPreview(opts) {
    opts = opts || {};
    var viewId = String(opts.view || "").toLowerCase();
    if (viewId !== "front" && viewId !== "back") {
      return Promise.reject(new Error("Unknown preview view."));
    }
    var payload = fabricPayloadFromEnvelope(opts.envelope, viewId);
    if (!payload) {
      return Promise.reject(new Error("Could not create preview. Please try again."));
    }
    var garment = opts.garment || {};
    var template = String(garment.template || "tee");
    var color = String(garment.color || "white");

    function compositeOnce(exportOpts) {
      var gApi = global.BlytzGarments;
      if (!gApi || typeof gApi.getExportLayerMarkups !== "function") {
        return Promise.reject(new Error("Garment export helpers are not available."));
      }
      // Clone again: Fabric loadFromJSON may mutate the object it is given.
      var frozen = cloneFabricPayload(payload);
      return Promise.all([
        gApi.getExportLayerMarkups(template, color, viewId, exportOpts || {}),
        artworkDataURLFromPayload(frozen, { enforceObjectCount: true }),
      ]).then(function (parts) {
        var layers = parts[0];
        var art = parts[1];
        return compositeUnderArtOver(layers.under, art, layers.over);
      });
    }

    return compositeOnce({}).then(function (url) {
      if (dataUrlByteLength(url) <= PREVIEW_MAX_BYTES) {
        return url;
      }
      return compositeOnce({ stripGrain: true }).then(function (retryUrl) {
        if (dataUrlByteLength(retryUrl) > PREVIEW_MAX_BYTES) {
          throw new Error("Preview PNG exceeds the 5 MB upload limit.");
        }
        return retryUrl;
      });
    });
  }

  function artworkDataURLForView(viewId) {
    var id = viewId === "back" ? "back" : "front";
    if (id === activeView && fabricCanvas) {
      return Promise.resolve(artworkDataURL());
    }
    return artworkDataURLFromPayload(fabricPayloadForView(id));
  }

  function dataUrlByteLength(dataUrl) {
    if (!dataUrl || typeof dataUrl !== "string") return 0;
    var comma = dataUrl.indexOf(",");
    var b64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
    return Math.floor((b64.length * 3) / 4);
  }

  function loadImageFromUrl(url, errorMessage) {
    return new Promise(function (resolve, reject) {
      if (!url) {
        resolve(null);
        return;
      }
      var img = new Image();
      img.onload = function () {
        var finish = function () {
          resolve(img);
        };
        if (typeof img.decode === "function") {
          img.decode().then(finish).catch(finish);
        } else {
          finish();
        }
      };
      img.onerror = function () {
        reject(new Error(errorMessage || "Could not load image for preview."));
      };
      img.src = url;
    });
  }

  function svgMarkupToImage(markup, size) {
    if (!markup) return Promise.resolve(null);
    var svgUrl =
      "data:image/svg+xml;charset=utf-8," + encodeURIComponent(markup);
    return loadImageFromUrl(svgUrl, "Could not load garment for preview.").then(
      function (img) {
        if (img && size) {
          /* natural size comes from SVG width/height; draw uses size */
        }
        return img;
      }
    );
  }

  /**
   * Composite UNDER garment + artwork + OVER garment into an 800×800 PNG.
   * Print-area guides are never included (export markups omit them).
   */
  function compositeUnderArtOver(underMarkup, artworkUrl, overMarkup) {
    var size = LOGICAL_SIZE;
    var out = document.createElement("canvas");
    out.width = size;
    out.height = size;
    var ctx = out.getContext("2d");
    if (!ctx) {
      return Promise.reject(new Error("Could not create preview canvas."));
    }
    ctx.fillStyle = "#FFFFFF";
    ctx.fillRect(0, 0, size, size);

    return Promise.all([
      svgMarkupToImage(underMarkup, size),
      loadImageFromUrl(artworkUrl, "Could not load artwork for preview."),
      svgMarkupToImage(overMarkup, size),
    ]).then(function (imgs) {
      var underImg = imgs[0];
      var artImg = imgs[1];
      var overImg = imgs[2];
      if (underImg) ctx.drawImage(underImg, 0, 0, size, size);
      if (artImg) ctx.drawImage(artImg, 0, 0, size, size);
      if (overImg) ctx.drawImage(overImg, 0, 0, size, size);
      return out.toDataURL("image/png");
    });
  }

  function compositeGarmentPreview(viewId, exportOpts) {
    var gApi = global.BlytzGarments;
    if (!gApi || typeof gApi.getExportLayerMarkups !== "function") {
      return Promise.reject(new Error("Garment export helpers are not available."));
    }
    var state = garmentState || { template: "tee", color: "white" };
    return Promise.all([
      gApi.getExportLayerMarkups(
        state.template,
        state.color,
        viewId,
        exportOpts || {}
      ),
      artworkDataURLForView(viewId),
    ]).then(function (parts) {
      var layers = parts[0];
      var art = parts[1];
      return compositeUnderArtOver(layers.under, art, layers.over);
    });
  }

  /**
   * Capture a PNG data-URL of a view.
   * @param {{view?: string, includeGarment?: boolean}|undefined} opts
   * @returns {string|Promise<string>}
   */
  function getPreviewPNG(opts) {
    opts = opts || {};
    var includeGarment = !!opts.includeGarment;
    var targetView = opts.view;
    if (targetView != null && targetView !== "") {
      targetView = String(targetView).toLowerCase();
      if (targetView !== "front" && targetView !== "back") {
        return Promise.reject(new Error("Unknown preview view."));
      }
    } else {
      targetView = activeView;
    }

    // Legacy sync path: active view, artwork only.
    if (!includeGarment && targetView === activeView) {
      return artworkDataURL();
    }

    if (!fabricCanvas && includeGarment) {
      return Promise.reject(new Error("Editor is not ready."));
    }

    if (!includeGarment) {
      // Inactive view, artwork only — offscreen render, no live switch / commits.
      return artworkDataURLForView(targetView);
    }

    // Garment composite: UNDER → artwork → OVER. Never switches live view.
    return compositeGarmentPreview(targetView, {}).then(function (url) {
      if (dataUrlByteLength(url) <= PREVIEW_MAX_BYTES) {
        return url;
      }
      // Grain noise can inflate PNG size — strip grain and retry once (export only).
      return compositeGarmentPreview(targetView, { stripGrain: true }).then(
        function (retryUrl) {
          if (dataUrlByteLength(retryUrl) > PREVIEW_MAX_BYTES) {
            throw new Error("Preview PNG exceeds the 5 MB upload limit.");
          }
          return retryUrl;
        }
      );
    });
  }

  global.BlytzCanvas = api;
})(window);
