/**
 * Landing demo widget — client-only; no save / upload.
 */
(function () {
  "use strict";

  function init(root) {
    const shirt = root.querySelector("#demo-shirt");
    const shirtText = root.querySelector("#demo-shirt-text");
    const input = root.querySelector("[data-demo-text-input]");
    if (!shirt || !shirtText || !input) return;

    root.querySelectorAll("[data-demo-color]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        shirt.setAttribute("fill", btn.getAttribute("data-demo-color"));
        shirtText.setAttribute("fill", btn.getAttribute("data-demo-text") || "#FFFFFF");
        root.querySelectorAll("[data-demo-color]").forEach(function (b) {
          b.classList.toggle("border-2", b === btn);
          b.classList.toggle("border-ink", b === btn);
          b.classList.toggle("border", b !== btn);
          b.classList.toggle("border-border", b !== btn);
        });
      });
    });

    input.addEventListener("input", function () {
      const value = input.value.trim() || " ";
      shirtText.textContent = value.slice(0, 24);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-demo-widget]").forEach(init);
  });
})();
