/**
 * Editor phone / tablet chrome: layout mode, contextual bar, undo/redo wiring,
 * visualViewport keyboard offset for the Text sheet.
 * Keeps window.BlytzEditor contract intact; additive helpers only.
 */
(function (global) {
  "use strict";

  var wired = false;
  var vvWired = false;

  function shell() {
    return document.querySelector(".editor-shell[data-editor-page]");
  }

  function isDockedLayout() {
    return (
      typeof matchMedia === "function" &&
      matchMedia("(pointer: coarse)").matches &&
      matchMedia("(min-width: 900px)").matches &&
      matchMedia("(orientation: landscape)").matches
    );
  }

  function isPhoneChrome() {
    return typeof matchMedia === "function" && matchMedia("(max-width: 767px)").matches;
  }

  function syncLayoutMode() {
    var el = shell();
    if (!el) return;
    el.setAttribute("data-editor-layout", isDockedLayout() ? "docked" : "sheets");
  }

  function contextBar() {
    return document.getElementById("editor-context-bar");
  }

  function syncContextBar() {
    var bar = contextBar();
    var api = global.BlytzCanvas;
    if (!bar || !api) return;
    var canvas = api.getFabricCanvas && api.getFabricCanvas();
    var active = canvas && canvas.getActiveObject && canvas.getActiveObject();
    var show =
      !!active &&
      !isDockedLayout() &&
      (isPhoneChrome() ||
        (typeof matchMedia === "function" && matchMedia("(max-width: 1023px)").matches));
    if (!show) {
      bar.hidden = true;
      bar.classList.remove("is-visible");
      return;
    }
    bar.hidden = false;
    bar.classList.add("is-visible");
    var multi = api.isActiveSelection && api.isActiveSelection(active);
    bar.querySelectorAll("[data-context-action]").forEach(function (btn) {
      var act = btn.getAttribute("data-context-action");
      if (act === "duplicate" || act === "color") {
        btn.disabled = !!multi;
      } else if (act === "forward") {
        btn.disabled = !(api.canReorderActive && api.canReorderActive("forward"));
      } else if (act === "backward") {
        btn.disabled = !(api.canReorderActive && api.canReorderActive("backward"));
      } else {
        btn.disabled = false;
      }
    });
  }

  function applyVisualViewportOffset() {
    var panel = document.getElementById("editor-tool-panel");
    if (!panel || !panel.classList.contains("is-open")) {
      document.documentElement.style.removeProperty("--blytz-keyboard-inset");
      return;
    }
    if (!global.visualViewport) return;
    var inset = Math.max(
      0,
      global.innerHeight - global.visualViewport.height - global.visualViewport.offsetTop
    );
    document.documentElement.style.setProperty(
      "--blytz-keyboard-inset",
      inset + "px"
    );
    if (inset > 40) {
      panel.style.maxHeight = "calc(100dvh - var(--blytz-keyboard-inset) - 4rem)";
      panel.style.bottom = "var(--blytz-keyboard-inset)";
    } else {
      panel.style.maxHeight = "";
      panel.style.bottom = "";
    }
  }

  function wireVisualViewport() {
    if (vvWired || !global.visualViewport) return;
    vvWired = true;
    global.visualViewport.addEventListener("resize", applyVisualViewportOffset);
    global.visualViewport.addEventListener("scroll", applyVisualViewportOffset);
  }

  function openColorPickerForActive() {
    var api = global.BlytzCanvas;
    var canvas = api && api.getFabricCanvas && api.getFabricCanvas();
    var obj = canvas && canvas.getActiveObject();
    if (!obj) return;
    var input = document.createElement("input");
    input.type = "color";
    var current =
      (obj.fill && typeof obj.fill === "string" && obj.fill.indexOf("#") === 0
        ? obj.fill
        : null) ||
      (obj.stroke && typeof obj.stroke === "string" && obj.stroke.indexOf("#") === 0
        ? obj.stroke
        : "#0A0A0A");
    input.value = current;
    input.style.position = "fixed";
    input.style.left = "-9999px";
    document.body.appendChild(input);
    input.addEventListener("change", function () {
      var next = input.value;
      var getJSON =
        global.BlytzEditor && global.BlytzEditor.getCanvasJSON
          ? function () {
              return global.BlytzEditor.getCanvasJSON();
            }
          : null;
      api.commitEdit(
        "context-color",
        function () {
          if (obj.fill != null && typeof obj.fill === "string") obj.set("fill", next);
          else if (obj.stroke != null) obj.set("stroke", next);
          canvas.requestRenderAll();
          return true;
        },
        getJSON
      );
      document.body.removeChild(input);
    });
    input.click();
  }

  function wire() {
    if (wired) return;
    wired = true;
    syncLayoutMode();
    wireVisualViewport();

    // Existing history only — Ctrl/Cmd+Z undo, Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y redo.
    document.addEventListener("keydown", function (e) {
      var tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.target && e.target.isContentEditable) return;
      var canvasApi = global.BlytzCanvas;
      var fc = canvasApi && canvasApi.getFabricCanvas && canvasApi.getFabricCanvas();
      var active = fc && fc.getActiveObject && fc.getActiveObject();
      if (active && active.isEditing) return;
      var mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      var key = e.key;
      if (key === "z" || key === "Z") {
        e.preventDefault();
        if (e.shiftKey) {
          if (global.BlytzEditor && global.BlytzEditor.redo) global.BlytzEditor.redo();
        } else if (global.BlytzEditor && global.BlytzEditor.undo) {
          global.BlytzEditor.undo();
        }
        return;
      }
      if (key === "y" || key === "Y") {
        e.preventDefault();
        if (global.BlytzEditor && global.BlytzEditor.redo) global.BlytzEditor.redo();
      }
    });

    document.addEventListener("click", function (e) {
      var undoBtn = e.target.closest("[data-editor-undo]");
      if (undoBtn) {
        e.preventDefault();
        if (undoBtn.disabled) return;
        if (global.BlytzEditor && global.BlytzEditor.undo) global.BlytzEditor.undo();
        return;
      }
      var redoBtn = e.target.closest("[data-editor-redo]");
      if (redoBtn) {
        e.preventDefault();
        if (redoBtn.disabled) return;
        if (global.BlytzEditor && global.BlytzEditor.redo) global.BlytzEditor.redo();
        return;
      }
      var viewBtn = e.target.closest("[data-editor-view]");
      if (viewBtn) {
        e.preventDefault();
        var view = viewBtn.getAttribute("data-editor-view");
        if (global.BlytzEditor && global.BlytzEditor.setActiveView) {
          global.BlytzEditor.setActiveView(view).then(function () {
            syncViewOverlay();
          });
        }
        return;
      }
      var ctx = e.target.closest("[data-context-action]");
      if (ctx && contextBar() && contextBar().contains(ctx)) {
        e.preventDefault();
        var act = ctx.getAttribute("data-context-action");
        var api = global.BlytzCanvas;
        var getJSON =
          global.BlytzEditor && global.BlytzEditor.getCanvasJSON
            ? function () {
                return global.BlytzEditor.getCanvasJSON();
              }
            : null;
        if (!api) return;
        if (act === "delete") api.deleteSelection(getJSON);
        else if (act === "duplicate") api.duplicateActive(getJSON);
        else if (act === "forward") api.reorderActive("forward", getJSON);
        else if (act === "backward") api.reorderActive("backward", getJSON);
        else if (act === "color") openColorPickerForActive();
        syncContextBar();
      }
    });

    global.addEventListener("resize", function () {
      syncLayoutMode();
      syncContextBar();
      applyVisualViewportOffset();
      if (global.BlytzCanvas && global.BlytzCanvas.applyResponsiveSize) {
        global.BlytzCanvas.applyResponsiveSize();
      }
    });
    global.addEventListener("orientationchange", function () {
      setTimeout(function () {
        syncLayoutMode();
        syncContextBar();
        if (global.BlytzCanvas && global.BlytzCanvas.applyResponsiveSize) {
          global.BlytzCanvas.applyResponsiveSize();
        }
      }, 100);
    });

    var tries = 0;
    (function waitCanvas() {
      var api = global.BlytzCanvas;
      var c = api && api.getFabricCanvas && api.getFabricCanvas();
      if (!c) {
        if (tries++ < 80) setTimeout(waitCanvas, 50);
        return;
      }
      [
        "selection:created",
        "selection:updated",
        "selection:cleared",
        "object:modified",
      ].forEach(function (ev) {
        c.on(ev, syncContextBar);
      });
      if (global.BlytzEditor && global.BlytzEditor.onCommittedChange) {
        global.BlytzEditor.onCommittedChange(syncContextBar);
      }
      if (global.BlytzEditor && global.BlytzEditor.onViewChange) {
        global.BlytzEditor.onViewChange(syncViewOverlay);
      }
      syncContextBar();
      syncViewOverlay();
    })();
  }

  function syncViewOverlay() {
    var active =
      global.BlytzEditor && global.BlytzEditor.getActiveView
        ? global.BlytzEditor.getActiveView()
        : "front";
    document.querySelectorAll("[data-editor-view]").forEach(function (btn) {
      var on = btn.getAttribute("data-editor-view") === active;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  global.BlytzEditorChrome = {
    syncLayoutMode: syncLayoutMode,
    syncContextBar: syncContextBar,
    applyVisualViewportOffset: applyVisualViewportOffset,
    isDockedLayout: isDockedLayout,
    isPhoneChrome: isPhoneChrome,
  };

  document.addEventListener("DOMContentLoaded", wire);
})(window);
