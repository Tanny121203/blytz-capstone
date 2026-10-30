/**
 * Blytz Stage O — AI Assistant (two candidates via Gemini when configured).
 * Stage 2 mock remains as offline/demo fallback when live AI is disabled.
 * Two candidates per turn · live canvas preview · commit on first real edit.
 * Canvas changes go only through BlytzEditor. Never hard-code API keys.
 */
(function (global) {
  "use strict";

  var MOCK_DELAY_MS = 450;
  var CANDIDATES_PER_TURN = 2;
  var STARTER_PROMPTS = [
    "Bold wordmark across the chest",
    "Minimal monogram in the corner",
    "Sporty number badge",
  ];

  var state = {
    busy: false,
    switching: false,
    requestId: 0,
    previewSeq: 0,
    turnId: 0,
    candidates: [],
    activeCandidateId: null,
    committed: false,
    commitUnsub: null,
    history: [],
  };

  function textSafe(text) {
    return String(text == null ? "" : text);
  }

  function deepClone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null && text !== "") node.textContent = textSafe(text);
    return node;
  }

  function clearChildren(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function thumbDataUrl(label, accent) {
    var safe = textSafe(label).slice(0, 18).replace(/[<>&]/g, "");
    var svg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160">' +
      '<rect width="160" height="160" fill="#fafafa"/>' +
      '<rect x="12" y="12" width="136" height="136" fill="#fff" stroke="#e5e5e5"/>' +
      '<circle cx="80" cy="64" r="28" fill="' +
      accent +
      '" opacity="0.25"/>' +
      '<text x="80" y="120" text-anchor="middle" font-family="Georgia,serif" font-size="11" fill="#0a0a0a">' +
      safe +
      "</text></svg>";
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  }

  function makeEnvelope(objects) {
    return {
      schema_version: 1,
      width: 800,
      height: 800,
      canvas: {
        version: "6.6.1",
        objects: objects,
      },
    };
  }

  function iTextObject(opts) {
    return {
      type: "IText",
      version: "6.6.1",
      left: opts.left,
      top: opts.top,
      width: opts.width || 200,
      height: 36,
      fill: opts.fill || "#0a0a0a",
      text: opts.text,
      fontSize: opts.fontSize || 36,
      fontFamily: opts.fontFamily || "Georgia, 'Times New Roman', serif",
      fontWeight: opts.fontWeight || "normal",
      textAlign: opts.textAlign || "left",
      originX: "left",
      originY: "top",
      selectable: true,
      evented: true,
      opacity: 1,
      visible: true,
      scaleX: 1,
      scaleY: 1,
      angle: opts.angle || 0,
    };
  }

  function rectObject(opts) {
    return {
      type: "Rect",
      version: "6.6.1",
      left: opts.left,
      top: opts.top,
      width: opts.width,
      height: opts.height,
      fill: opts.fill,
      stroke: opts.stroke || null,
      strokeWidth: opts.strokeWidth || 0,
      rx: opts.rx || 0,
      ry: opts.ry || 0,
      originX: "left",
      originY: "top",
      selectable: true,
      evented: true,
      opacity: opts.opacity == null ? 1 : opts.opacity,
      visible: true,
      scaleX: 1,
      scaleY: 1,
      angle: 0,
    };
  }

  /** Deterministic fingerprint so tests can see which canvas context fed the mock. */
  function contextFingerprint(contextJSON) {
    try {
      var env = contextJSON && typeof contextJSON === "object" ? contextJSON : null;
      var objects =
        env && env.canvas && Array.isArray(env.canvas.objects) ? env.canvas.objects : [];
      var firstText = "";
      for (var i = 0; i < objects.length; i++) {
        if (objects[i] && typeof objects[i].text === "string" && objects[i].text) {
          firstText = objects[i].text;
          break;
        }
      }
      return {
        objectCount: objects.length,
        firstText: firstText.slice(0, 24),
        schema: env && env.schema_version === 1 ? 1 : 0,
      };
    } catch (e) {
      return { objectCount: 0, firstText: "", schema: 0 };
    }
  }

  function buildMockSuggestions(prompt, contextJSON) {
    var base = textSafe(prompt).trim() || "Design";
    var short = base.length > 24 ? base.slice(0, 24) + "…" : base;
    var fp = contextFingerprint(contextJSON);
    var ctxNote =
      "ctx:" + fp.objectCount + (fp.firstText ? ":" + fp.firstText : ":empty");

    var list = [
      {
        id: "mock-wordmark",
        label: "Bold wordmark",
        description: "Local demo: large centered title. (" + ctxNote + ")",
        thumb: thumbDataUrl("Wordmark", "#0a0a0a"),
        canvasJSON: makeEnvelope([
          iTextObject({
            left: 120,
            top: 340,
            text: short.toUpperCase(),
            fontSize: 42,
            fontWeight: "bold",
            width: 560,
            textAlign: "center",
          }),
        ]),
      },
      {
        id: "mock-monogram",
        label: "Corner monogram",
        description: "Local demo: small mark in the upper-left. (" + ctxNote + ")",
        thumb: thumbDataUrl("Monogram", "#c9a227"),
        canvasJSON: makeEnvelope([
          rectObject({
            left: 48,
            top: 48,
            width: 72,
            height: 72,
            fill: "#f7f1de",
            stroke: "#c9a227",
            strokeWidth: 2,
            rx: 8,
            ry: 8,
          }),
          iTextObject({
            left: 60,
            top: 68,
            text: (short.charAt(0) || "B").toUpperCase(),
            fontSize: 36,
            fontWeight: "bold",
            fill: "#0a0a0a",
            width: 48,
            textAlign: "center",
          }),
        ]),
      },
    ];

    // Independent mutable copies for each candidate.
    return list.map(function (item) {
      return {
        id: item.id,
        label: item.label,
        description: item.description,
        thumb: item.thumb,
        canvasJSON: deepClone(item.canvasJSON),
        contextNote: ctxNote,
      };
    });
  }

  /**
   * Replaceable mock adapter — accepts prompt + canvas context for multi-turn.
   * @param {string} prompt
   * @param {object|null} contextJSON Blytz schema v1 envelope
   * @returns {Promise<{ok: boolean, message?: string, suggestions?: array, error?: string, contextNote?: string}>}
   */
  function mockAssistantRespond(prompt, contextJSON) {
    var trimmed = textSafe(prompt).trim();
    return new Promise(function (resolve) {
      global.setTimeout(function () {
        if (/fail|error|timeout/i.test(trimmed)) {
          resolve({
            ok: false,
            code: "mock_error",
            error:
              "Mock assistant failure (demo). Retry, or try a different prompt without “fail”/“error”.",
          });
          return;
        }
        var suggestions = buildMockSuggestions(trimmed, contextJSON);
        var fp = contextFingerprint(contextJSON);
        resolve({
          ok: true,
          source: "mock",
          contextNote: suggestions[0] && suggestions[0].contextNote,
          message:
            "Here are two local demo candidates for “" +
            trimmed +
            "” (context objects: " +
            fp.objectCount +
            "). These are not from a live AI model. Select either option to preview it on the canvas. The first real edit keeps that option and discards the other.",
          suggestions: suggestions,
        });
      }, MOCK_DELAY_MS);
    });
  }

  function getCookie(name) {
    var match = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
    );
    return match ? decodeURIComponent(match[1]) : "";
  }

  function getEditorShell() {
    return document.querySelector("[data-editor-page]");
  }

  function getSuggestUrl() {
    var shell = getEditorShell();
    return (shell && shell.getAttribute("data-ai-suggest-url")) || "";
  }

  function isLiveAiEnabled() {
    var shell = getEditorShell();
    return !!(shell && shell.getAttribute("data-ai-suggest-enabled") === "1");
  }

  function getActiveSide() {
    try {
      if (global.BlytzEditor && typeof global.BlytzEditor.getActiveView === "function") {
        var view = global.BlytzEditor.getActiveView();
        return view === "back" ? "back" : "front";
      }
    } catch (e) {
      /* ignore */
    }
    return "front";
  }

  /**
   * Live Gemini suggest via design-scoped POST. Falls back to mock when AI is disabled.
   * @returns {Promise<{ok: boolean, message?: string, suggestions?: array, error?: string, code?: string, source?: string}>}
   */
  function liveAssistantRespond(prompt, contextJSON) {
    var url = getSuggestUrl();
    if (!url || !isLiveAiEnabled()) {
      return mockAssistantRespond(prompt, contextJSON);
    }

    var csrf = getCookie("csrftoken");
    return global
      .fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify(
          (function () {
            var garment = { template: "", color: "" };
            try {
              if (
                global.BlytzEditor &&
                typeof global.BlytzEditor.getGarmentState === "function"
              ) {
                garment = global.BlytzEditor.getGarmentState() || garment;
              }
            } catch (eG) {
              /* ignore */
            }
            return {
              message: textSafe(prompt).trim(),
              canvas_json: contextJSON || {},
              active_side: getActiveSide(),
              garment_template: garment.template || "",
              garment_color: garment.color || "",
            };
          })()
        ),
      })
      .then(function (resp) {
        return resp.json().then(
          function (data) {
            return { httpStatus: resp.status, data: data || {} };
          },
          function () {
            return {
              httpStatus: resp.status,
              data: {
                ok: false,
                error: "AI response was unreadable. Please retry.",
                code: "bad_response",
              },
            };
          }
        );
      })
      .then(function (pack) {
        var data = pack.data;
        if (pack.httpStatus === 429 || data.code === "rate_limited") {
          return {
            ok: false,
            code: "rate_limited",
            error:
              data.error ||
              "AI suggestion rate limit reached. Try again later, or edit manually.",
          };
        }
        if (pack.httpStatus === 503 || data.code === "ai_unavailable") {
          return {
            ok: false,
            code: "ai_unavailable",
            error:
              data.error ||
              "AI suggestions are unavailable right now. Manual editing is still available.",
          };
        }
        if (!data.ok) {
          return {
            ok: false,
            code: data.code || "ai_error",
            error: data.error || "Could not generate AI candidates. Please retry.",
          };
        }
        return {
          ok: true,
          source: "gemini",
          message: data.message,
          suggestions: data.suggestions,
        };
      })
      .catch(function () {
        return {
          ok: false,
          code: "network",
          error: "Network error talking to AI. Check your connection and retry.",
        };
      });
  }

  function assistantRespond(prompt, contextJSON) {
    return liveAssistantRespond(prompt, contextJSON);
  }

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function getRoots() {
    return {
      panel: document.getElementById("ai-assistant"),
      messages: qs("[data-ai-messages]"),
      form: qs("[data-ai-form]"),
      input: qs("[data-ai-input]"),
      send: qs("[data-ai-send]"),
      status: qs("[data-ai-status]"),
      empty: qs("[data-ai-empty]"),
      turn: qs("[data-ai-turn]"),
    };
  }

  function setStatus(msg) {
    var roots = getRoots();
    if (roots.status) roots.status.textContent = msg || "";
  }

  function syncControls() {
    var roots = getRoots();
    var locked = state.busy || state.switching;
    if (roots.send) roots.send.disabled = locked;
    if (roots.input) roots.input.disabled = locked;
  }

  function setBusy(busy) {
    state.busy = !!busy;
    syncControls();
  }

  function appendMessage(role, text) {
    var roots = getRoots();
    if (!roots.messages) return;
    if (roots.empty) roots.empty.classList.add("hidden");

    var row = el(
      "div",
      role === "user" ? "flex justify-end" : "flex justify-start"
    );
    var bubble = el(
      "div",
      role === "user"
        ? "max-w-[90%] rounded-md bg-ink px-3 py-2 text-sm text-canvas"
        : "max-w-[90%] rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink"
    );
    bubble.textContent = textSafe(text);
    row.appendChild(bubble);
    roots.messages.appendChild(row);
    roots.messages.scrollTop = roots.messages.scrollHeight;
    state.history.push({ role: role, text: textSafe(text) });
  }

  function editorReady() {
    return !!(
      global.BlytzEditor &&
      typeof global.BlytzEditor.canPersist === "function" &&
      global.BlytzEditor.canPersist()
    );
  }

  function captureContextCanvas() {
    // Active-view only for AI context (B1); full envelope is for Save/Submit.
    try {
      if (
        global.BlytzEditor &&
        typeof global.BlytzEditor.getActiveCanvasJSON === "function"
      ) {
        return deepClone(global.BlytzEditor.getActiveCanvasJSON());
      }
      if (!global.BlytzEditor || typeof global.BlytzEditor.getCanvasJSON !== "function") {
        return null;
      }
      return deepClone(global.BlytzEditor.getCanvasJSON());
    } catch (e) {
      return null;
    }
  }

  function clearTurnUi() {
    var roots = getRoots();
    if (roots.turn) {
      clearChildren(roots.turn);
      roots.turn.classList.add("hidden");
    }
  }

  function discardCandidates(keepId) {
    state.previewSeq += 1;
    if (keepId) {
      state.candidates = state.candidates.filter(function (c) {
        return c.id === keepId;
      });
      state.activeCandidateId = keepId;
    } else {
      state.candidates = [];
      state.activeCandidateId = null;
    }
  }

  function renderTurnPanel() {
    var roots = getRoots();
    if (!roots.turn) return;
    clearChildren(roots.turn);

    if (!state.candidates.length) {
      roots.turn.classList.add("hidden");
      return;
    }

    roots.turn.classList.remove("hidden");
    var title = el(
      "p",
      "text-xs font-medium uppercase tracking-wide text-ink-subtle",
      state.committed ? "Kept candidate" : "Candidates (preview freely)"
    );
    roots.turn.appendChild(title);

    // Layout via [data-ai-candidates] in responsive.css (stack mobile, side-by-side desktop).
    var grid = el("div", "mt-2");
    grid.setAttribute("data-ai-candidates", "");
    state.candidates.forEach(function (cand) {
      var active = cand.id === state.activeCandidateId;
      var btn = el(
        "button",
        "flex flex-col items-stretch rounded-md border p-2 text-left text-xs transition " +
          (active
            ? "border-ink bg-surface ring-1 ring-ink"
            : "border-border bg-canvas hover:bg-surface") +
          (state.committed && !active ? " opacity-40" : "")
      );
      btn.type = "button";
      btn.setAttribute("data-ai-candidate", cand.id);
      btn.disabled = state.committed || state.switching || state.busy;
      if (state.committed && !active) {
        btn.disabled = true;
      }

      var img = el("img", "mb-2 h-14 w-full rounded border border-border object-cover bg-surface");
      img.alt = "";
      img.src = cand.thumb || thumbDataUrl(cand.label || "Option", "#e5e5e5");
      btn.appendChild(img);
      btn.appendChild(el("span", "font-medium text-ink", cand.label || "Option"));
      btn.appendChild(
        el(
          "span",
          "mt-0.5 text-[10px] text-ink-muted",
          state.committed && active
            ? "Committed — edit freely"
            : active
              ? "Previewing"
              : "Select to preview"
        )
      );

      btn.addEventListener("click", function () {
        selectCandidate(cand.id);
      });
      grid.appendChild(btn);
    });
    roots.turn.appendChild(grid);

    if (!state.committed) {
      roots.turn.appendChild(
        el(
          "p",
          "mt-2 text-[11px] text-ink-subtle",
          "Selecting only previews. Drag, resize, rotate, recolor, add, or delete to keep this option and discard the other."
        )
      );
    }
  }

  function validateCandidateSet(suggestions) {
    if (!suggestions || !Array.isArray(suggestions)) {
      return { ok: false, error: "Demo response was incomplete. Please retry." };
    }
    if (suggestions.length !== CANDIDATES_PER_TURN) {
      return {
        ok: false,
        error:
          "Demo response did not include exactly two valid candidates. Please retry.",
      };
    }
    if (!global.BlytzEditor || !global.BlytzEditor.validateCanvasJSON) {
      return { ok: false, error: "Canvas validation is unavailable." };
    }
    var clones = [];
    for (var i = 0; i < suggestions.length; i++) {
      var sug = suggestions[i];
      if (!sug || !sug.canvasJSON) {
        return { ok: false, error: "A demo candidate was missing canvas data." };
      }
      var validated = global.BlytzEditor.validateCanvasJSON(sug.canvasJSON);
      if (!validated.ok) {
        return {
          ok: false,
          error: validated.error || "A demo candidate failed validation.",
        };
      }
      var entry = {
        id: sug.id || "candidate-" + i,
        label: sug.label || "Option " + (i + 1),
        description: sug.description || "",
        thumb: sug.thumb,
        canvasJSON: deepClone(sug.canvasJSON),
        contextNote: sug.contextNote || "",
      };
      if (sug.otherSideCanvasJSON) {
        var otherValidated = global.BlytzEditor.validateCanvasJSON(
          sug.otherSideCanvasJSON
        );
        if (otherValidated.ok) {
          entry.otherSideCanvasJSON = deepClone(sug.otherSideCanvasJSON);
          entry.other_side = sug.other_side || "";
        }
      }
      clones.push(entry);
    }
    // Ensure unique ids
    var seen = {};
    for (var j = 0; j < clones.length; j++) {
      if (seen[clones[j].id]) clones[j].id = clones[j].id + "-" + j;
      seen[clones[j].id] = true;
    }
    return { ok: true, candidates: clones };
  }

  function selectCandidate(candidateId) {
    if (state.committed || state.busy || state.switching) return;
    var cand = null;
    for (var i = 0; i < state.candidates.length; i++) {
      if (state.candidates[i].id === candidateId) {
        cand = state.candidates[i];
        break;
      }
    }
    if (!cand) return;
    if (state.activeCandidateId === candidateId && !state.switching) {
      renderTurnPanel();
      return;
    }
    if (!editorReady()) {
      setStatus(
        (global.BlytzEditor && global.BlytzEditor.getPersistBlockReason()) ||
          "Canvas is not ready to preview."
      );
      return;
    }
    if (!global.BlytzEditor.previewCanvasJSON) {
      setStatus("Canvas preview is unavailable.");
      return;
    }

    var turnAtStart = state.turnId;
    var seq = ++state.previewSeq;
    state.switching = true;
    syncControls();
    setStatus("Loading preview…");
    renderTurnPanel();

    global.BlytzEditor
      .previewCanvasJSON(cand.canvasJSON)
      .then(function (result) {
        if (seq !== state.previewSeq || turnAtStart !== state.turnId || state.committed) {
          return;
        }
        if (result && result.ok) {
          state.activeCandidateId = cand.id;
          setStatus("Previewing “" + cand.label + "”. Edit to keep it.");
        } else {
          setStatus((result && result.error) || "Preview failed.");
          appendMessage(
            "assistant",
            (result && result.error) || "Could not preview that candidate."
          );
        }
      })
      .catch(function () {
        if (seq !== state.previewSeq || turnAtStart !== state.turnId) return;
        setStatus("Preview failed.");
        appendMessage("assistant", "Could not preview that candidate.");
      })
      .finally(function () {
        if (seq === state.previewSeq) {
          state.switching = false;
          syncControls();
          renderTurnPanel();
        }
      });
  }

  function applyOtherSideIfPresent(cand) {
    if (!cand || !cand.otherSideCanvasJSON) return;
    if (!global.BlytzEditor || typeof global.BlytzEditor.setStoredViewPayload !== "function") {
      return;
    }
    var otherSide = cand.other_side;
    if (otherSide !== "front" && otherSide !== "back") {
      otherSide = getActiveSide() === "front" ? "back" : "front";
    }
    var fabricPayload =
      cand.otherSideCanvasJSON.canvas || cand.otherSideCanvasJSON;
    try {
      global.BlytzEditor.setStoredViewPayload(otherSide, fabricPayload);
    } catch (eApply) {
      /* non-fatal: active side already committed */
    }
  }

  function onCanvasCommitted() {
    if (state.committed) return;
    if (!state.candidates.length) return;
    if (state.switching || state.busy) return;
    if (!state.activeCandidateId) return;

    var kept = null;
    for (var i = 0; i < state.candidates.length; i++) {
      if (state.candidates[i].id === state.activeCandidateId) {
        kept = state.candidates[i];
        break;
      }
    }
    applyOtherSideIfPresent(kept);

    state.committed = true;
    state.previewSeq += 1;
    var keptId = state.activeCandidateId;
    discardCandidates(keptId);
    renderTurnPanel();
    setStatus("Candidate kept. Other options discarded. Save when you are ready.");
    appendMessage(
      "assistant",
      kept && kept.otherSideCanvasJSON
        ? "Kept the active candidate (and applied the matching other side). The other option was discarded."
        : "Kept the active candidate after your edit. The other option was discarded. Send another message anytime to refine."
    );
  }

  function ensureCommitListener() {
    if (state.commitUnsub) return;
    if (!global.BlytzEditor || typeof global.BlytzEditor.onCommittedChange !== "function") {
      return;
    }
    state.commitUnsub = global.BlytzEditor.onCommittedChange(function () {
      onCanvasCommitted();
    });
  }

  function beginTurnWithCandidates(candidates) {
    state.turnId += 1;
    state.committed = false;
    state.candidates = candidates;
    state.activeCandidateId = null;
    state.previewSeq += 1;
    ensureCommitListener();
    renderTurnPanel();
  }

  function sendPrompt(raw, options) {
    options = options || {};
    var prompt = textSafe(raw).trim();
    if (!prompt) {
      setStatus("Enter a prompt to continue.");
      return;
    }
    if (state.busy || state.switching) return;

    var contextJSON = captureContextCanvas();
    var requestId = ++state.requestId;

    setBusy(true);
    setStatus(isLiveAiEnabled() ? "Asking AI…" : "Thinking…");
    if (!options.isRetry) {
      appendMessage("user", prompt);
    }
    // New prompt discards prior uncommitted alternatives (context already captured).
    // Next-turn context: previewed candidate if uncommitted, else live canvas after commit.
    discardCandidates(null);
    state.committed = false;
    clearTurnUi();

    var roots = getRoots();
    if (roots.input) roots.input.value = "";

    assistantRespond(prompt, contextJSON)
      .then(function (result) {
        if (requestId !== state.requestId) return;

        if (!result || !result.ok) {
          var errText =
            (result && result.error) ||
            "Something went wrong generating candidates.";
          appendMessage("assistant", errText);
          renderRetry(prompt);
          if (result && result.code === "rate_limited") {
            setStatus("Rate limit reached. Manual editing is still available.");
          } else if (result && result.code === "ai_unavailable") {
            setStatus("AI unavailable. Manual editing is still available.");
          } else {
            setStatus("Request failed. Manual editing is still available.");
          }
          return;
        }

        var checked = validateCandidateSet(result.suggestions);
        if (!checked.ok) {
          appendMessage("assistant", checked.error);
          renderRetry(prompt);
          setStatus("Invalid candidates. Please retry.");
          return;
        }

        appendMessage(
          "assistant",
          result.message || "Here are two candidates."
        );
        beginTurnWithCandidates(checked.candidates);
        setStatus("Select a candidate to preview on the canvas.");
        // Unlock send before preview load so selectCandidate is not blocked by busy.
        setBusy(false);
        // Auto-preview the first candidate so the canvas reflects the turn.
        selectCandidate(checked.candidates[0].id);
      })
      .catch(function () {
        if (requestId !== state.requestId) return;
        appendMessage("assistant", "Unexpected error. Please retry.");
        renderRetry(prompt);
        setStatus("Request failed.");
        setBusy(false);
      })
      .finally(function () {
        if (requestId === state.requestId && state.busy) {
          setBusy(false);
        }
      });
  }

  function renderRetry(prompt) {
    var roots = getRoots();
    if (!roots.messages) return;
    var row = el("div", "flex justify-start");
    var btn = el(
      "button",
      "inline-flex min-h-9 items-center rounded-md border border-border-strong bg-canvas px-3 text-xs font-medium text-ink hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink",
      "Retry"
    );
    btn.type = "button";
    btn.addEventListener("click", function () {
      if (state.busy || state.switching) return;
      sendPrompt(prompt, { isRetry: true });
    });
    row.appendChild(btn);
    roots.messages.appendChild(row);
    roots.messages.scrollTop = roots.messages.scrollHeight;
  }

  function openMobileAssistant() {
    var panel = document.getElementById("ai-assistant");
    var backdrop = document.getElementById("ai-assistant-backdrop");
    if (!panel) return;
    panel.classList.add("is-open");
    panel.setAttribute("aria-hidden", "false");
    if (backdrop) backdrop.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
  }

  function closeMobileAssistant() {
    var panel = document.getElementById("ai-assistant");
    var backdrop = document.getElementById("ai-assistant-backdrop");
    if (!panel) return;
    panel.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
    if (backdrop) backdrop.classList.add("hidden");
    if (!document.querySelector("[data-drawer]:not(.hidden)")) {
      document.body.classList.remove("overflow-hidden");
    }
  }

  function wireUi() {
    var roots = getRoots();
    if (!panelReady(roots)) return;

    document.querySelectorAll("[data-ai-starter]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var prompt = btn.getAttribute("data-ai-starter") || btn.textContent;
        if (roots.input) roots.input.value = prompt;
        sendPrompt(prompt);
      });
    });

    roots.form.addEventListener("submit", function (e) {
      e.preventDefault();
      sendPrompt(roots.input.value);
    });

    roots.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendPrompt(roots.input.value);
      }
    });

    document.querySelectorAll("[data-ai-open]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        openMobileAssistant();
      });
    });
    document.querySelectorAll("[data-ai-close]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        closeMobileAssistant();
      });
    });
    var backdrop = document.getElementById("ai-assistant-backdrop");
    if (backdrop) {
      backdrop.addEventListener("click", closeMobileAssistant);
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        closeMobileAssistant();
      }
    });

    ensureCommitListener();
  }

  function panelReady(roots) {
    return !!(roots.panel && roots.form && roots.input);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("ai-assistant")) return;
    wireUi();
  });

  global.BlytzAIChat = {
    mockAssistantRespond: mockAssistantRespond,
    assistantRespond: assistantRespond,
    liveAssistantRespond: liveAssistantRespond,
    sendPrompt: sendPrompt,
    buildMockSuggestions: buildMockSuggestions,
    contextFingerprint: contextFingerprint,
    isLiveAiEnabled: isLiveAiEnabled,
    CANDIDATES_PER_TURN: CANDIDATES_PER_TURN,
    getState: function () {
      return {
        busy: state.busy,
        switching: state.switching,
        committed: state.committed,
        activeCandidateId: state.activeCandidateId,
        candidateCount: state.candidates.length,
        candidateIds: state.candidates.map(function (c) {
          return c.id;
        }),
        /** True while candidates exist and the first real edit has not committed yet. */
        hasPendingCandidates: state.candidates.length > 0 && !state.committed,
      };
    },
    hasPendingCandidates: function () {
      return state.candidates.length > 0 && !state.committed;
    },
  };
})(window);
