/**
 * Stage 3b measurement helpers — OUTSIDE repo (QA_SCRIPTS_IN_REPO=no).
 * Paste / evaluate in the live editor console or via CDP Runtime.evaluate.
 */
(function (global) {
  "use strict";

  function snap() {
    var wrap = document.getElementById("editor-canvas-wrap");
    var root = document.getElementById("editor-root");
    var shell = document.querySelector(".editor-shell");
    var panel = document.getElementById("editor-tool-panel");
    var wr = wrap ? wrap.getBoundingClientRect() : null;
    var pr = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
    var toolbar = document.getElementById("editor-toolbar");
    var tr = toolbar ? toolbar.getBoundingClientRect() : null;
    var btn = document.querySelector("#editor-toolbar [data-editor-action=\"elements\"]");
    var br = btn ? btn.getBoundingClientRect() : null;
    return {
      logical: window.BlytzCanvas ? BlytzCanvas.LOGICAL_SIZE : null,
      wrapW: wr ? Math.round(wr.width) : null,
      wrapH: wr ? Math.round(wr.height) : null,
      rootClientW: root ? root.clientWidth : null,
      rootClientH: root ? root.clientHeight : null,
      shellH: shell ? Math.round(shell.getBoundingClientRect().height) : null,
      scrollH: document.documentElement.scrollHeight,
      hOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      canPersist: !!(window.BlytzEditor && BlytzEditor.canPersist()),
      panelBox: pr
        ? {
            top: Math.round(pr.top),
            left: Math.round(pr.left),
            bottom: Math.round(pr.bottom),
            right: Math.round(pr.right),
            w: Math.round(pr.width),
            h: Math.round(pr.height),
          }
        : null,
      viewport: { w: window.innerWidth, h: window.innerHeight },
      toolbarBtn: br
        ? { w: Math.round(br.width), h: Math.round(br.height) }
        : null,
      panelToolbarOverlap:
        pr && tr
          ? !(pr.bottom <= tr.top || pr.top >= tr.bottom || pr.right <= tr.left || pr.left >= tr.right)
          : null,
      panelCoverPct:
        pr && root
          ? Math.round(
              ((pr.width * pr.height) / (root.clientWidth * root.clientHeight || 1)) * 100
            )
          : null,
    };
  }

  function installCommitCounter() {
    if (!global.__blytzCommitLog) {
      global.__blytzCommitLog = [];
      if (window.BlytzEditor && BlytzEditor.onCommittedChange) {
        BlytzEditor.onCommittedChange(function (label) {
          global.__blytzCommitLog.push({
            t: Date.now(),
            label: label || "commit",
            n: global.__blytzCommitLog.length + 1,
          });
        });
      }
    }
    global.__blytzCommitLog.length = 0;
    return global.__blytzCommitLog;
  }

  function commitCount() {
    return (global.__blytzCommitLog && global.__blytzCommitLog.length) || 0;
  }

  function makeImageFile(opts) {
    opts = opts || {};
    var type = opts.type || "image/png";
    var w = opts.w || 200;
    var h = opts.h || 200;
    var name = opts.name || "test.png";
    var targetBytes = opts.targetBytes || 0;
    var corrupt = !!opts.corrupt;

    if (corrupt) {
      var bad = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x01, 0x02, 0x03]);
      return new File([bad], name, { type: type });
    }

    if (type === "image/gif") {
      // Minimal GIF89a 1x1
      var gif = new Uint8Array([
        0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x21,
        0xf9, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2c, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00,
        0x01, 0x00, 0x00, 0x02, 0x02, 0x4c, 0x01, 0x00, 0x3b,
      ]);
      return new File([gif], name, { type: "image/gif" });
    }

    if (type === "image/svg+xml" || name.endsWith(".svg")) {
      var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>';
      return new File([svg], name, { type: "image/svg+xml" });
    }

    return new Promise(function (resolve) {
      var c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      var ctx = c.getContext("2d");
      ctx.fillStyle = opts.color || "#336699";
      ctx.fillRect(0, 0, w, h);
      // Noise to inflate size toward targetBytes
      if (targetBytes > 0) {
        var imgData = ctx.getImageData(0, 0, w, h);
        for (var i = 0; i < imgData.data.length; i += 4) {
          imgData.data[i] = (i * 17) % 256;
          imgData.data[i + 1] = (i * 31) % 256;
          imgData.data[i + 2] = (i * 47) % 256;
        }
        ctx.putImageData(imgData, 0, 0);
      }
      var mime = type === "image/jpeg" || type === "image/jpg" ? "image/jpeg" : type;
      var quality = mime === "image/jpeg" ? 0.92 : undefined;
      c.toBlob(
        function (blob) {
          if (!blob) {
            resolve(null);
            return;
          }
          if (targetBytes > 0 && blob.size < targetBytes) {
            // Pad with a custom chunk appended — may break decode for PNG.
            // Instead grow canvas until near target.
            resolve(new File([blob], name, { type: mime }));
            return;
          }
          resolve(new File([blob], name, { type: mime }));
        },
        mime,
        quality
      );
    });
  }

  /** Build near-max PNG by binary search on canvas size / quality pad. */
  async function makeNearMaxPng(maxBytes) {
    // Start large; shrink until <= maxBytes
    var w = 900;
    var h = 900;
    for (var attempt = 0; attempt < 40; attempt++) {
      var file = await makeImageFile({ type: "image/png", w: w, h: h, name: "max.png", targetBytes: 1 });
      if (!file) throw new Error("no file");
      if (file.size <= maxBytes && file.size > maxBytes * 0.9) return file;
      if (file.size > maxBytes) {
        w = Math.max(50, Math.floor(w * 0.92));
        h = Math.max(50, Math.floor(h * 0.92));
      } else {
        w = Math.floor(w * 1.05);
        h = Math.floor(h * 1.05);
      }
    }
    return makeImageFile({ type: "image/png", w: w, h: h, name: "max.png", targetBytes: 1 });
  }

  async function makeOversizePng(overBytes) {
    var f = await makeNearMaxPng(overBytes);
    // If still under, append zeros in a way that keeps MIME but breaks? Better: larger canvas
    var w = 1200;
    var h = 1200;
    var file = await makeImageFile({ type: "image/png", w: w, h: h, name: "over.png", targetBytes: 1 });
    while (file && file.size <= overBytes && w < 4000) {
      w += 200;
      h += 200;
      file = await makeImageFile({ type: "image/png", w: w, h: h, name: "over.png", targetBytes: 1 });
    }
    return file;
  }

  global.Blytz3bMeasure = {
    snap: snap,
    installCommitCounter: installCommitCounter,
    commitCount: commitCount,
    makeImageFile: makeImageFile,
    makeNearMaxPng: makeNearMaxPng,
    makeOversizePng: makeOversizePng,
  };
})(window);
)