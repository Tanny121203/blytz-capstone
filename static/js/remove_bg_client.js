/**
 * Stage R.2 — client-side background removal via @imgly/background-removal.
 *
 * Loads the library with dynamic import (ESM CDN). Models/WASM are fetched on
 * first use (cached by the browser). Output is always a PNG data URL for
 * canvas_safety. Does not call any Blytz backend.
 *
 * License: see static/vendor/imgly/LICENSE.md (IMG.LY package license).
 */
(function (global) {
  "use strict";

  // Pin version; esm.sh resolves onnxruntime-web peer. Override via
  // data-imgly-esm-url on [data-editor-page] if needed.
  var DEFAULT_IMGLY_ESM =
    "https://esm.sh/@imgly/background-removal@1.7.0?deps=onnxruntime-web@1.21.0";

  var loadPromise = null;

  function editorPage() {
    return document.querySelector("[data-editor-page]");
  }

  function imglyEsmUrl() {
    var page = editorPage();
    var custom = page && page.getAttribute("data-imgly-esm-url");
    return (custom && custom.trim()) || DEFAULT_IMGLY_ESM;
  }

  function blobToDataUrl(blob) {
    return new Promise(function (resolve, reject) {
      if (!blob) {
        reject(new Error("empty-blob"));
        return;
      }
      var reader = new FileReader();
      reader.onload = function () {
        var result = reader.result;
        if (typeof result !== "string" || result.indexOf("data:image/") !== 0) {
          reject(new Error("bad-data-url"));
          return;
        }
        resolve(result);
      };
      reader.onerror = function () {
        reject(new Error("read-failed"));
      };
      reader.readAsDataURL(blob);
    });
  }

  function loadLib() {
    if (loadPromise) return loadPromise;
    loadPromise = import(/* webpackIgnore: true */ imglyEsmUrl())
      .then(function (mod) {
        var removeBackground =
          (mod && (mod.default || mod.removeBackground)) || null;
        if (typeof removeBackground !== "function") {
          throw new Error("imgly-api");
        }
        return {
          removeBackground: removeBackground,
          preload: typeof mod.preload === "function" ? mod.preload : null,
        };
      })
      .catch(function (err) {
        loadPromise = null;
        throw err;
      });
    return loadPromise;
  }

  /**
   * @param {string|Blob|URL} imageSource data URL, Blob, etc.
   * @param {{progress?: function, onLoadStart?: function}=} options
   * @returns {Promise<string>} PNG data URL
   */
  function removeToDataUrl(imageSource, options) {
    options = options || {};
    var notifiedLoad = false;
    return loadLib()
      .then(function (api) {
        if (options.onLoadStart && !notifiedLoad) {
          notifiedLoad = true;
          try {
            options.onLoadStart();
          } catch (_e) {
            /* ignore */
          }
        }
        return api.removeBackground(imageSource, {
          progress: options.progress,
          output: { format: "image/png", type: "foreground" },
          // Prefer GPU; library falls back when WebGPU is unavailable.
          device: options.device || "cpu",
          model: options.model || "isnet_fp16",
        });
      })
      .then(function (blob) {
        return blobToDataUrl(blob);
      });
  }

  function supported() {
    try {
      // Dynamic import exists in evergreen browsers used for the editor.
      return typeof Promise !== "undefined" && typeof FileReader !== "undefined";
    } catch (_e) {
      return false;
    }
  }

  global.BlytzRemoveBg = {
    VERSION: "1.7.0",
    supported: supported,
    load: loadLib,
    removeToDataUrl: removeToDataUrl,
  };
})(typeof window !== "undefined" ? window : this);
