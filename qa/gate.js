/**
 * Blytz Capstone — in-page GATE (console-pasteable).
 * Paste into DevTools on the editor page. Returns a plain result object.
 * Mutates nothing permanent. Self-contained.
 *
 * Usage: paste entire file, then: await blytzGate()
 * Or:    copy(JSON.stringify(await blytzGate(), null, 2))
 */
async function blytzGate(options) {
  options = options || {};
  var EXPECT = options.expect || null;
  var EXTRA = options.extraScripts || []; // e.g. ["editor_garments.js"]
  var NAMES = ["editor_canvas.js", "editor_tools.js", "editor_properties.js"].concat(EXTRA);

  async function sha256Hex(buf) {
    var dig = await crypto.subtle.digest("SHA-256", buf);
    return Array.prototype.map
      .call(new Uint8Array(dig), function (b) {
        return b.toString(16).padStart(2, "0");
      })
      .join("");
  }

  async function fetchHash(name) {
    var url = "/static/js/" + name + "?gate=" + Date.now();
    var res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      return { name: name, ok: false, error: "HTTP " + res.status, hex: null, len: 0 };
    }
    var buf = await res.arrayBuffer();
    var hex = await sha256Hex(buf);
    var expected = EXPECT && EXPECT[name];
    return {
      name: name,
      ok: expected ? hex === expected : true,
      hex: hex,
      len: buf.byteLength,
      expected: expected || null,
      match: expected ? hex === expected : null,
    };
  }

  var hashes = [];
  for (var i = 0; i < NAMES.length; i++) {
    hashes.push(await fetchHash(NAMES[i]));
  }

  var api = window.BlytzCanvas;
  var types = {
    runSilent: typeof (api && api.runSilent),
    reorderActive: typeof (api && api.reorderActive),
    canReorderActive: typeof (api && api.canReorderActive),
    typeKey: typeof (api && api.typeKey),
  };

  var loadErrors = window.__blytzLoadErrors || [];
  var consoleErrors = window.__blytzConsoleErrors || [];

  var abort = [];
  if (EXPECT) {
    var mismatch = hashes.filter(function (h) {
      return !h.ok;
    });
    if (mismatch.length) {
      abort.push("ABORT: served script sha256 mismatch: " + JSON.stringify(mismatch));
    }
  }
  var typeFail = Object.keys(types).filter(function (k) {
    return types[k] !== "function";
  });
  if (typeFail.length) {
    abort.push("ABORT: typeof not function: " + JSON.stringify(typeFail));
  }
  if (loadErrors.length) {
    abort.push("ABORT: page load errors: " + JSON.stringify(loadErrors));
  }
  if (consoleErrors.length) {
    abort.push("ABORT: console.error during/after load: " + JSON.stringify(consoleErrors));
  }

  var result = {
    ok: abort.length === 0,
    abort: abort,
    hashes: hashes,
    types: types,
    loadErrors: loadErrors,
    consoleErrors: consoleErrors,
    fabricVersion: (window.fabric && fabric.version) || null,
    fabricVersionOk: typeof (api && api.fabricVersionOk) === "boolean" ? api.fabricVersionOk : null,
    ready: !!(window.BlytzEditor && BlytzEditor.canPersist && BlytzEditor.canPersist()),
  };
  window.__blytzGate = result;
  if (!result.ok) {
    throw new Error(abort.join(" | "));
  }
  return result;
}

/**
 * Install load/console error collectors. Call BEFORE navigating if possible,
 * or paste early on the page. Safe to call multiple times.
 */
function blytzInstallErrorHooks() {
  if (window.__blytzHooksInstalled) return;
  window.__blytzHooksInstalled = true;
  window.__blytzLoadErrors = window.__blytzLoadErrors || [];
  window.__blytzConsoleErrors = window.__blytzConsoleErrors || [];
  window.addEventListener("error", function (e) {
    window.__blytzLoadErrors.push(String(e.message || e.type || "error"));
  });
  window.addEventListener("unhandledrejection", function (e) {
    window.__blytzLoadErrors.push(String(e.reason || "rejection"));
  });
  var orig = console.error;
  console.error = function () {
    try {
      window.__blytzConsoleErrors.push(
        Array.prototype.slice.call(arguments).map(String).join(" ")
      );
    } catch (err) {
      /* ignore */
    }
    return orig.apply(console, arguments);
  };
}

blytzInstallErrorHooks();
console.log("[blytzGate] ready — run: await blytzGate({ expect: { /* disk sha256 map */ } })");
