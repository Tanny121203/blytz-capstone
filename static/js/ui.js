/**
 * Blytz UI — Modal, Drawer, Tabs
 */
(function () {
  "use strict";

  function openOverlay(el) {
    if (!el) return;
    el.classList.remove("hidden");
    el.classList.add("flex");
    document.body.classList.add("overflow-hidden");
    const focusable = el.querySelector(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable) focusable.focus();
  }

  function closeOverlay(el) {
    if (!el) return;
    el.classList.add("hidden");
    el.classList.remove("flex");
    if (!document.querySelector("[data-modal].flex, [data-drawer]:not(.hidden)")) {
      document.body.classList.remove("overflow-hidden");
    }
  }

  document.addEventListener("click", function (e) {
    const openModal = e.target.closest("[data-modal-open]");
    if (openModal) {
      e.preventDefault();
      openOverlay(document.getElementById(openModal.getAttribute("data-modal-open")));
      return;
    }
    const closeModal = e.target.closest("[data-modal-close]");
    if (closeModal) {
      closeOverlay(closeModal.closest("[data-modal]"));
      return;
    }
    const openDrawer = e.target.closest("[data-drawer-open]");
    if (openDrawer) {
      e.preventDefault();
      const drawer = document.getElementById(openDrawer.getAttribute("data-drawer-open"));
      if (drawer) {
        drawer.classList.remove("hidden");
        document.body.classList.add("overflow-hidden");
      }
      return;
    }
    const closeDrawer = e.target.closest("[data-drawer-close]");
    if (closeDrawer) {
      const drawer = closeDrawer.closest("[data-drawer]");
      if (drawer) {
        drawer.classList.add("hidden");
        document.body.classList.remove("overflow-hidden");
      }
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll("[data-modal].flex").forEach(closeOverlay);
    document.querySelectorAll("[data-drawer]:not(.hidden)").forEach(function (d) {
      d.classList.add("hidden");
      document.body.classList.remove("overflow-hidden");
    });
  });

  function activateTab(root, key) {
    root.querySelectorAll("[data-tab]").forEach(function (btn) {
      const active = btn.getAttribute("data-tab") === key;
      btn.setAttribute("aria-selected", active ? "true" : "false");
      btn.tabIndex = active ? 0 : -1;
      btn.classList.toggle("border-ink", active);
      btn.classList.toggle("text-ink", active);
      btn.classList.toggle("border-transparent", !active);
      btn.classList.toggle("text-ink-muted", !active);
    });
    root.querySelectorAll("[data-tab-panel]").forEach(function (panel) {
      const active = panel.getAttribute("data-tab-panel") === key;
      panel.classList.toggle("hidden", !active);
      if (active) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    });
  }

  document.addEventListener("click", function (e) {
    const tab = e.target.closest("[data-tab]");
    if (!tab) return;
    const root = tab.closest("[data-tabs]");
    if (!root) return;
    activateTab(root, tab.getAttribute("data-tab"));
  });

  var SUCCESS_AUTO_DISMISS_MS = 2000;

  function prefersReducedMotion() {
    return (
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function dismissMessage(el, animate) {
    if (!el || el.getAttribute("data-dismissing") === "1") return;
    el.setAttribute("data-dismissing", "1");
    var finish = function () {
      var root = el.closest("[data-messages-root]");
      el.remove();
      if (root && !root.querySelector("[data-message]")) {
        root.remove();
      }
    };
    if (!animate || prefersReducedMotion()) {
      finish();
      return;
    }
    el.style.transition = "opacity 300ms ease";
    el.style.opacity = "0";
    window.setTimeout(finish, 300);
  }

  // Delegation so close works even if banners are re-rendered or init is late.
  document.addEventListener("click", function (e) {
    var closeBtn = e.target.closest("[data-message-close]");
    if (!closeBtn) return;
    var banner = closeBtn.closest("[data-message]");
    if (!banner) return;
    e.preventDefault();
    e.stopPropagation();
    var level = banner.getAttribute("data-message-level") || "info";
    dismissMessage(banner, level === "success");
  });

  function initMessageBanners() {
    var root = document.querySelector("[data-messages-root]");
    if (!root) return;

    root.querySelectorAll("[data-message]").forEach(function (banner) {
      if (banner.getAttribute("data-message-bound") === "1") return;
      banner.setAttribute("data-message-bound", "1");

      var level = (banner.getAttribute("data-message-level") || "info").trim();
      if (level !== "success") return;

      var remaining = SUCCESS_AUTO_DISMISS_MS;
      var timerId = null;
      var lastStarted = 0;
      var paused = false;

      function clearTimer() {
        if (timerId) {
          window.clearTimeout(timerId);
          timerId = null;
        }
      }

      function startTimer() {
        if (paused || banner.getAttribute("data-dismissing") === "1") return;
        clearTimer();
        lastStarted = Date.now();
        timerId = window.setTimeout(function () {
          dismissMessage(banner, true);
        }, remaining);
      }

      function pauseTimer() {
        if (paused || !timerId) return;
        paused = true;
        remaining = Math.max(0, remaining - (Date.now() - lastStarted));
        clearTimer();
      }

      function resumeTimer() {
        if (!paused) return;
        paused = false;
        if (remaining <= 0) {
          dismissMessage(banner, true);
          return;
        }
        startTimer();
      }

      banner.addEventListener("mouseenter", pauseTimer);
      banner.addEventListener("mouseleave", resumeTimer);
      banner.addEventListener("focusin", pauseTimer);
      banner.addEventListener("focusout", function (e) {
        if (!banner.contains(e.relatedTarget)) {
          resumeTimer();
        }
      });

      startTimer();
    });
  }

  function syncNavOffset() {
    var nav = document.querySelector("header.sticky") || document.querySelector("header");
    if (!nav) return;
    var height = Math.ceil(nav.getBoundingClientRect().height);
    document.documentElement.style.setProperty(
      "--blytz-nav-offset",
      height + "px"
    );
  }

  function bootUi() {
    syncNavOffset();
    initMessageBanners();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootUi);
  } else {
    bootUi();
  }
  window.addEventListener("resize", syncNavOffset);
})();
