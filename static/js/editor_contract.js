/**
 * BlytzEditor public contract — Fabric.js-backed (Stage 1).
 *
 * Stable public methods:
 *   getCanvasJSON(), loadCanvasJSON(json|string),
 *   getPreviewPNG(opts?), onCommittedChange(cb)
 *   getPreviewPNG: no opts → sync artwork-only; {view, includeGarment} may return a Promise
 *
 * Additive readiness / safety helpers (used by editor_page.js):
 *   getLoadState(), isReady(), canPersist(), getPersistBlockReason(),
 *   whenReady(), preparePersistPayload()
 * Additive history navigate hook (Stage G dirty recompute after undo/redo):
 *   onHistoryNavigate(cb)
 *
 * Canvas JSON schema (schema_version 1):
 * {
 *   schema_version: 1,
 *   width: 800,
 *   height: 800,
 *   canvas: { ...Fabric.js canvas.toObject()... }
 * }
 */
(function (global) {
  "use strict";

  var commitListeners = [];
  var historyNavigateListeners = [];
  /** @type {'idle'|'loading'|'ready'|'error'} */
  var loadState = "idle";
  var persistBlocked = false;
  var persistBlockReason = "";
  var readyPromise = Promise.resolve();
  var readyResolve = null;
  var pageInitialized = false;

  function notifyHistoryNavigate(action, result) {
    historyNavigateListeners.slice().forEach(function (cb) {
      try {
        cb(action, result);
      } catch (err) {
        console.error("BlytzEditor onHistoryNavigate error", err);
      }
    });
  }

  function canvasApi() {
    return global.BlytzCanvas;
  }

  function syncDomState() {
    var page = document.querySelector("[data-editor-page]");
    if (page) {
      page.dataset.editorLoadState = loadState;
      page.dataset.editorCanPersist = persistBlocked || loadState !== "ready" ? "0" : "1";
    }
    var saveBtn = document.querySelector("[data-editor-save]");
    var submitBtn = document.querySelector("[data-editor-submit]");
    var already =
      page && page.dataset.alreadySubmitted === "1";
    var allow = loadState === "ready" && !persistBlocked;
    if (saveBtn) saveBtn.disabled = !allow;
    if (submitBtn) submitBtn.disabled = !allow || already;
  }

  function beginReadyCycle() {
    readyPromise = new Promise(function (resolve) {
      readyResolve = resolve;
    });
  }

  function finishReadyCycle() {
    if (readyResolve) {
      readyResolve({ state: loadState, canPersist: !persistBlocked && loadState === "ready" });
      readyResolve = null;
    }
    syncDomState();
  }

  function setLoading() {
    loadState = "loading";
    persistBlocked = true;
    persistBlockReason = "Design is still loading…";
    syncDomState();
  }

  function setReady() {
    loadState = "ready";
    persistBlocked = false;
    persistBlockReason = "";
    finishReadyCycle();
    var api = canvasApi();
    if (api && typeof api.seedHistory === "function") {
      try {
        api.seedHistory(getJSON());
      } catch (err) {
        /* ignore */
      }
    }
  }

  function setError(message) {
    loadState = "error";
    persistBlocked = true;
    persistBlockReason = message || "Design could not be loaded. Saving is blocked.";
    var api = canvasApi();
    if (api) api.setToolFeedback(persistBlockReason);
    finishReadyCycle();
  }

  function getJSON() {
    var api = canvasApi();
    if (!api) {
      return {
        schema_version: 1,
        width: 800,
        height: 800,
        canvas: { version: "6.6.1", objects: [] },
      };
    }
    api.ensureCanvas(getJSON);
    return JSON.parse(JSON.stringify(api.buildEnvelopeFromCanvas()));
  }

  /**
   * Validate + snapshot + load fabric payload; restore snapshot on failure.
   * Shared by applyCanvasJSON (legacy name) and previewCanvasJSON (Stage 2).
   * @returns {Promise<{ok: boolean, error?: string, restored?: boolean}>}
   */
  function safeReplaceCanvas(json, messages) {
    messages = messages || {};
    return new Promise(function (resolve) {
      if (!BlytzEditor.canPersist()) {
        resolve({
          ok: false,
          error: BlytzEditor.getPersistBlockReason() || "Editor is not ready.",
        });
        return;
      }
      var validated = BlytzEditor.validateCanvasJSON(json);
      if (!validated.ok) {
        resolve({ ok: false, error: validated.error });
        return;
      }
      var api = canvasApi();
      var snapshot = getJSON();
      beginReadyCycle();
      setLoading();
      api
        .loadFabricPayload(validated.fabricPayload, getJSON)
        .then(function () {
          if (api.getLastLoadError()) {
            throw new Error(api.getLastLoadError());
          }
          setReady();
          resolve({ ok: true });
        })
        .catch(function () {
          var snapParsed = api.parseInput(snapshot);
          api
            .loadFabricPayload(snapParsed.fabricPayload, getJSON)
            .then(function () {
              if (api.getLastLoadError()) {
                throw new Error(api.getLastLoadError());
              }
              setReady();
              resolve({
                ok: false,
                restored: true,
                error:
                  messages.failMessage ||
                  "Could not update the canvas. Your previous design was restored.",
              });
            })
            .catch(function () {
              setError(
                messages.dualFailMessage ||
                  "Canvas update failed and the previous design could not be restored. Reload the page."
              );
              resolve({
                ok: false,
                restored: false,
                error:
                  messages.dualFailMessage ||
                  "Canvas update failed and the previous design could not be restored. Reload the page.",
              });
            });
        });
    });
  }

  var BlytzEditor = {
    getCanvasJSON: function () {
      return getJSON();
    },

    /**
     * Start loading design JSON into the canvas.
     * Returns the normalized envelope immediately (legacy sync contract).
     * Loading completion is tracked via getLoadState() / whenReady().
     */
    loadCanvasJSON: function (json) {
      var api = canvasApi();
      if (!api) {
        console.error("BlytzCanvas is not loaded");
        setError("Editor failed to initialize.");
        return {
          schema_version: 1,
          width: 800,
          height: 800,
          canvas: { version: "6.6.1", objects: [] },
        };
      }

      beginReadyCycle();
      setLoading();

      var parsed = api.parseInput(json);
      api.ensureCanvas(getJSON);

      if (parsed.blockPersist) {
        // Show empty workspace but keep persist blocked so originals stay safe.
        api
          .loadFabricPayload(parsed.fabricPayload, getJSON)
          .catch(function () {})
          .then(function () {
            setError(parsed.message || api.getLastLoadError() || "Design could not be loaded.");
          });
        return JSON.parse(JSON.stringify(parsed.envelope));
      }

      // Shared safety scan BEFORE Fabric loadFromJSON so no network image fetch can run.
      // Must stay identical to apps/designs/canvas_safety.py.
      if (
        (parsed.kind === "blytz_v1" || parsed.kind === "raw_fabric") &&
        typeof api.scanCanvasPayload === "function"
      ) {
        var scanTarget =
          parsed.kind === "blytz_v1" ? parsed.envelope : parsed.fabricPayload;
        var scanned = api.scanCanvasPayload(scanTarget);
        if (!scanned.ok) {
          var safeMsg =
            "This saved design contains content the editor cannot load safely. Your saved data was not changed.";
          api
            .loadFabricPayload(
              { version: "6.6.1", objects: [] },
              getJSON
            )
            .catch(function () {})
            .then(function () {
              setError(safeMsg);
            });
          return JSON.parse(JSON.stringify(parsed.envelope));
        }
      }

      // Full envelope load: front → live canvas, views.back → viewStore, activeView = front.
      var loadPromise =
        parsed.kind === "blytz_v1" &&
        typeof api.loadAllViewsFromEnvelope === "function"
          ? api.loadAllViewsFromEnvelope(parsed.envelope, getJSON)
          : api.loadFabricPayload(parsed.fabricPayload, getJSON);

      loadPromise
        .then(function () {
          if (api.getLastLoadError()) {
            setError(api.getLastLoadError());
            return;
          }
          if (typeof api.refreshGarmentLayer === "function") {
            api.refreshGarmentLayer();
          }
          setReady();
        })
        .catch(function () {
          setError(
            api.getLastLoadError() ||
              "Could not load this design. Saving is blocked so the original is not overwritten."
          );
        });

      return JSON.parse(JSON.stringify(parsed.envelope));
    },

    getActiveView: function () {
      var api = canvasApi();
      return api && typeof api.getActiveView === "function"
        ? api.getActiveView()
        : "front";
    },

    /** Stage O.1 dual-side: store inactive view Fabric payload without switching. */
    setStoredViewPayload: function (viewId, fabricPayload) {
      var api = canvasApi();
      if (!api || typeof api.setStoredViewPayload !== "function") {
        return { ok: false, reason: "Editor is not available." };
      }
      return api.setStoredViewPayload(viewId, fabricPayload);
    },

    setActiveView: function (id) {
      var api = canvasApi();
      if (!api || typeof api.setActiveView !== "function") {
        return Promise.resolve({ ok: false, reason: "Editor is not available." });
      }
      return api.setActiveView(id);
    },

    onViewChange: function (cb) {
      var api = canvasApi();
      if (!api || typeof api.onViewChange !== "function") {
        return function () {};
      }
      return api.onViewChange(cb);
    },

    getActiveCanvasJSON: function () {
      var api = canvasApi();
      if (!api || typeof api.getActiveCanvasJSON !== "function") {
        return getJSON();
      }
      return JSON.parse(JSON.stringify(api.getActiveCanvasJSON()));
    },

    getGarmentState: function () {
      var api = canvasApi();
      if (!api || typeof api.getGarmentState !== "function") {
        return { template: "tee", color: "white" };
      }
      return api.getGarmentState();
    },

    setGarmentState: function (next) {
      var api = canvasApi();
      if (!api || typeof api.setGarmentState !== "function") {
        return { ok: false, reason: "Editor is not available." };
      }
      return api.setGarmentState(next);
    },

    onGarmentChange: function (cb) {
      var api = canvasApi();
      if (!api || typeof api.onGarmentChange !== "function") {
        return function () {};
      }
      return api.onGarmentChange(cb);
    },

    /**
     * PNG data-URL of the workspace.
     * @param {{view?: 'front'|'back', includeGarment?: boolean}|undefined} opts
     *   With no opts: sync, active view, artwork only (legacy).
     *   With view / includeGarment: may return a Promise<data-URL>.
     */
    getPreviewPNG: function (opts) {
      var fallback =
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
      var api = canvasApi();
      if (!api) {
        return opts ? Promise.resolve(fallback) : fallback;
      }
      api.ensureCanvas(getJSON);
      if (typeof api.getPreviewPNG === "function") {
        return api.getPreviewPNG(opts);
      }
      var canvas = api.getFabricCanvas && api.getFabricCanvas();
      if (!canvas) {
        return opts ? Promise.resolve(fallback) : fallback;
      }
      var url = canvas.toDataURL({
        format: "png",
        multiplier: 1,
        enableRetinaScaling: false,
      });
      return opts ? Promise.resolve(url) : url;
    },

    /**
     * Submit mock-up from a frozen envelope + garment snapshot.
     * Does not load that JSON into the live editor.
     * @param {{envelope: object, view: string, garment?: {template?: string, color?: string}}} opts
     * @returns {Promise<string>}
     */
    renderFrozenPreview: function (opts) {
      var api = canvasApi();
      if (!api || typeof api.renderFrozenPreview !== "function") {
        return Promise.reject(new Error("Could not create preview. Please try again."));
      }
      return api.renderFrozenPreview(opts);
    },

    onCommittedChange: function (cb) {
      if (typeof cb === "function") {
        commitListeners.push(cb);
      }
      return function unsubscribe() {
        var idx = commitListeners.indexOf(cb);
        if (idx >= 0) commitListeners.splice(idx, 1);
      };
    },

    getLoadState: function () {
      return loadState;
    },

    isReady: function () {
      return loadState === "ready" && !persistBlocked;
    },

    canPersist: function () {
      return loadState === "ready" && !persistBlocked;
    },

    getPersistBlockReason: function () {
      if (loadState === "loading") return "Design is still loading…";
      if (persistBlocked) return persistBlockReason || "Saving is currently blocked.";
      return "";
    },

    whenReady: function () {
      return readyPromise;
    },

    /**
     * Build a Save/Submit payload only when safe.
     * @returns {{ok: boolean, json?: object, jsonString?: string, byteLength?: number, error?: string}}
     */
    preparePersistPayload: function () {
      if (!BlytzEditor.canPersist()) {
        return {
          ok: false,
          error: BlytzEditor.getPersistBlockReason() || "Design is not ready to save.",
        };
      }
      // Never persist an in-progress curve preview (Apply not chosen).
      if (
        global.BlytzEditorProps &&
        typeof global.BlytzEditorProps.discardCurvePreview === "function"
      ) {
        global.BlytzEditorProps.discardCurvePreview();
      }
      var api = canvasApi();
      var json = getJSON();
      var jsonString = JSON.stringify(json);
      var byteLength = api
        ? api.utf8ByteLength(jsonString)
        : jsonString.length;
      var maxBytes = api ? api.MAX_CANVAS_JSON_BYTES : 2 * 1024 * 1024;
      if (byteLength > maxBytes) {
        return {
          ok: false,
          error:
            "This design is too large to save (" +
            Math.ceil(byteLength / 1024) +
            " KB). Remove or use smaller images (max about " +
            Math.floor(maxBytes / 1024) +
            " KB total) and try again.",
          byteLength: byteLength,
        };
      }
      return { ok: true, json: json, jsonString: jsonString, byteLength: byteLength };
    },

    /**
     * Validate a Blytz schema_version 1 envelope for suggestion apply.
     * Does not mutate the canvas.
     * @returns {{ok: boolean, error?: string, envelope?: object}}
     */
    validateCanvasJSON: function (json) {
      var api = canvasApi();
      if (!api) {
        return { ok: false, error: "Editor is not available." };
      }
      if (typeof json === "string") {
        try {
          json = JSON.parse(json);
        } catch (e) {
          return { ok: false, error: "Suggestion JSON is invalid." };
        }
      }
      if (!json || typeof json !== "object" || Array.isArray(json)) {
        return { ok: false, error: "Suggestion must be a canvas object." };
      }
      if (json.schema_version !== 1) {
        return { ok: false, error: "Suggestion must use schema_version 1." };
      }
      if (!json.canvas || typeof json.canvas !== "object" || Array.isArray(json.canvas)) {
        return { ok: false, error: "Suggestion is missing a valid canvas payload." };
      }
      if (!Array.isArray(json.canvas.objects)) {
        return { ok: false, error: "Suggestion canvas.objects must be an array." };
      }
      var parsed = api.parseInput(json);
      if (!parsed.ok || parsed.blockPersist || parsed.kind !== "blytz_v1") {
        return {
          ok: false,
          error: parsed.message || "Suggestion failed validation.",
        };
      }
      // AI candidates must not carry a views key (active-view only).
      if (Object.prototype.hasOwnProperty.call(json, "views")) {
        return {
          ok: false,
          error: "Suggestion must not include a views key. Please retry.",
        };
      }
      // Shared safety scan (identical rules to apps/designs/canvas_safety.py).
      if (typeof api.scanCanvasPayload === "function") {
        var scanned = api.scanCanvasPayload(parsed.envelope);
        if (!scanned.ok) {
          return {
            ok: false,
            error: (scanned.reason || "Suggestion failed safety checks.") + " Please retry.",
          };
        }
      } else if (typeof api.validateObjectsAllowlist === "function") {
        var allowed = api.validateObjectsAllowlist(json.canvas.objects);
        if (!allowed.ok) {
          return { ok: false, error: allowed.error };
        }
      }
      return { ok: true, envelope: parsed.envelope, fabricPayload: parsed.fabricPayload };
    },

    /**
     * Safely replace the working canvas with validated schema v1 JSON.
     * Snapshots the current design and restores it if the load fails.
     * Unlike loadCanvasJSON, a failed replace does not permanently block persist
     * when the snapshot can be restored.
     * Does not fire onCommittedChange (loads suppress commit notifications).
     * @returns {Promise<{ok: boolean, error?: string, restored?: boolean}>}
     */
    applyCanvasJSON: function (json) {
      return safeReplaceCanvas(json, {
        failMessage: "Could not apply that design. Your previous design was restored.",
        dualFailMessage:
          "Apply failed and the previous design could not be restored. Reload the page.",
      });
    },

    /**
     * Preview a candidate design on the working canvas (Stage 2).
     * Same safety as applyCanvasJSON: validate → snapshot → load → restore on failure.
     * Previewing is not a committed edit; onCommittedChange still only fires on real edits.
     * @returns {Promise<{ok: boolean, error?: string, restored?: boolean}>}
     */
    previewCanvasJSON: function (json) {
      return safeReplaceCanvas(json, {
        failMessage:
          "Could not preview that candidate. Your previous design was restored.",
        dualFailMessage:
          "Preview failed and the previous design could not be restored. Reload the page.",
      });
    },

    /** Additive: undo last committed edit (phone chrome). */
    undo: function () {
      var api = canvasApi();
      if (!api || typeof api.undo !== "function") return Promise.resolve(false);
      return Promise.resolve(api.undo()).then(function (result) {
        notifyHistoryNavigate("undo", result);
        return result;
      });
    },

    /** Additive: redo previously undone edit. */
    redo: function () {
      var api = canvasApi();
      if (!api || typeof api.redo !== "function") return Promise.resolve(false);
      return Promise.resolve(api.redo()).then(function (result) {
        notifyHistoryNavigate("redo", result);
        return result;
      });
    },

    canUndo: function () {
      var api = canvasApi();
      return !!(api && api.canUndo && api.canUndo());
    },

    canRedo: function () {
      var api = canvasApi();
      return !!(api && api.canRedo && api.canRedo());
    },

    /**
     * Subscribe to completed undo/redo navigations (after canvas restore).
     * Used by Stage G save-state to recompute dirty vs last saved snapshot.
     * @returns {function(): void} unsubscribe
     */
    onHistoryNavigate: function (cb) {
      if (typeof cb === "function") {
        historyNavigateListeners.push(cb);
      }
      return function unsubscribe() {
        var idx = historyNavigateListeners.indexOf(cb);
        if (idx >= 0) historyNavigateListeners.splice(idx, 1);
      };
    },

    get _commitListeners() {
      return commitListeners;
    },
  };

  global.BlytzEditor = BlytzEditor;

  document.addEventListener("DOMContentLoaded", function () {
    if (pageInitialized) return;
    pageInitialized = true;
    var api = canvasApi();
    if (!api) return;
    api.ensureCanvas(getJSON);
    api.wireTools(getJSON);
    syncDomState();
  });
})(window);
