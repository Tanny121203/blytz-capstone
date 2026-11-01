/* editor_title_sync.js
 * Keeps every visible rendering of the design title in sync with
 * the #editor-design-title input while the user types.
 * No server calls; the existing save/submit flow handles persistence.
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var input = document.querySelector('[data-editor-title]');
    if (!input) return;                       // already-submitted view

    var crumb        = document.querySelector('[data-editor-title-crumb]');
    var previewTitle = document.querySelector('[data-design-preview-title]');
    var fallback     = 'Untitled Design';

    function currentTitle() {
      var v = (input.value || '').trim();
      return v || fallback;
    }

    function apply() {
      var t = currentTitle();
      if (crumb)        crumb.textContent = t;
      if (previewTitle) previewTitle.textContent = t;
      document.title = 'Editor · ' + t + ' — Blytz';
    }

    input.addEventListener('input',  apply);
    input.addEventListener('change', apply);

    var previewBtn = document.querySelector('[data-editor-preview]');
    if (previewBtn) {
      previewBtn.addEventListener('click', function () {
        setTimeout(apply, 0);
        setTimeout(apply, 150);
      });
    }

    apply();
  });
})();