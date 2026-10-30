/**
 * Stage 3b — shared editor tool panels (Upload, Elements) + shape/graphics factories.
 * Canvas mutations go through BlytzCanvas.commitEdit / insertElement / addImageFromFile.
 */
(function (global) {
  "use strict";

  var openPanelId = null;
  var lastTrigger = null;
  var wired = false;

  /** Local graphics: each is one Polygon or Path (never a Group). No SVG parsing. */
  var GRAPHICS_DEFS = {
    // 5-point star: alternating outer/inner radii around origin.
    star: {
      label: "Star",
      kind: "polygon",
      build: function (R) {
        var outer = R * 0.5;
        var inner = outer * 0.4;
        var pts = [];
        for (var i = 0; i < 10; i++) {
          var rad = i % 2 === 0 ? outer : inner;
          var a = -Math.PI / 2 + (i * Math.PI) / 5;
          pts.push({ x: Math.cos(a) * rad, y: Math.sin(a) * rad });
        }
        return pts;
      },
    },
    // Right arrow: shaft + head as one polygon.
    arrow: {
      label: "Arrow",
      kind: "polygon",
      build: function (R) {
        var w = R * 0.5;
        var h = R * 0.28;
        return [
          { x: -w, y: -h * 0.35 },
          { x: w * 0.15, y: -h * 0.35 },
          { x: w * 0.15, y: -h },
          { x: w, y: 0 },
          { x: w * 0.15, y: h },
          { x: w * 0.15, y: h * 0.35 },
          { x: -w, y: h * 0.35 },
        ];
      },
    },
    // Shield / badge silhouette.
    badge: {
      label: "Badge",
      kind: "polygon",
      build: function (R) {
        var w = R * 0.4;
        var h = R * 0.5;
        return [
          { x: -w, y: -h * 0.7 },
          { x: w, y: -h * 0.7 },
          { x: w, y: h * 0.15 },
          { x: 0, y: h },
          { x: -w, y: h * 0.15 },
        ];
      },
    },
    // Heart as a single Path (cubic beziers). Scale so max edge ≈ 190 at R=200.
    heart: {
      label: "Heart",
      kind: "path",
      build: function (R) {
        var s = R * 0.0175;
        return (
          "M " +
          0 +
          " " +
          12 * s +
          " C " +
          -20 * s +
          " " +
          -2 * s +
          ", " +
          -40 * s +
          " " +
          -28 * s +
          ", " +
          0 +
          " " +
          -42 * s +
          " C " +
          40 * s +
          " " +
          -28 * s +
          ", " +
          20 * s +
          " " +
          -2 * s +
          ", " +
          0 +
          " " +
          12 * s +
          " Z"
        );
      },
    },
    // Lightning bolt polygon (single closed outline).
    lightning: {
      label: "Lightning",
      kind: "polygon",
      build: function (R) {
        var s = R * 0.5;
        return [
          { x: 0.15 * s, y: -s },
          { x: -0.35 * s, y: -0.05 * s },
          { x: -0.05 * s, y: -0.05 * s },
          { x: -0.2 * s, y: s },
          { x: 0.4 * s, y: 0.05 * s },
          { x: 0.1 * s, y: 0.05 * s },
        ];
      },
    },
    // Starburst: 16-point spike star.
    starburst: {
      label: "Starburst",
      kind: "polygon",
      build: function (R) {
        var outer = R * 0.5;
        var inner = outer * 0.35;
        var spikes = 8;
        var pts = [];
        for (var i = 0; i < spikes * 2; i++) {
          var rad = i % 2 === 0 ? outer : inner;
          var a = -Math.PI / 2 + (i * Math.PI) / spikes;
          pts.push({ x: Math.cos(a) * rad, y: Math.sin(a) * rad });
        }
        return pts;
      },
    },
  };

  function api() {
    return global.BlytzCanvas;
  }

  function isMobilePanel() {
    return window.matchMedia && window.matchMedia("(max-width: 1023px)").matches;
  }

  function panelEl() {
    return document.getElementById("editor-tool-panel");
  }

  function panelBody() {
    return document.querySelector("[data-panel-body]");
  }

  function panelTitle() {
    return document.getElementById("editor-tool-panel-title");
  }

  function panelFeedback() {
    return document.querySelector("[data-panel-feedback]");
  }

  function setPanelFeedback(msg) {
    var el = panelFeedback();
    if (el) el.textContent = msg || "";
  }

  function toolbarBtn(action) {
    return document.querySelector(
      '#editor-toolbar [data-editor-action="' + action + '"]'
    );
  }

  function panelIdForAction(action) {
    if (action === "garment") return "garment";
    if (action === "add-image") return "upload";
    if (action === "elements") return "elements";
    if (action === "layers") return "layers";
    return null;
  }

  var GARMENT_VIEW_BLOCK_TITLE =
    "Choose an AI suggestion or edit the design first";

  function garmentsApi() {
    return global.BlytzGarments;
  }

  function garmentColorsForPanel() {
    var g = garmentsApi();
    if (!g || !g.GARMENT_COLORS) return [];
    var out = [];
    g.GARMENT_COLORS.forEach(function (c) {
      if (c.id === "grey") return;
      out.push(c);
    });
    return out;
  }

  function garmentSummaryLabel(state) {
    state = state || {};
    var g = garmentsApi();
    var template = state.template || "tee";
    var colorId = state.color || "white";
    var typeLabel = template;
    var colorLabel = colorId;
    if (g) {
      var gt = g.garmentById && g.garmentById(template);
      if (gt && gt.label) typeLabel = gt.label;
      var col = g.colorById && g.colorById(colorId);
      if (col && col.label) colorLabel = col.label;
    }
    return typeLabel + ", " + colorLabel;
  }

  function updateGarmentSummary() {
    var el = document.getElementById("editor-garment-summary");
    if (!el || !global.BlytzEditor || !global.BlytzEditor.getGarmentState) return;
    el.textContent = garmentSummaryLabel(global.BlytzEditor.getGarmentState());
  }

  function syncGarmentPanelLive(body) {
    if (!body) body = panelBody();
    if (!body) return;
    var live = body.querySelector("[data-garment-panel-live]");
    if (!live || !global.BlytzEditor || !global.BlytzEditor.getGarmentState) return;
    live.textContent = garmentSummaryLabel(global.BlytzEditor.getGarmentState());
  }

  function syncGarmentPanelPressed(body) {
    if (!body) body = panelBody();
    if (!body || !global.BlytzEditor || !global.BlytzEditor.getGarmentState) return;
    var state = global.BlytzEditor.getGarmentState();
    body.querySelectorAll("[data-garment-type]").forEach(function (btn) {
      var id = btn.getAttribute("data-garment-type");
      var on = id === state.template;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    body.querySelectorAll("[data-garment-color]").forEach(function (btn) {
      var id = btn.getAttribute("data-garment-color");
      var on = id === state.color;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function viewSwitchBlocked() {
    var a = api();
    var canvasPending =
      a && typeof a.aiCandidatesPending === "function" && a.aiCandidatesPending();
    var chatPending =
      global.BlytzAIChat &&
      typeof global.BlytzAIChat.hasPendingCandidates === "function" &&
      global.BlytzAIChat.hasPendingCandidates();
    return !!(canvasPending || chatPending);
  }

  function refreshViewToggle() {
    // Toolbar toggle + always-visible Front/Back overlay group.
    var active =
      global.BlytzEditor && global.BlytzEditor.getActiveView
        ? global.BlytzEditor.getActiveView()
        : "front";
    var blocked = viewSwitchBlocked();
    var label = active === "back" ? "Back" : "Front";
    var btn = document.getElementById("editor-view-toggle-btn");
    if (btn) {
      var icon = btn.querySelector("[data-view-toggle-icon]");
      var text = btn.querySelector("[data-view-toggle-label]");
      if (icon) icon.textContent = active === "back" ? "B" : "F";
      if (text) text.textContent = label;
      btn.setAttribute("aria-label", "Garment view: " + label);
      btn.setAttribute("aria-pressed", "true");
      if (blocked) {
        btn.setAttribute("aria-disabled", "true");
        btn.removeAttribute("title");
        btn.setAttribute("aria-description", GARMENT_VIEW_BLOCK_TITLE);
      } else {
        btn.removeAttribute("aria-disabled");
        btn.removeAttribute("title");
        btn.removeAttribute("aria-description");
      }
    }
    document.querySelectorAll("[data-editor-view]").forEach(function (el) {
      var on = el.getAttribute("data-editor-view") === active;
      el.setAttribute("aria-pressed", on ? "true" : "false");
      if (blocked) {
        el.setAttribute("aria-disabled", "true");
        el.disabled = true;
      } else {
        el.removeAttribute("aria-disabled");
        el.disabled = false;
      }
    });
  }

  function renderTextBody(body) {
    var api = global.BlytzCanvas;
    var canvas = api && api.getFabricCanvas && api.getFabricCanvas();
    var active = canvas && canvas.getActiveObject && canvas.getActiveObject();
    var isText =
      active &&
      api.typeKey &&
      (api.typeKey(active) === "itext" ||
        api.typeKey(active) === "text" ||
        api.typeKey(active) === "textbox");
    var value = isText ? active.text || "" : "";
    body.innerHTML =
      '<p class="editor-panel-lead">Edit text here so the on-screen keyboard does not cover the canvas.</p>' +
      '<label class="editor-props-label" for="editor-text-sheet-input">Text</label>' +
      '<textarea id="editor-text-sheet-input" class="editor-props-textarea" data-text-sheet-input rows="3" maxlength="200">' +
      String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;") +
      "</textarea>" +
      '<button type="button" class="editor-panel-primary" data-text-sheet-apply style="margin-top:0.75rem">' +
      (isText ? "Update text" : "Add text") +
      "</button>";
    var input = body.querySelector("[data-text-sheet-input]");
    if (input) {
      setTimeout(function () {
        input.focus();
        if (global.BlytzEditorChrome && BlytzEditorChrome.applyVisualViewportOffset) {
          BlytzEditorChrome.applyVisualViewportOffset();
        }
      }, 50);
    }
  }

  function buildGarmentTypeThumb(garmentId) {
    var g = garmentsApi();
    var url =
      g && typeof g.thumbUrl === "function" ? g.thumbUrl(garmentId) : null;
    if (!url) return null;
    var img = document.createElement("img");
    img.className = "editor-garment-thumb";
    img.src = url;
    img.alt = "";
    img.setAttribute("aria-hidden", "true");
    img.draggable = false;
    return img;
  }

  function renderGarmentBody(body) {
    while (body.firstChild) body.removeChild(body.firstChild);
    var g = garmentsApi();
    if (!g) {
      var err = document.createElement("p");
      err.className = "editor-panel-lead";
      err.textContent = "Garment options are not available.";
      body.appendChild(err);
      return;
    }

    var heading = document.createElement("h3");
    heading.className = "editor-panel-h";
    heading.textContent = "Type";
    body.appendChild(heading);

    var types = document.createElement("div");
    types.className = "editor-garment-types";
    types.setAttribute("role", "group");
    types.setAttribute("aria-label", "Garment type");
    (g.GARMENT_TYPES || []).forEach(function (gt) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "editor-garment-type-btn";
      btn.setAttribute("data-garment-type", gt.id);
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-label", gt.label);
      var thumb = buildGarmentTypeThumb(gt.id);
      if (thumb) btn.appendChild(thumb);
      var lab = document.createElement("span");
      lab.textContent = gt.label;
      btn.appendChild(lab);
      types.appendChild(btn);
    });
    body.appendChild(types);

    var colorHeading = document.createElement("h3");
    colorHeading.className = "editor-panel-h";
    colorHeading.style.marginTop = "1rem";
    colorHeading.textContent = "Color";
    body.appendChild(colorHeading);

    var swatches = document.createElement("div");
    swatches.className = "editor-garment-swatches";
    swatches.setAttribute("role", "group");
    swatches.setAttribute("aria-label", "Garment color");
    garmentColorsForPanel().forEach(function (c) {
      var sw = document.createElement("button");
      sw.type = "button";
      sw.className = "editor-garment-swatch";
      sw.setAttribute("data-garment-color", c.id);
      sw.setAttribute("aria-pressed", "false");
      sw.setAttribute("aria-label", c.label);
      sw.style.backgroundColor = c.hex;
      swatches.appendChild(sw);
    });
    body.appendChild(swatches);

    var live = document.createElement("p");
    live.className = "editor-garment-live";
    live.setAttribute("data-garment-panel-live", "");
    live.setAttribute("aria-live", "polite");
    body.appendChild(live);

    syncGarmentPanelPressed(body);
    syncGarmentPanelLive(body);
  }

  function syncExpanded() {
    ["garment", "add-image", "elements", "layers"].forEach(function (action) {
      var btn = toolbarBtn(action);
      if (!btn) return;
      var expanded = openPanelId === panelIdForAction(action);
      btn.setAttribute("aria-expanded", expanded ? "true" : "false");
      btn.classList.toggle("is-active", expanded);
    });
  }

  function closePanel() {
    var panel = panelEl();
    if (!panel) return;
    panel.hidden = true;
    panel.classList.remove("is-open");
    openPanelId = null;
    syncExpanded();
    if (api()) api().setMessageSink(null);
    setPanelFeedback("");
    if (lastTrigger && typeof lastTrigger.focus === "function") {
      try {
        lastTrigger.focus();
      } catch (err) {
        /* ignore */
      }
    }
    lastTrigger = null;
  }

  function objectTypeKey(obj) {
    var a = api();
    if (a && typeof a.typeKey === "function") return a.typeKey(obj);
    return String((obj && obj.type) || "")
      .toLowerCase()
      .replace(/[^a-z]/g, "");
  }

  function typeGlyph(obj) {
    var t = objectTypeKey(obj);
    if (t === "itext" || t === "text" || t === "textbox") return "T";
    if (t === "image") return "▣";
    if (t === "line") return "／";
    if (t === "ellipse" || t === "circle") return "◯";
    if (t === "rect") return "▭";
    if (t === "path") return "∿";
    if (t === "polygon") return "◇";
    return "•";
  }

  function typeFallbackLabel(obj) {
    var t = objectTypeKey(obj);
    if (t === "itext" || t === "text" || t === "textbox") return "Text";
    if (t === "image") return "Image";
    if (t === "line") return "Line";
    if (t === "ellipse") return "Ellipse";
    if (t === "circle") return "Circle";
    if (t === "rect") return "Rectangle";
    if (t === "path") return "Path";
    if (t === "polygon") return "Polygon";
    return "Object";
  }

  /**
   * Layer row label: prefer custom blytzName; for default "Text" show live text;
   * else type fallback. Truncate for the list.
   */
  function layerLabel(obj) {
    var t = objectTypeKey(obj);
    var name =
      obj && typeof obj.blytzName === "string" ? obj.blytzName.trim() : "";
    if (name) {
      var isDefaultTextName =
        (t === "itext" || t === "text" || t === "textbox") && name === "Text";
      if (isDefaultTextName) {
        var text = obj && typeof obj.text === "string" ? obj.text : "";
        if (text.length > 20) return text.slice(0, 20) + "…";
        return text || "Text";
      }
      if (name.length > 20) return name.slice(0, 20) + "…";
      return name;
    }
    if (t === "itext" || t === "text" || t === "textbox") {
      var fallbackText = obj && typeof obj.text === "string" ? obj.text : "";
      if (fallbackText.length > 20) return fallbackText.slice(0, 20) + "…";
      return fallbackText || "Text";
    }
    return typeFallbackLabel(obj);
  }

  function layerNameMax() {
    var a = api();
    var L = a && a.PROP_LIMITS;
    return L && L.layerNameMax != null ? L.layerNameMax : 60;
  }

  function renderLayerRow(obj, selectedIds) {
    var row = document.createElement("div");
    row.className = "editor-layer-row";
    row.setAttribute("data-layer-id", obj.blytzId || "");
    row.setAttribute("role", "listitem");
    var pressed = !!(obj.blytzId && selectedIds[obj.blytzId]);
    row.setAttribute("aria-selected", pressed ? "true" : "false");
    if (pressed) row.classList.add("is-selected");
    if (obj && obj.visible === false) row.classList.add("is-hidden");
    if (obj && obj.blytzLocked) row.classList.add("is-locked");

    var selectBtn = document.createElement("button");
    selectBtn.type = "button";
    selectBtn.className = "editor-layer-select";
    selectBtn.setAttribute("data-layer-select", "1");
    selectBtn.setAttribute("aria-pressed", pressed ? "true" : "false");
    selectBtn.setAttribute(
      "aria-label",
      "Select layer " + layerLabel(obj)
    );

    var glyph = document.createElement("span");
    glyph.className = "editor-layer-glyph";
    glyph.setAttribute("aria-hidden", "true");
    glyph.textContent = typeGlyph(obj);

    var lab = document.createElement("span");
    lab.className = "editor-layer-label";
    lab.setAttribute("data-layer-label", "1");
    lab.textContent = layerLabel(obj);

    selectBtn.appendChild(glyph);
    selectBtn.appendChild(lab);

    var actions = document.createElement("div");
    actions.className = "editor-layer-row-actions";
    actions.setAttribute("role", "group");
    actions.setAttribute("aria-label", "Layer actions for " + layerLabel(obj));

    function iconBtn(action, label, pressedState, text) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "editor-layer-icon-btn";
      b.setAttribute("data-layer-row-action", action);
      b.setAttribute("aria-label", label);
      b.title = label;
      if (pressedState != null) {
        b.setAttribute("aria-pressed", pressedState ? "true" : "false");
        if (pressedState) b.classList.add("is-active");
      }
      b.textContent = text;
      return b;
    }

    var hidden = !!(obj && obj.visible === false);
    var locked = !!(obj && obj.blytzLocked);
    actions.appendChild(
      iconBtn(
        "visibility",
        hidden ? "Show layer" : "Hide layer",
        !hidden,
        hidden ? "○" : "◉"
      )
    );
    actions.appendChild(
      iconBtn(
        "lock",
        locked ? "Unlock layer" : "Lock layer",
        locked,
        locked ? "▣" : "□"
      )
    );
    actions.appendChild(iconBtn("rename", "Rename layer", null, "✎"));
    actions.appendChild(iconBtn("duplicate", "Duplicate layer", null, "⧉"));

    row.appendChild(selectBtn);
    row.appendChild(actions);
    return row;
  }

  function beginLayerRename(row, obj) {
    if (!row || !obj || !obj.blytzId) return;
    if (row.querySelector("[data-layer-rename-input]")) return;
    var lab = row.querySelector("[data-layer-label]");
    var selectBtn = row.querySelector("[data-layer-select]");
    if (!lab || !selectBtn) return;
    var prior = typeof obj.blytzName === "string" ? obj.blytzName : layerLabel(obj);
    var input = document.createElement("input");
    input.type = "text";
    input.className = "editor-layer-rename-input";
    input.setAttribute("data-layer-rename-input", "1");
    input.setAttribute("aria-label", "Rename layer");
    input.maxLength = layerNameMax();
    input.value = prior;
    lab.hidden = true;
    selectBtn.appendChild(input);
    input.focus();
    input.select();

    var finished = false;
    function cleanup() {
      if (finished) return;
      finished = true;
      if (input.parentNode) input.parentNode.removeChild(input);
      lab.hidden = false;
    }
    function confirm() {
      if (finished) return;
      var a = api();
      var id = obj.blytzId;
      var raw = input.value;
      cleanup();
      if (a && a.renameObjectById) {
        a.renameObjectById(id, raw, getJSON);
      }
      // Refresh even on reject (empty name) so the label returns.
      refreshLayers();
    }
    function cancel() {
      cleanup();
      refreshLayers();
    }
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        confirm();
      } else if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        cancel();
      }
    });
    input.addEventListener("blur", function () {
      // Blur after Enter/Escape already finished — ignore.
      if (finished) return;
      confirm();
    });
  }

  function selectedIdMap() {
    var map = Object.create(null);
    var c = api() && api().getFabricCanvas();
    if (!c) return map;
    var active = c.getActiveObjects ? c.getActiveObjects() : [];
    (active || []).forEach(function (o) {
      if (o && o.blytzId) map[o.blytzId] = true;
    });
    return map;
  }

  function getJSON() {
    return global.BlytzEditor && global.BlytzEditor.getCanvasJSON();
  }

  function renderLayersBody(body) {
    while (body.firstChild) body.removeChild(body.firstChild);

    var toolbar = document.createElement("div");
    toolbar.className = "editor-layers-toolbar";
    toolbar.setAttribute("role", "toolbar");
    toolbar.setAttribute("aria-label", "Layer order");

    function layerActionBtn(action, label) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "editor-layers-action";
      b.setAttribute("data-layer-action", action);
      b.setAttribute("aria-label", label);
      b.title = label;
      b.textContent = label;
      return b;
    }

    toolbar.appendChild(layerActionBtn("front", "Bring to Front"));
    toolbar.appendChild(layerActionBtn("forward", "Bring Forward"));
    toolbar.appendChild(layerActionBtn("backward", "Send Backward"));
    toolbar.appendChild(layerActionBtn("back", "Send to Back"));
    toolbar.appendChild(layerActionBtn("duplicate", "Duplicate"));
    toolbar.appendChild(layerActionBtn("delete", "Delete"));
    body.appendChild(toolbar);

    var list = document.createElement("div");
    list.className = "editor-layers-list";
    list.setAttribute("data-layers-list", "");
    list.setAttribute("role", "list");
    body.appendChild(list);
    fillLayersList(list);
    syncLayerActionState(toolbar);
  }

  function fillLayersList(list) {
    if (!list) list = document.querySelector("[data-layers-list]");
    if (!list) return;
    var t0 =
      typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
    while (list.firstChild) list.removeChild(list.firstChild);
    var c = api() && api().getFabricCanvas();
    var objects = c ? c.getObjects().slice() : [];
    // FRONTMOST at the TOP — reverse Fabric bottom→top order.
    objects.reverse();
    var selected = selectedIdMap();
    if (!objects.length) {
      var empty = document.createElement("p");
      empty.className = "editor-layers-empty";
      empty.textContent = "No layers yet.";
      list.appendChild(empty);
    } else {
      objects.forEach(function (obj) {
        list.appendChild(renderLayerRow(obj, selected));
      });
    }
    var t1 =
      typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
    list.setAttribute("data-render-ms", String(Math.round((t1 - t0) * 100) / 100));
  }

  function syncAutoLayoutToolbar() {
    var btn = document.querySelector(
      '#editor-toolbar [data-editor-action="auto-layout"]'
    );
    if (!btn || !api()) return;
    var can = !!(api().canAutoLayout && api().canAutoLayout());
    btn.disabled = !can;
    if (can) {
      btn.removeAttribute("aria-disabled");
      btn.title = "Arrange images and text on the print panel (rule-based)";
    } else {
      btn.setAttribute("aria-disabled", "true");
      btn.title = "Add unlocked images or text to use auto layout";
    }
  }

  function syncLayerActionState(toolbar) {
    toolbar = toolbar || document.querySelector(".editor-layers-toolbar");
    if (!toolbar || !api()) return;
    var c = api().getFabricCanvas();
    var active = c && c.getActiveObject();
    var multi = !!(active && api().isActiveSelection(active));
    ["forward", "backward", "front", "back"].forEach(function (action) {
      var btn = toolbar.querySelector('[data-layer-action="' + action + '"]');
      if (!btn) return;
      var can = !multi && api().canReorderActive(action);
      if (multi) {
        btn.setAttribute("aria-disabled", "true");
        btn.disabled = true;
        btn.title = "Reorder is unavailable for multi-selection";
      } else if (!can) {
        btn.setAttribute("aria-disabled", "true");
        btn.disabled = true;
        btn.title = "Already at the edge of the stack";
      } else {
        btn.removeAttribute("aria-disabled");
        btn.disabled = false;
        btn.title = btn.getAttribute("aria-label") || "";
      }
    });
    var dup = toolbar.querySelector('[data-layer-action="duplicate"]');
    if (dup) {
      var canDup = !!(active && !multi);
      dup.disabled = !canDup;
      dup.setAttribute("aria-disabled", canDup ? "false" : "true");
      dup.title = canDup
        ? "Duplicate"
        : multi
          ? "Duplicate is unavailable for multi-selection"
          : "Select one layer to duplicate";
    }
    var del = toolbar.querySelector('[data-layer-action="delete"]');
    if (del) {
      var has = !!(active || (c && c.getActiveObjects && c.getActiveObjects().length));
      del.disabled = !has;
      del.setAttribute("aria-disabled", has ? "false" : "true");
    }
  }

  var layersRaf = 0;
  function refreshLayers() {
    if (openPanelId !== "layers") {
      // Still cheap to skip full render when closed.
      return;
    }
    // Do not rebuild while a rename input is open — selection sync would
    // destroy the input before Enter/Escape/blur can commit or cancel.
    if (document.querySelector("[data-layer-rename-input]")) {
      return;
    }
    if (layersRaf) return;
    layersRaf = requestAnimationFrame(function () {
      layersRaf = 0;
      if (document.querySelector("[data-layer-rename-input]")) {
        return;
      }
      fillLayersList();
      syncLayerActionState();
    });
  }

  function formatInputLimitLabel() {
    var a = api();
    var bytes = a && a.IMAGE_INPUT_LIMIT_BYTES != null ? a.IMAGE_INPUT_LIMIT_BYTES : 8 * 1024 * 1024;
    var target = a && a.IMAGE_TARGET_BYTES != null ? a.IMAGE_TARGET_BYTES : 300 * 1024;
    return {
      inputMb: Math.round(bytes / (1024 * 1024)),
      targetKb: Math.round(target / 1024),
    };
  }

  function renderUploadBody(body) {
    var lim = formatInputLimitLabel();
    body.innerHTML =
      '<p class="editor-panel-lead">Add an image to the canvas. Files are embedded in the design.</p>' +
      '<p class="editor-panel-meta">Accepted: PNG, JPEG, WebP · up to ' +
      lim.inputMb +
      " MB input · stored around " +
      lim.targetKb +
      " KB</p>" +
      '<button type="button" class="editor-panel-primary" data-panel-choose-image>' +
      "Choose image</button>";
  }

  function shapeButton(id, label, mark) {
    return (
      '<button type="button" class="editor-panel-tile" data-insert-shape="' +
      id +
      '" aria-label="' +
      label +
      '">' +
      '<span class="editor-panel-tile-mark" aria-hidden="true">' +
      mark +
      "</span>" +
      '<span class="editor-panel-tile-label">' +
      label +
      "</span></button>"
    );
  }

  function renderElementsBody(body) {
    var html = '<section class="editor-panel-section"><h3 class="editor-panel-h">Basic shapes</h3>';
    html += '<div class="editor-panel-grid">';
    html += shapeButton("rect", "Rectangle", "▭");
    html += shapeButton("ellipse", "Ellipse", "◯");
    html += shapeButton("line", "Line", "／");
    html += "</div></section>";
    html += '<section class="editor-panel-section"><h3 class="editor-panel-h">Graphics</h3>';
    html += '<div class="editor-panel-grid">';
    Object.keys(GRAPHICS_DEFS).forEach(function (key) {
      var def = GRAPHICS_DEFS[key];
      var mark =
        key === "star"
          ? "★"
          : key === "arrow"
            ? "→"
            : key === "badge"
              ? "⛨"
              : key === "heart"
                ? "♥"
                : key === "lightning"
                  ? "⚡"
                  : "✸";
      html += shapeButton(key, def.label, mark);
    });
    html += "</div></section>";
    body.innerHTML = html;
  }

  function openPanel(id, trigger) {
    var panel = panelEl();
    var body = panelBody();
    var title = panelTitle();
    if (!panel || !body || !title) return;
    if (
      global.BlytzEditorProps &&
      typeof global.BlytzEditorProps.onToolPanelOpening === "function"
    ) {
      global.BlytzEditorProps.onToolPanelOpening();
    }
    lastTrigger = trigger || lastTrigger;
    openPanelId = id;
    title.textContent =
      id === "upload"
        ? "Upload image"
        : id === "layers"
          ? "Layers"
          : id === "garment"
            ? "Garment"
            : id === "text"
              ? "Text"
              : "Elements";
    panel.setAttribute("aria-labelledby", "editor-tool-panel-title");
    if (id === "upload") renderUploadBody(body);
    else if (id === "layers") renderLayersBody(body);
    else if (id === "garment") renderGarmentBody(body);
    else if (id === "text") renderTextBody(body);
    else renderElementsBody(body);
    panel.hidden = false;
    panel.classList.add("is-open");
    syncExpanded();
    setPanelFeedback("");
    if (api()) {
      api().setMessageSink(function (msg) {
        setPanelFeedback(msg);
      });
    }
    var closeBtn = panel.querySelector("[data-panel-close]");
    if (closeBtn) closeBtn.focus();
  }

  function togglePanel(id, trigger) {
    if (openPanelId === id) {
      closePanel();
      return;
    }
    openPanel(id, trigger);
  }

  var SHAPE_LAYER_NAMES = {
    rect: "Rectangle",
    ellipse: "Ellipse",
    line: "Line",
    star: "Star",
    arrow: "Arrow",
    badge: "Badge",
    heart: "Heart",
    lightning: "Lightning",
    starburst: "Starburst",
  };

  function fabricObjectFromShape(shapeId, pos) {
    var fabric = global.fabric;
    var a = api();
    if (!fabric || !a) return null;
    var fill =
      typeof a.defaultContrastFill === "function"
        ? a.defaultContrastFill()
        : a.DEFAULT_SHAPE_FILL;
    var R = a.DEFAULT_SHAPE_MAX_EDGE;
    var common = {
      left: pos.left,
      top: pos.top,
      originX: "center",
      originY: "center",
      strokeUniform: true,
    };
    var layerName = SHAPE_LAYER_NAMES[shapeId] || "Shape";
    var obj = null;

    if (shapeId === "rect") {
      obj = new fabric.Rect(
        Object.assign({}, common, {
          width: R * 0.85,
          height: R * 0.65,
          fill: fill,
          strokeWidth: 0,
        })
      );
    } else if (shapeId === "ellipse") {
      obj = new fabric.Ellipse(
        Object.assign({}, common, {
          rx: R * 0.42,
          ry: R * 0.32,
          fill: fill,
          strokeWidth: 0,
        })
      );
    } else if (shapeId === "line") {
      var half = R * 0.45;
      obj = new fabric.Line([-half, 0, half, 0], {
        left: pos.left,
        top: pos.top,
        originX: "center",
        originY: "center",
        stroke: fill,
        strokeWidth: 6,
        fill: "",
        strokeUniform: true,
      });
    } else {
      var def = GRAPHICS_DEFS[shapeId];
      if (!def) return null;
      var geom = def.build(R);
      if (def.kind === "path") {
        obj = new fabric.Path(geom, Object.assign({}, common, { fill: fill, strokeWidth: 0 }));
      } else {
        obj = new fabric.Polygon(
          geom,
          Object.assign({}, common, { fill: fill, strokeWidth: 0 })
        );
      }
    }
    if (obj && a.assignBlytzName) a.assignBlytzName(obj, layerName);
    else if (obj) obj.blytzName = layerName;
    return obj;
  }

  function insertShape(shapeId) {
    var a = api();
    if (!a || !global.BlytzEditor) return;
    var getJSON = function () {
      return global.BlytzEditor.getCanvasJSON();
    };
    var ok = a.insertElement(
      "insert-" + shapeId,
      function (pos) {
        return fabricObjectFromShape(shapeId, pos);
      },
      getJSON,
      SHAPE_LAYER_NAMES[shapeId]
    );
    if (ok) {
      setPanelFeedback("Added " + (GRAPHICS_DEFS[shapeId] ? GRAPHICS_DEFS[shapeId].label : shapeId) + ".");
      onSuccessfulInsert("elements");
    }
  }

  function onSuccessfulInsert(fromPanel) {
    if (isMobilePanel() && openPanelId) {
      closePanel();
    }
  }

  function wire() {
    if (wired) return;
    wired = true;

    document.addEventListener("click", function (e) {
      var choose = e.target.closest("[data-panel-choose-image]");
      if (choose) {
        e.preventDefault();
        if (api()) api().triggerImagePicker();
        return;
      }
      var shapeBtn = e.target.closest("[data-insert-shape]");
      if (shapeBtn) {
        e.preventDefault();
        insertShape(shapeBtn.getAttribute("data-insert-shape"));
        return;
      }
      var close = e.target.closest("[data-panel-close]");
      if (close && panelEl() && panelEl().contains(close)) {
        e.preventDefault();
        closePanel();
        return;
      }
      var viewToggleBtn = e.target.closest(
        '[data-editor-action="toggle-view"], #editor-view-toggle-btn'
      );
      if (viewToggleBtn) {
        e.preventDefault();
        if (viewToggleBtn.getAttribute("aria-disabled") === "true") return;
        if (!global.BlytzEditor || !global.BlytzEditor.setActiveView) return;
        var cur =
          typeof global.BlytzEditor.getActiveView === "function"
            ? global.BlytzEditor.getActiveView()
            : "front";
        var next = cur === "back" ? "front" : "back";
        global.BlytzEditor.setActiveView(next).then(function () {
          refreshViewToggle();
        });
        return;
      }
      var garmentType = e.target.closest("[data-garment-type]");
      if (garmentType && panelEl() && panelEl().contains(garmentType)) {
        e.preventDefault();
        if (!global.BlytzEditor || !global.BlytzEditor.setGarmentState) return;
        global.BlytzEditor.setGarmentState({
          template: garmentType.getAttribute("data-garment-type"),
        });
        syncGarmentPanelPressed();
        syncGarmentPanelLive();
        updateGarmentSummary();
        return;
      }
      var garmentColor = e.target.closest("[data-garment-color]");
      if (garmentColor && panelEl() && panelEl().contains(garmentColor)) {
        e.preventDefault();
        if (!global.BlytzEditor || !global.BlytzEditor.setGarmentState) return;
        global.BlytzEditor.setGarmentState({
          color: garmentColor.getAttribute("data-garment-color"),
        });
        syncGarmentPanelPressed();
        syncGarmentPanelLive();
        updateGarmentSummary();
        return;
      }
      var actionBtn = e.target.closest("#editor-toolbar [data-editor-action]");
      if (!actionBtn || actionBtn.disabled || actionBtn.getAttribute("aria-disabled") === "true") {
        return;
      }
      var action = actionBtn.getAttribute("data-editor-action");
      if (action === "garment") {
        e.preventDefault();
        e.stopPropagation();
        togglePanel("garment", actionBtn);
      } else if (action === "add-image") {
        e.preventDefault();
        e.stopPropagation();
        togglePanel("upload", actionBtn);
      } else if (action === "add-text") {
        var sheetText =
          global.BlytzCanvas &&
          typeof global.BlytzCanvas.prefersSheetTextEdit === "function" &&
          global.BlytzCanvas.prefersSheetTextEdit();
        if (sheetText) {
          e.preventDefault();
          e.stopPropagation();
          togglePanel("text", actionBtn);
        }
      } else if (action === "elements") {
        e.preventDefault();
        e.stopPropagation();
        togglePanel("elements", actionBtn);
      } else if (action === "layers") {
        e.preventDefault();
        e.stopPropagation();
        togglePanel("layers", actionBtn);
      }
    }, true);

    document.addEventListener("click", function (e) {
      var applyText = e.target.closest("[data-text-sheet-apply]");
      if (!applyText || !panelEl() || !panelEl().contains(applyText)) return;
      e.preventDefault();
      var input = panelEl().querySelector("[data-text-sheet-input]");
      var next = input ? String(input.value || "") : "";
      var a = api();
      var getJSON =
        global.BlytzEditor && global.BlytzEditor.getCanvasJSON
          ? function () {
              return global.BlytzEditor.getCanvasJSON();
            }
          : null;
      if (!a) return;
      var canvas = a.getFabricCanvas();
      var active = canvas && canvas.getActiveObject();
      var isText =
        active &&
        a.typeKey &&
        (a.typeKey(active) === "itext" ||
          a.typeKey(active) === "text" ||
          a.typeKey(active) === "textbox");
      if (isText) {
        a.commitEdit(
          "text-sheet",
          function () {
            active.set("text", next || "Your text");
            if (typeof active.initDimensions === "function") active.initDimensions();
            active.setCoords();
            canvas.requestRenderAll();
            return true;
          },
          getJSON
        );
      } else {
        a.addText(getJSON, { text: next || "Your text", skipEditing: true });
      }
      closePanel();
      if (global.BlytzEditorChrome && BlytzEditorChrome.syncContextBar) {
        BlytzEditorChrome.syncContextBar();
      }
    });

    document.addEventListener("click", function (e) {
      if (!panelEl() || !panelEl().contains(e.target)) return;

      var rowAction = e.target.closest("[data-layer-row-action]");
      if (rowAction) {
        e.preventDefault();
        e.stopPropagation();
        var row = rowAction.closest("[data-layer-id]");
        var id = row && row.getAttribute("data-layer-id");
        var a = api();
        if (!a || !id) return;
        var act = rowAction.getAttribute("data-layer-row-action");
        var obj = a.findObjectByBlytzId ? a.findObjectByBlytzId(id) : null;
        if (!obj) return;
        if (act === "visibility") {
          var show = obj.visible === false;
          a.setObjectVisibleById(id, show, getJSON);
          if (show && a.selectObjectById) a.selectObjectById(id);
          refreshLayers();
          if (global.BlytzEditorProps && BlytzEditorProps.syncFromSelection) {
            BlytzEditorProps.syncFromSelection();
          }
          return;
        }
        if (act === "lock") {
          a.setObjectLockedById(id, !obj.blytzLocked, getJSON);
          if (a.selectObjectById) a.selectObjectById(id);
          refreshLayers();
          if (global.BlytzEditorProps && BlytzEditorProps.syncFromSelection) {
            BlytzEditorProps.syncFromSelection();
          }
          return;
        }
        if (act === "rename") {
          if (a.selectObjectById) a.selectObjectById(id);
          beginLayerRename(row, obj);
          return;
        }
        if (act === "duplicate") {
          if (a.selectObjectById) a.selectObjectById(id);
          Promise.resolve(a.duplicateActive(getJSON)).then(function () {
            refreshLayers();
            if (global.BlytzEditorProps && BlytzEditorProps.syncFromSelection) {
              BlytzEditorProps.syncFromSelection();
            }
          });
          return;
        }
        return;
      }

      var selectBtn = e.target.closest("[data-layer-select]");
      var rowEl = e.target.closest("[data-layer-id]");
      if (selectBtn || (rowEl && !e.target.closest("[data-layer-rename-input]"))) {
        if (e.target.closest("[data-layer-rename-input]")) return;
        e.preventDefault();
        var selectId =
          (selectBtn && selectBtn.closest("[data-layer-id]")
            ? selectBtn.closest("[data-layer-id]")
            : rowEl
          ).getAttribute("data-layer-id");
        var canvasApi = api();
        if (!canvasApi || !selectId) return;
        // Management selection — works for locked/hidden via selectObjectById.
        if (canvasApi.selectObjectById) {
          canvasApi.selectObjectById(selectId);
        }
        // Selection only — 0 commits.
        refreshLayers();
        if (global.BlytzEditorProps && BlytzEditorProps.syncFromSelection) {
          BlytzEditorProps.syncFromSelection();
        }
        return;
      }

      var actionBtn = e.target.closest("[data-layer-action]");
      if (actionBtn) {
        e.preventDefault();
        if (actionBtn.disabled || actionBtn.getAttribute("aria-disabled") === "true") {
          return;
        }
        var toolbarAct = actionBtn.getAttribute("data-layer-action");
        var canvas = api();
        if (!canvas) return;
        if (toolbarAct === "delete") {
          canvas.deleteSelection(getJSON);
        } else if (toolbarAct === "duplicate") {
          Promise.resolve(canvas.duplicateActive(getJSON)).then(function () {
            refreshLayers();
          });
          return;
        } else {
          canvas.reorderActive(toolbarAct, getJSON);
        }
        refreshLayers();
      }
    });

    document.addEventListener("dblclick", function (e) {
      if (!panelEl() || !panelEl().contains(e.target)) return;
      var label = e.target.closest("[data-layer-label]");
      var row = e.target.closest("[data-layer-id]");
      if (!label || !row) return;
      e.preventDefault();
      var a = api();
      var id = row.getAttribute("data-layer-id");
      var obj = a && a.findObjectByBlytzId ? a.findObjectByBlytzId(id) : null;
      if (!obj) return;
      if (a.selectObjectById) a.selectObjectById(id);
      beginLayerRename(row, obj);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!openPanelId) return;
      e.preventDefault();
      closePanel();
    });

    // Refresh layers on canvas structural / selection changes.
    var tries = 0;
    (function waitCanvas() {
      var c = api() && api().getFabricCanvas();
      if (!c) {
        if (tries++ < 40) setTimeout(waitCanvas, 50);
        return;
      }
      [
        "object:added",
        "object:removed",
        "selection:created",
        "selection:updated",
        "selection:cleared",
      ].forEach(function (ev) {
        c.on(ev, function () {
          refreshLayers();
          syncAutoLayoutToolbar();
        });
      });
      if (global.BlytzEditor && BlytzEditor.onCommittedChange) {
        BlytzEditor.onCommittedChange(function () {
          refreshLayers();
          syncAutoLayoutToolbar();
        });
      }
      syncAutoLayoutToolbar();
    })();

    function bindGarmentUi() {
      if (!global.BlytzEditor) return false;
      function refreshGarmentChrome() {
        updateGarmentSummary();
        refreshViewToggle();
      }
      if (typeof global.BlytzEditor.whenReady === "function") {
        global.BlytzEditor.whenReady().then(refreshGarmentChrome).catch(refreshGarmentChrome);
      } else {
        refreshGarmentChrome();
      }
      if (typeof global.BlytzEditor.onViewChange === "function") {
        global.BlytzEditor.onViewChange(function () {
          refreshViewToggle();
          syncAutoLayoutToolbar();
        });
      }
      if (typeof global.BlytzEditor.onGarmentChange === "function") {
        global.BlytzEditor.onGarmentChange(function () {
          updateGarmentSummary();
          syncAutoLayoutToolbar();
          if (openPanelId === "garment") {
            syncGarmentPanelPressed();
            syncGarmentPanelLive();
          }
        });
      }
      if (typeof global.BlytzEditor.onCommittedChange === "function") {
        global.BlytzEditor.onCommittedChange(function () {
          refreshViewToggle();
          syncAutoLayoutToolbar();
        });
      }
      syncAutoLayoutToolbar();
      return true;
    }
    var garmentTries = 0;
    (function waitEditorGarment() {
      if (bindGarmentUi()) return;
      if (garmentTries++ < 80) setTimeout(waitEditorGarment, 50);
    })();
  }

  var BlytzEditorTools = {
    GRAPHICS_DEFS: GRAPHICS_DEFS,
    SHAPE_LAYER_NAMES: SHAPE_LAYER_NAMES,
    openPanel: openPanel,
    closePanel: closePanel,
    onSuccessfulInsert: onSuccessfulInsert,
    fabricObjectFromShape: fabricObjectFromShape,
    refreshLayers: refreshLayers,
    layerLabel: layerLabel,
    renderLayerRow: renderLayerRow,
    getOpenPanelId: function () {
      return openPanelId;
    },
  };

  global.BlytzEditorTools = BlytzEditorTools;

  document.addEventListener("DOMContentLoaded", function () {
    wire();
    ["garment", "add-image", "elements", "layers"].forEach(function (action) {
      var btn = toolbarBtn(action);
      if (!btn) return;
      btn.setAttribute("aria-controls", "editor-tool-panel");
      btn.setAttribute("aria-expanded", "false");
      btn.setAttribute("aria-haspopup", "dialog");
    });
  });
})(window);
