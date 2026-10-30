/**
 * Responsive navigation drawer (< 1024px)
 */
(function () {
  "use strict";

  function closeAll() {
    document.querySelectorAll(".nav-drawer.is-open").forEach(function (d) {
      d.classList.remove("is-open");
    });
    document.body.classList.remove("overflow-hidden");
  }

  document.addEventListener("click", function (e) {
    var openBtn = e.target.closest("[data-nav-open]");
    if (openBtn) {
      e.preventDefault();
      var id = openBtn.getAttribute("data-nav-open");
      var drawer = document.getElementById(id);
      if (drawer) {
        drawer.classList.add("is-open");
        document.body.classList.add("overflow-hidden");
      }
      return;
    }
    if (e.target.closest("[data-nav-close]")) {
      closeAll();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAll();
  });

  // Jobs pipeline mobile tabs (<768px; desktop CSS shows all phases)
  document.addEventListener("click", function (e) {
    var tab = e.target.closest("[data-pipeline-tab]");
    if (!tab) return;
    var root = tab.closest("[data-pipeline]");
    if (!root) return;
    var key = tab.getAttribute("data-pipeline-tab");
    root.querySelectorAll("[data-pipeline-tab]").forEach(function (t) {
      var on = t.getAttribute("data-pipeline-tab") === key;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.classList.toggle("is-active", on);
      t.classList.toggle("border-ink", on);
      t.classList.toggle("text-ink", on);
      t.classList.toggle("border-transparent", !on);
      t.classList.toggle("text-ink-muted", !on);
    });
    root.querySelectorAll("[data-pipeline-panel]").forEach(function (p) {
      p.classList.toggle(
        "is-inactive",
        p.getAttribute("data-pipeline-panel") !== key
      );
    });
  });
})();
