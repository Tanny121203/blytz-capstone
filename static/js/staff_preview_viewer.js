/**
 * Full-screen mock-up viewer with pinch-zoom on touch devices.
 */
(function () {
  "use strict";

  function init() {
    var overlay = document.getElementById("preview-lightbox");
    if (!overlay) return;

    var img = overlay.querySelector("[data-lightbox-img]");
    var label = overlay.querySelector("[data-lightbox-label]");
    var stage = overlay.querySelector("[data-lightbox-stage]");

    var scale = 1;
    var tx = 0;
    var ty = 0;
    var pointers = new Map();
    var lastPinchDist = 0;

    function applyTransform() {
      if (!img) return;
      img.style.transform =
        "translate(" + tx + "px, " + ty + "px) scale(" + scale + ")";
    }

    function resetTransform() {
      scale = 1;
      tx = 0;
      ty = 0;
      applyTransform();
    }

    function open(src, title) {
      if (!img) return;
      img.src = src;
      img.alt = title || "Mock-up preview";
      if (label) label.textContent = title || "";
      resetTransform();
      overlay.classList.remove("hidden");
      overlay.classList.add("flex");
      document.body.classList.add("overflow-hidden");
      overlay.setAttribute("aria-hidden", "false");
    }

    function close() {
      overlay.classList.add("hidden");
      overlay.classList.remove("flex");
      document.body.classList.remove("overflow-hidden");
      overlay.setAttribute("aria-hidden", "true");
      if (img) img.removeAttribute("src");
      pointers.clear();
      lastPinchDist = 0;
      resetTransform();
    }

    document.querySelectorAll("[data-preview-open]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var src = btn.getAttribute("data-preview-src");
        var title = btn.getAttribute("data-preview-label") || "Preview";
        if (src) open(src, title);
      });
    });

    overlay.querySelectorAll("[data-lightbox-close]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        e.preventDefault();
        close();
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !overlay.classList.contains("hidden")) {
        close();
      }
    });

    if (!stage || !img) return;

    stage.addEventListener(
      "wheel",
      function (e) {
        if (overlay.classList.contains("hidden")) return;
        e.preventDefault();
        var delta = e.deltaY > 0 ? -0.1 : 0.1;
        scale = Math.min(4, Math.max(1, scale + delta));
        if (scale === 1) {
          tx = 0;
          ty = 0;
        }
        applyTransform();
      },
      { passive: false }
    );

    stage.addEventListener("pointerdown", function (e) {
      if (overlay.classList.contains("hidden")) return;
      stage.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        var pts = Array.from(pointers.values());
        var dx = pts[0].x - pts[1].x;
        var dy = pts[0].y - pts[1].y;
        lastPinchDist = Math.hypot(dx, dy) || 1;
      }
    });

    stage.addEventListener("pointermove", function (e) {
      if (!pointers.has(e.pointerId)) return;
      var prev = pointers.get(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (pointers.size === 2) {
        var pts = Array.from(pointers.values());
        var dx = pts[0].x - pts[1].x;
        var dy = pts[0].y - pts[1].y;
        var dist = Math.hypot(dx, dy) || 1;
        if (lastPinchDist > 0) {
          scale = Math.min(4, Math.max(1, scale * (dist / lastPinchDist)));
          if (scale === 1) {
            tx = 0;
            ty = 0;
          }
          applyTransform();
        }
        lastPinchDist = dist;
      } else if (pointers.size === 1 && scale > 1) {
        tx += e.clientX - prev.x;
        ty += e.clientY - prev.y;
        applyTransform();
      }
    });

    function endPointer(e) {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) lastPinchDist = 0;
    }

    stage.addEventListener("pointerup", endPointer);
    stage.addEventListener("pointercancel", endPointer);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
