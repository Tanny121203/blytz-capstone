/**
 * Blytz Capstone — garment mockups (inline SVG under/over layers + print areas).
 * Vanilla JS; attaches global BlytzGarments (no modules).
 *
 * Assets: static/garments/<id>-<view>.svg + garments.json print areas (800×800).
 * Under = ground + base (below Fabric). Over = details + shade (above Fabric).
 * Art group is omitted — Fabric is the art layer.
 */
(function (global) {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var VIEW_BOX = "0 0 800 800";
  var ASSET_VERSION = "1";
  var STRING_COLOR = "#e9e5da";

  /**
   * Exact CSS variable strings embedded in static/garments/*.svg.
   * Replacement order for PNG export: TRIM first (nested garment fallback),
   * then GARMENT, then STRING. <img> rasterization cannot resolve CSS vars.
   */
  var SVG_VAR_TRIM = "var(--trim, var(--garment, #f2f2ef))";
  var SVG_VAR_GARMENT = "var(--garment, #f2f2ef)";
  var SVG_VAR_STRING = "var(--string, #e9e5da)";

  /**
   * Grain rect opacity in source SVGs is typically ".10". Export lowers this
   * so feTurbulence noise does not push preview PNGs over the 5 MB submit cap.
   */
  var EXPORT_GRAIN_OPACITY = "0.03";

  var VIEW_IDS = ["front", "back"];
  var DEFAULT_VIEW = "front";

  /* Color palette (ids match persisted Design.garment_color):
   * white #ffffff, black #111111, gray #6b7280, navy #1e3a8a, red #dc2626,
   * royal #2563eb, green #16a34a, yellow #facc15, orange #f97316, maroon #7f1d1d
   */
  var GARMENT_COLORS = [
    { id: "white", label: "White", hex: "#ffffff" },
    { id: "black", label: "Black", hex: "#111111" },
    { id: "gray", label: "Gray", hex: "#6b7280" },
    { id: "grey", label: "Gray", hex: "#6b7280" },
    { id: "navy", label: "Navy", hex: "#1e3a8a" },
    { id: "red", label: "Red", hex: "#dc2626" },
    { id: "royal", label: "Royal", hex: "#2563eb" },
    { id: "green", label: "Green", hex: "#16a34a" },
    { id: "yellow", label: "Yellow", hex: "#facc15" },
    { id: "orange", label: "Orange", hex: "#f97316" },
    { id: "maroon", label: "Maroon", hex: "#7f1d1d" },
  ];

  var COLOR_BY_HEX = Object.create(null);
  var COLOR_BY_ID = Object.create(null);
  (function indexColors() {
    for (var i = 0; i < GARMENT_COLORS.length; i++) {
      var c = GARMENT_COLORS[i];
      COLOR_BY_ID[c.id] = c;
      COLOR_BY_HEX[c.hex.toLowerCase()] = c;
    }
  })();

  /**
   * Must stay identical to apps/designs/garment_choices.py GARMENT_TEMPLATE_ALIASES
   * (keys → canonical GARMENT_TYPES ids).
   */
  var GARMENT_TEMPLATE_ALIASES = {
    "t-shirt": "tee",
    tshirt: "tee",
    "t shirt": "tee",
    "polo-shirt": "polo",
    poloshirt: "polo",
    sweatshirt: "hoodie",
    hooded: "hoodie",
  };

  /**
   * Metadata aligned with static/garments/garments.json (labels + print areas).
   * Cross-ref: apps/designs/garment_choices.py GARMENT_TEMPLATE_IDS
   */
  /* Stage O.1.2: primary printable = full flat front/back incl. sleeves (id front|back). */
  var GARMENT_TYPES = [
    {
      id: "tee",
      label: "T-shirt",
      views: {
        front: {
          svg: "tee-front.svg",
          printAreas: [
            { id: "front", name: "Front", x: 100, y: 160, w: 600, h: 520 },
          ],
        },
        back: {
          svg: "tee-back.svg",
          printAreas: [
            { id: "back", name: "Back", x: 100, y: 155, w: 600, h: 525 },
          ],
        },
      },
    },
    {
      id: "polo",
      label: "Polo shirt",
      views: {
        front: {
          svg: "polo-front.svg",
          printAreas: [
            { id: "front", name: "Front", x: 100, y: 175, w: 600, h: 505 },
          ],
        },
        back: {
          svg: "polo-back.svg",
          printAreas: [
            { id: "back", name: "Back", x: 100, y: 160, w: 600, h: 510 },
          ],
        },
      },
    },
    {
      id: "hoodie",
      label: "Hoodie",
      views: {
        front: {
          svg: "hoodie-front.svg",
          printAreas: [
            { id: "front", name: "Front", x: 130, y: 185, w: 540, h: 495 },
          ],
        },
        back: {
          svg: "hoodie-back.svg",
          printAreas: [
            { id: "back", name: "Back", x: 130, y: 210, w: 540, h: 470 },
          ],
        },
      },
    },
    {
      id: "jersey",
      label: "Jersey",
      views: {
        front: {
          svg: "jersey-front.svg",
          printAreas: [
            { id: "front", name: "Front", x: 240, y: 165, w: 320, h: 520 },
          ],
        },
        back: {
          svg: "jersey-back.svg",
          printAreas: [
            { id: "back", name: "Back", x: 240, y: 160, w: 320, h: 520 },
            { id: "name", name: "Name", x: 300, y: 215, w: 200, h: 70 },
            { id: "number", name: "Number", x: 320, y: 300, w: 160, h: 260 },
          ],
        },
      },
    },
  ];

  var GARMENT_BY_ID = Object.create(null);
  (function indexGarments() {
    for (var i = 0; i < GARMENT_TYPES.length; i++) {
      var g = GARMENT_TYPES[i];
      GARMENT_BY_ID[g.id] = g;
      var v;
      for (v = 0; v < VIEW_IDS.length; v++) {
        var viewId = VIEW_IDS[v];
        if (!g.views[viewId]) {
          g.views[viewId] = { svg: "", printAreas: [] };
        } else if (!Array.isArray(g.views[viewId].printAreas)) {
          g.views[viewId].printAreas = [];
        }
      }
    }
  })();

  var svgTextCache = Object.create(null);
  var splitCache = Object.create(null);
  var renderToken = 0;

  /**
   * sRGB relative luminance (WCAG).
   * contrastColor returns "#111111" when L > 0.5 else "#ffffff".
   */
  function contrastColor(hex) {
    var rgb = parseHex(hex);
    if (!rgb) return "#111111";
    var lin = [rgb.r, rgb.g, rgb.b].map(function (c) {
      c = c / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    var L = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
    return L > 0.5 ? "#111111" : "#ffffff";
  }

  function parseHex(hex) {
    if (!hex || typeof hex !== "string") return null;
    var s = hex.trim();
    if (s.charAt(0) === "#") s = s.slice(1);
    if (!/^[0-9a-fA-F]{6}$/.test(s)) return null;
    return {
      r: parseInt(s.slice(0, 2), 16),
      g: parseInt(s.slice(2, 4), 16),
      b: parseInt(s.slice(4, 6), 16),
    };
  }

  function toHex(r, g, b) {
    function clamp(v) {
      return Math.max(0, Math.min(255, Math.round(v)));
    }
    function h(n) {
      var x = clamp(n).toString(16);
      return x.length === 1 ? "0" + x : x;
    }
    return "#" + h(r) + h(g) + h(b);
  }

  /** Darken (amount < 0) or lighten (amount > 0) a hex color for trim strokes. */
  function shadeColor(hex, amount) {
    var rgb = parseHex(hex);
    if (!rgb) return "#000000";
    var a = typeof amount === "number" ? amount : 0;
    if (a >= 0) {
      return toHex(
        rgb.r + (255 - rgb.r) * a,
        rgb.g + (255 - rgb.g) * a,
        rgb.b + (255 - rgb.b) * a
      );
    }
    var f = 1 + a;
    return toHex(rgb.r * f, rgb.g * f, rgb.b * f);
  }

  function colorById(id) {
    if (id == null || id === "") {
      return COLOR_BY_ID.white || GARMENT_COLORS[0];
    }
    var raw = String(id).trim();
    var lower = raw.toLowerCase();
    if (COLOR_BY_ID[lower]) return COLOR_BY_ID[lower];
    var hex = raw.charAt(0) === "#" ? raw : lower.charAt(0) === "#" ? lower : null;
    if (!hex && /^[0-9a-f]{6}$/i.test(raw)) hex = "#" + raw;
    if (!hex && /^[0-9a-f]{6}$/i.test(lower)) hex = "#" + lower;
    if (hex) {
      var hit = COLOR_BY_HEX[hex.toLowerCase()];
      if (hit) return hit;
      return { id: lower.replace(/^#/, "") || "custom", label: hex, hex: hex.toLowerCase() };
    }
    return COLOR_BY_ID.white || GARMENT_COLORS[0];
  }

  function normalizeGarmentId(id) {
    if (id == null || id === "") return "tee";
    var key = String(id).trim().toLowerCase();
    if (GARMENT_BY_ID[key]) return key;
    if (GARMENT_TEMPLATE_ALIASES[key]) return GARMENT_TEMPLATE_ALIASES[key];
    return key;
  }

  function garmentById(id) {
    var key = normalizeGarmentId(id);
    return GARMENT_BY_ID[key] || null;
  }

  function normalizeViewId(viewId) {
    if (viewId == null || viewId === "") return DEFAULT_VIEW;
    var v = String(viewId).trim().toLowerCase();
    return VIEW_IDS.indexOf(v) >= 0 ? v : DEFAULT_VIEW;
  }

  function assetsBaseUrl() {
    var page = document.querySelector("[data-editor-page]");
    var base =
      (page && page.getAttribute("data-garments-base")) ||
      "/static/garments/";
    if (base.charAt(base.length - 1) !== "/") base += "/";
    return base;
  }

  function svgUrl(fileName) {
    return assetsBaseUrl() + fileName + "?v=" + encodeURIComponent(ASSET_VERSION);
  }

  function fetchSvgText(fileName) {
    var url = svgUrl(fileName);
    if (svgTextCache[url]) return svgTextCache[url];
    svgTextCache[url] = fetch(url, { credentials: "same-origin" }).then(function (res) {
      if (!res.ok) throw new Error("Garment SVG HTTP " + res.status);
      return res.text();
    });
    return svgTextCache[url];
  }

  function escapeRegExp(s) {
    return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  /**
   * Rewrite id prefix in an OVER copy so under/over defs do not collide.
   * Example: "tee-front-" → "tee-front-o-"
   */
  function rewriteIdPrefix(svgText, fromPrefix, toPrefix) {
    if (!fromPrefix || fromPrefix === toPrefix) return svgText;
    var from = escapeRegExp(fromPrefix);
    var out = svgText;
    out = out.replace(new RegExp('id="' + from, "g"), 'id="' + toPrefix);
    out = out.replace(new RegExp("url\\(#" + from, "g"), "url(#" + toPrefix);
    out = out.replace(new RegExp('href="#' + from, "g"), 'href="#' + toPrefix);
    out = out.replace(
      new RegExp('xlink:href="#' + from, "g"),
      'xlink:href="#' + toPrefix
    );
    return out;
  }

  function detectIdPrefix(root) {
    if (!root) return "";
    var groups = root.querySelectorAll("g[id]");
    var i;
    for (i = 0; i < groups.length; i++) {
      var id = groups[i].getAttribute("id") || "";
      var m = id.match(/^(.*-)(ground|base|art|details|shade)$/);
      if (m) return m[1];
    }
    var svgId = root.getAttribute("id") || "";
    if (svgId && /-svg$/.test(svgId)) return svgId.replace(/-svg$/, "-");
    return "";
  }

  function groupBySuffix(root, prefix, suffix) {
    if (!root) return null;
    if (prefix) {
      var want = prefix + suffix;
      var doc = root.ownerDocument;
      if (doc && typeof doc.getElementById === "function") {
        var byId = doc.getElementById(want);
        if (byId) return byId;
      }
      var exact = root.querySelector('[id="' + want + '"]');
      if (exact) return exact;
    }
    var nodes = root.querySelectorAll("g[id]");
    var i;
    for (i = 0; i < nodes.length; i++) {
      var id = nodes[i].getAttribute("id") || "";
      if (id === suffix || id.slice(-(suffix.length + 1)) === "-" + suffix) {
        return nodes[i];
      }
    }
    return null;
  }

  function wrapLayerSvg(defsHtml, bodyHtml, svgAttrs) {
    var attrs = svgAttrs || "";
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="' +
      VIEW_BOX +
      '" width="800" height="800" ' +
      attrs +
      ">" +
      (defsHtml || "") +
      (bodyHtml || "") +
      "</svg>"
    );
  }

  /**
   * Split a garment SVG into under (ground+base) and over (details+shade) documents.
   * Each copy includes the full <defs>. Art group is omitted.
   */
  function splitGarmentSvg(svgText) {
    var cached = splitCache[svgText];
    if (cached) return cached;

    var doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
    var root = doc.documentElement;
    if (!root || root.nodeName.toLowerCase() === "parsererror") {
      throw new Error("Could not parse garment SVG.");
    }

    var prefix = detectIdPrefix(root);
    var overPrefix = prefix ? prefix.replace(/-$/, "-o-") : "o-";
    var defs = root.querySelector("defs");
    var defsHtml = defs ? defs.outerHTML : "";

    var ground = groupBySuffix(root, prefix, "ground");
    var base = groupBySuffix(root, prefix, "base");
    var details = groupBySuffix(root, prefix, "details");
    var shade = groupBySuffix(root, prefix, "shade");

    var underBody =
      (ground ? ground.outerHTML : "") + (base ? base.outerHTML : "");
    var overBody =
      (details ? details.outerHTML : "") + (shade ? shade.outerHTML : "");

    var dataAttrs = "";
    if (root.getAttribute("data-garment")) {
      dataAttrs +=
        ' data-garment="' + root.getAttribute("data-garment") + '"';
    }
    if (root.getAttribute("data-view")) {
      dataAttrs += ' data-view="' + root.getAttribute("data-view") + '"';
    }

    var under = wrapLayerSvg(defsHtml, underBody, dataAttrs);
    var over = rewriteIdPrefix(
      wrapLayerSvg(defsHtml, overBody, dataAttrs),
      prefix,
      overPrefix
    );

    cached = { under: under, over: over, prefix: prefix, overPrefix: overPrefix };
    splitCache[svgText] = cached;
    return cached;
  }

  function liteGarmentEnabled(wrap) {
    if (!wrap) return false;
    if (wrap.getAttribute("data-blytz-lite-garment") === "1") return true;
    var page = document.querySelector("[data-editor-page]");
    return !!(page && page.getAttribute("data-blytz-lite-garment") === "1");
  }

  function stripGrainAndWeave(svgRoot) {
    if (!svgRoot) return;
    var rects = svgRoot.querySelectorAll("rect");
    var i;
    for (i = rects.length - 1; i >= 0; i--) {
      var el = rects[i];
      var fill = el.getAttribute("fill") || "";
      var filter = el.getAttribute("filter") || "";
      if (
        /grain/i.test(fill) ||
        /weave/i.test(fill) ||
        /grain/i.test(filter) ||
        /weave/i.test(filter)
      ) {
        if (el.parentNode) el.parentNode.removeChild(el);
      }
    }
  }

  /**
   * Mount target for garment SVGs: shared #editor-artboard-scene when present
   * so CSS viewport zoom scales garment + Fabric together (Option A).
   */
  function getArtboardMount() {
    return (
      document.getElementById("editor-artboard-scene") ||
      document.getElementById("editor-canvas-wrap")
    );
  }

  function positionLayerSvg(svg, mount) {
    mount = mount || getArtboardMount();
    if (!mount) return;
    svg.setAttribute("viewBox", VIEW_BOX);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("draggable", "false");
    // Inside the scene: fill the scene box (no wrap-border offset).
    // Legacy wrap mount: compensate border so SVG covers the padded box.
    var bl = 0;
    var bt = 0;
    if (mount.id === "editor-canvas-wrap") {
      var cs =
        typeof global.getComputedStyle === "function"
          ? global.getComputedStyle(mount)
          : null;
      bl = cs ? parseFloat(cs.borderLeftWidth) || 0 : 0;
      bt = cs ? parseFloat(cs.borderTopWidth) || 0 : 0;
    }
    var w = mount.clientWidth || mount.offsetWidth || 0;
    var h = mount.clientHeight || mount.offsetHeight || 0;
    svg.style.pointerEvents = "none";
    svg.style.userSelect = "none";
    svg.style.position = "absolute";
    svg.style.left = -bl + "px";
    svg.style.top = -bt + "px";
    svg.style.width = w + bl * 2 + "px";
    svg.style.height = h + bt * 2 + "px";
    svg.style.maxWidth = "none";
    svg.style.maxHeight = "none";
    svg.style.boxSizing = "border-box";
    svg.style.margin = "0";
    svg.style.padding = "0";
    svg.style.overflow = "visible";
    // Clear any leftover per-layer zoom transform (scene owns zoom now).
    svg.style.transform = "";
    svg.style.transformOrigin = "";
    svg.setAttribute("width", String(w + bl * 2));
    svg.setAttribute("height", String(h + bt * 2));
  }

  function syncGarmentViewportFromCanvas() {
    var canvas = global.BlytzCanvas;
    if (canvas && typeof canvas.ensureArtboardScene === "function") {
      canvas.ensureArtboardScene();
    }
    if (canvas && typeof canvas.syncGarmentViewport === "function") {
      canvas.syncGarmentViewport();
    }
  }

  function applyColorVars(el, fillHex, trimHex) {
    if (!el || !el.style) return;
    el.style.setProperty("--garment", fillHex);
    el.style.setProperty("--trim", trimHex);
    el.style.setProperty("--string", STRING_COLOR);
  }

  function parseSvgMarkup(markup) {
    var doc = new DOMParser().parseFromString(markup, "image/svg+xml");
    var root = doc.documentElement;
    if (!root || root.nodeName.toLowerCase() === "parsererror") {
      throw new Error("Could not parse split garment SVG.");
    }
    return document.importNode(root, true);
  }

  function replaceLayerSvg(mount, id, markup, asFirst) {
    mount = mount || getArtboardMount();
    var next = parseSvgMarkup(markup);
    next.setAttribute("id", id);
    positionLayerSvg(next, mount);
    var prev = document.getElementById(id);
    if (prev && prev.parentNode) {
      prev.parentNode.replaceChild(next, prev);
    } else if (asFirst) {
      mount.insertBefore(next, mount.firstChild);
    } else {
      mount.appendChild(next);
    }
    return next;
  }

  /**
   * Print areas for a garment + view from the embedded GARMENT_TYPES catalog
   * (aligned with garments.json). Does not invent dimensions.
   * @returns {{ok: boolean, areas: Array<{id?: string, name?: string, x: number, y: number, w: number, h: number}>, reason: string}}
   */
  function getPrintAreas(garmentId, viewId) {
    var garment = garmentById(garmentId);
    if (!garment) {
      return {
        ok: false,
        areas: [],
        reason: "unknown_garment",
      };
    }
    var view = normalizeViewId(viewId);
    var viewDef = garment.views && garment.views[view];
    if (!viewDef) {
      return {
        ok: false,
        areas: [],
        reason: "unknown_view",
      };
    }
    var raw = viewDef.printAreas;
    if (!Array.isArray(raw) || raw.length === 0) {
      return {
        ok: false,
        areas: [],
        reason: "no_print_areas",
      };
    }
    var areas = [];
    var i;
    for (i = 0; i < raw.length; i++) {
      var a = raw[i];
      if (!a) continue;
      var x = Number(a.x);
      var y = Number(a.y);
      var w = Number(a.w);
      var h = Number(a.h);
      if (!(w > 0) || !(h > 0) || isNaN(x) || isNaN(y)) continue;
      areas.push({
        id: a.id || "",
        name: a.name || "",
        x: x,
        y: y,
        w: w,
        h: h,
      });
    }
    if (!areas.length) {
      return {
        ok: false,
        areas: [],
        reason: "no_print_areas",
      };
    }
    return { ok: true, areas: areas, reason: "" };
  }

  function drawPrintAreas(svg, printAreas, strokeHex) {
    var existing = svg.querySelectorAll('[data-blytz-layer="print-area"]');
    var i;
    for (i = 0; i < existing.length; i++) {
      if (existing[i].parentNode) existing[i].parentNode.removeChild(existing[i]);
    }
    var areas = Array.isArray(printAreas) ? printAreas : [];
    for (i = 0; i < areas.length; i++) {
      var a = areas[i];
      if (!a || a.w == null || a.h == null) continue;
      var rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("data-blytz-layer", "print-area");
      if (a.id) rect.setAttribute("data-print-area-id", a.id);
      rect.setAttribute("aria-hidden", "true");
      rect.setAttribute("fill", "none");
      rect.setAttribute("x", String(a.x));
      rect.setAttribute("y", String(a.y));
      rect.setAttribute("width", String(a.w));
      rect.setAttribute("height", String(a.h));
      rect.setAttribute("stroke", strokeHex || "#111111");
      rect.setAttribute("stroke-width", "2");
      rect.setAttribute("stroke-dasharray", "8 6");
      rect.setAttribute("opacity", "0.5");
      svg.appendChild(rect);
    }
  }

  /**
   * Legacy test helper — placeholder parts removed; returns [].
   * Thumbs use svg file URLs instead.
   */
  function buildPartsForTest() {
    return [];
  }

  function thumbUrl(garmentId) {
    var g = garmentById(garmentId) || garmentById("tee");
    var file =
      g && g.views && g.views.front && g.views.front.svg
        ? g.views.front.svg
        : "tee-front.svg";
    return svgUrl(file);
  }

  function renderGarmentLayer(garmentId, colorId, viewId) {
    var wrap = document.getElementById("editor-canvas-wrap");
    if (!wrap) return null;
    var mount = getArtboardMount() || wrap;

    var garment = garmentById(garmentId) || garmentById("tee");
    var view = normalizeViewId(viewId);
    var color = colorById(colorId);
    var fillHex = color.hex;
    var trimHex = contrastColor(fillHex);

    applyColorVars(wrap, fillHex, trimHex);
    applyColorVars(mount, fillHex, trimHex);

    var viewDef = garment.views[view] || { svg: "", printAreas: [] };
    var fileName = viewDef.svg;
    if (!fileName) return null;

    var token = ++renderToken;
    var promise = fetchSvgText(fileName)
      .then(function (text) {
        if (token !== renderToken) return null;
        var split = splitGarmentSvg(text);
        var under = replaceLayerSvg(
          mount,
          "editor-garment-layer",
          split.under,
          true
        );
        var over = replaceLayerSvg(
          mount,
          "editor-garment-overlay",
          split.over,
          false
        );
        applyColorVars(under, fillHex, trimHex);
        applyColorVars(over, fillHex, trimHex);
        positionLayerSvg(under, mount);
        positionLayerSvg(over, mount);
        syncGarmentViewportFromCanvas();
        if (liteGarmentEnabled(wrap)) {
          stripGrainAndWeave(over);
        }
        drawPrintAreas(over, viewDef.printAreas, contrastColor(fillHex));
        // Keep overlay above Fabric canvases inside the scene.
        if (over.parentNode === mount) {
          mount.appendChild(over);
        }
        return { under: under, over: over };
      })
      .catch(function (err) {
        console.warn("BlytzGarments: failed to load garment SVG", fileName, err);
        return null;
      });

    return promise;
  }

  /**
   * Hide print-area guides on a cloned SVG before PNG composite.
   */
  function hidePrintAreas(svgRoot) {
    if (!svgRoot) return;
    var nodes = svgRoot.querySelectorAll('[data-blytz-layer="print-area"]');
    var i;
    for (i = 0; i < nodes.length; i++) {
      nodes[i].setAttribute("opacity", "0");
      nodes[i].setAttribute("stroke", "none");
    }
  }

  /**
   * Replace SVG CSS variable references with concrete hex colors.
   * Trim form must be replaced before garment (nested var(--garment, …)).
   * Throws if any "var(" remains.
   */
  function resolveSvgCssVars(svgText, colors) {
    colors = colors || {};
    var garment =
      typeof colors.garment === "string" && colors.garment
        ? colors.garment
        : "#f2f2ef";
    var trim =
      typeof colors.trim === "string" && colors.trim ? colors.trim : garment;
    var stringCol =
      typeof colors.string === "string" && colors.string
        ? colors.string
        : STRING_COLOR;
    var out = String(svgText == null ? "" : svgText);
    out = out.split(SVG_VAR_TRIM).join(trim);
    out = out.split(SVG_VAR_GARMENT).join(garment);
    out = out.split(SVG_VAR_STRING).join(stringCol);
    if (out.indexOf("var(") >= 0) {
      throw new Error("Unresolved CSS variables remain in garment SVG.");
    }
    return out;
  }

  /**
   * Lower opacity on grain-filter rects for PNG export only (live editor unchanged).
   * Handles opacity before or after the filter attribute.
   */
  function lowerExportGrainOpacity(svgText, opacity) {
    var op =
      opacity == null || opacity === "" ? EXPORT_GRAIN_OPACITY : String(opacity);
    var out = String(svgText == null ? "" : svgText);
    out = out.replace(
      /(filter="url\([^"]*grain[^"]*\)")(\s+opacity=")[^"]*(")/gi,
      "$1$2" + op + "$3"
    );
    out = out.replace(
      /(\sopacity=")[^"]*("\s+filter="url\([^"]*grain[^"]*\)")/gi,
      "$1" + op + "$2"
    );
    return out;
  }

  /** Strip grain-filter rects entirely (last-resort export size reduction). */
  function stripExportGrain(svgText) {
    var out = String(svgText == null ? "" : svgText);
    return out.replace(/<rect\b[^>]*filter="url\([^"]*grain[^"]*\)"[^>]*\/?>/gi, "");
  }

  /**
   * Build under/over SVG markups for PNG export without touching the live canvas.
   * Bakes CSS vars to hex, lowers grain opacity, omits print-area guides (never drawn here).
   * @returns {Promise<{under: string, over: string, garmentHex: string, trimHex: string}>}
   */
  function getExportLayerMarkups(garmentId, colorId, viewId, opts) {
    opts = opts || {};
    var garment = garmentById(garmentId) || garmentById("tee");
    var view = normalizeViewId(viewId);
    var color = colorById(colorId);
    var fillHex = color.hex;
    var trimHex = contrastColor(fillHex);
    var viewDef = (garment && garment.views && garment.views[view]) || {
      svg: "",
      printAreas: [],
    };
    var fileName = viewDef.svg;
    if (!fileName) {
      return Promise.reject(new Error("Missing garment SVG for export."));
    }
    return fetchSvgText(fileName).then(function (text) {
      var baked = resolveSvgCssVars(text, {
        garment: fillHex,
        trim: trimHex,
        string: STRING_COLOR,
      });
      if (opts.stripGrain) {
        baked = stripExportGrain(baked);
      } else {
        baked = lowerExportGrainOpacity(
          baked,
          opts.grainOpacity != null ? opts.grainOpacity : EXPORT_GRAIN_OPACITY
        );
      }
      var split = splitGarmentSvg(baked);
      return {
        under: split.under,
        over: split.over,
        garmentHex: fillHex,
        trimHex: trimHex,
      };
    });
  }

  global.BlytzGarments = {
    GARMENT_TYPES: GARMENT_TYPES,
    GARMENT_COLORS: GARMENT_COLORS,
    GARMENT_TEMPLATE_ALIASES: GARMENT_TEMPLATE_ALIASES,
    VIEW_IDS: VIEW_IDS,
    DEFAULT_VIEW: DEFAULT_VIEW,
    ASSET_VERSION: ASSET_VERSION,
    STRING_COLOR: STRING_COLOR,
    SVG_VAR_TRIM: SVG_VAR_TRIM,
    SVG_VAR_GARMENT: SVG_VAR_GARMENT,
    SVG_VAR_STRING: SVG_VAR_STRING,
    EXPORT_GRAIN_OPACITY: EXPORT_GRAIN_OPACITY,
    garmentById: garmentById,
    colorById: colorById,
    contrastColor: contrastColor,
    shadeColor: shadeColor,
    normalizeGarmentId: normalizeGarmentId,
    splitGarmentSvg: splitGarmentSvg,
    rewriteIdPrefix: rewriteIdPrefix,
    renderGarmentLayer: renderGarmentLayer,
    getPrintAreas: getPrintAreas,
    buildPartsForTest: buildPartsForTest,
    thumbUrl: thumbUrl,
    hidePrintAreas: hidePrintAreas,
    resolveSvgCssVars: resolveSvgCssVars,
    lowerExportGrainOpacity: lowerExportGrainOpacity,
    stripExportGrain: stripExportGrain,
    getExportLayerMarkups: getExportLayerMarkups,
    fetchSvgText: fetchSvgText,
  };
})(typeof window !== "undefined" ? window : globalThis);
