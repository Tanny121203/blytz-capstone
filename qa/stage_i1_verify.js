/**
 * Stage I.1 browser verification. Disposable draft only.
 * Does not let a submit POST reach the server (fetch is stubbed).
 *
 * Checks frozen-snapshot previews, live-edit mismatch blocking,
 * stale in-flight submit, render failure, resource disposal,
 * and that the Stage H preview modal still renders.
 */
(async function stageI1Verify() {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const report = {
    steps: [],
    ok: true,
    designId: (location.pathname.match(/\/designs\/(\d+)\//) || [])[1] || "?",
    note: "fetch stubbed — no order created",
  };
  const step = (name, data) => {
    report.steps.push(Object.assign({ name: name }, data));
    if (data.ok === false) report.ok = false;
  };

  for (let i = 0; i < 80; i++) {
    if (
      window.BlytzEditor &&
      BlytzEditor.whenReady &&
      window.BlytzEditorSaveState &&
      window.BlytzCanvas &&
      BlytzCanvas.getFabricCanvas &&
      BlytzCanvas.getFabricCanvas() &&
      typeof BlytzEditor.renderFrozenPreview === "function"
    ) {
      try {
        await BlytzEditor.whenReady();
      } catch (e) {}
      break;
    }
    await sleep(100);
  }

  const editor = window.BlytzEditor;
  const canvasApi = window.BlytzCanvas;
  const ss = window.BlytzEditorSaveState;
  const live = canvasApi && canvasApi.getFabricCanvas && canvasApi.getFabricCanvas();
  if (!editor || !canvasApi || !ss || !live || !editor.renderFrozenPreview) {
    return { ok: false, reason: "editor-not-ready", report: report };
  }

  function editorSnapshot() {
    const active = live.getActiveObject ? live.getActiveObject() : null;
    const json = editor.getCanvasJSON();
    return {
      view: editor.getActiveView(),
      frontCount: ((json.canvas || {}).objects || []).length,
      backCount: (((json.views || {}).back || {}).objects || []).length,
      selection: active && active.blytzId ? active.blytzId : active ? "selected" : null,
      canUndo: canvasApi.canUndo ? canvasApi.canUndo() : null,
      dirty: ss.isDirty(),
      status: ss.getStatus(),
      fingerprint: ss._test.readCurrentFingerprint(),
      title: (document.querySelector("[data-editor-title]") || {}).value || "",
      garment: JSON.stringify(editor.getGarmentState()),
    };
  }

  canvasApi.addText(function () {
    return editor.getCanvasJSON();
  }, { text: "I1Live", skipEditing: true });
  await sleep(200);
  const activeObj = live.getActiveObject && live.getActiveObject();
  const before = editorSnapshot();

  const toDataURL = live.toDataURL;
  const discard = live.discardActiveObject ? live.discardActiveObject.bind(live) : null;
  let liveRaster = 0;
  let liveDiscard = 0;
  live.toDataURL = function () {
    liveRaster += 1;
    return toDataURL.apply(this, arguments);
  };
  if (live.discardActiveObject) {
    live.discardActiveObject = function () {
      liveDiscard += 1;
      return discard.apply(live, arguments);
    };
  }

  const fabricRef = window.fabric;
  const OriginalStatic = fabricRef && fabricRef.StaticCanvas;
  let constructed = 0;
  let disposed = 0;
  if (OriginalStatic) {
    const Wrapped = function () {
      constructed += 1;
      const instance = Reflect.construct(OriginalStatic, arguments, new.target || OriginalStatic);
      const origDispose = instance.dispose;
      if (typeof origDispose === "function") {
        instance.dispose = function () {
          disposed += 1;
          return origDispose.apply(this, arguments);
        };
      }
      return instance;
    };
    Wrapped.prototype = OriginalStatic.prototype;
    fabricRef.StaticCanvas = Wrapped;
  }

  function restoreSpies() {
    live.toDataURL = toDataURL;
    if (discard && live.discardActiveObject) live.discardActiveObject = discard;
    if (OriginalStatic) fabricRef.StaticCanvas = OriginalStatic;
  }

  const frozen = JSON.parse(JSON.stringify(editor.getCanvasJSON()));
  const garment = editor.getGarmentState();
  let frontUrl = "";
  let backUrl = "";
  let renderError = "";
  try {
    [frontUrl, backUrl] = await Promise.all([
      editor.renderFrozenPreview({ envelope: frozen, view: "front", garment: garment }),
      editor.renderFrozenPreview({ envelope: frozen, view: "back", garment: garment }),
    ]);
  } catch (err) {
    renderError = err && err.message ? err.message : String(err);
  }
  const afterRender = editorSnapshot();
  step("frozen-render-does-not-mutate-live-editor", {
    ok:
      !renderError &&
      frontUrl.indexOf("data:image/png") === 0 &&
      backUrl.indexOf("data:image/png") === 0 &&
      liveRaster === 0 &&
      liveDiscard === 0 &&
      afterRender.view === before.view &&
      afterRender.frontCount === before.frontCount &&
      afterRender.backCount === before.backCount &&
      afterRender.selection === before.selection &&
      afterRender.canUndo === before.canUndo &&
      afterRender.dirty === before.dirty &&
      afterRender.fingerprint === before.fingerprint &&
      afterRender.title === before.title &&
      afterRender.garment === before.garment &&
      constructed > 0 &&
      disposed === constructed,
    renderError: renderError,
    liveRaster: liveRaster,
    liveDiscard: liveDiscard,
    constructed: constructed,
    disposed: disposed,
    before: before,
    after: afterRender,
  });

  const redEnvelope = {
    schema_version: 1,
    width: 800,
    height: 800,
    canvas: {
      version: "6.6.1",
      objects: [
        {
          type: "rect",
          left: 100,
          top: 100,
          width: 80,
          height: 80,
          fill: "#ff0000",
          originX: "left",
          originY: "top",
        },
      ],
    },
    views: { back: { version: "6.6.1", objects: [] } },
  };
  const liveCountDuring = editor.getCanvasJSON().canvas.objects.length;
  let redUrl = "";
  try {
    redUrl = await editor.renderFrozenPreview({
      envelope: redEnvelope,
      view: "front",
      garment: { template: "tee", color: "white" },
    });
  } catch (err) {
    redUrl = "";
    renderError = err && err.message ? err.message : String(err);
  }
  let redPixel = null;
  if (redUrl) {
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = redUrl;
    });
    const probe = document.createElement("canvas");
    probe.width = img.naturalWidth;
    probe.height = img.naturalHeight;
    const ctx = probe.getContext("2d");
    ctx.drawImage(img, 0, 0);
    redPixel = Array.from(ctx.getImageData(120, 120, 1, 1).data);
  }
  step("png-comes-from-frozen-rect-not-live-text", {
    ok:
      redPixel &&
      redPixel[0] > 200 &&
      redPixel[1] < 40 &&
      redPixel[2] < 40 &&
      editor.getCanvasJSON().canvas.objects.length === liveCountDuring,
    redPixel: redPixel,
    liveCount: editor.getCanvasJSON().canvas.objects.length,
  });

  constructed = 0;
  disposed = 0;
  let failedDisposed = false;
  let failMessage = "";
  try {
    await editor.renderFrozenPreview({
      envelope: {
        schema_version: 1,
        width: 800,
        height: 800,
        canvas: {
          version: "6.6.1",
          objects: [
            {
              type: "image",
              src: "data:image/png;base64,AAAA",
              left: 10,
              top: 10,
              width: 20,
              height: 20,
            },
          ],
        },
        views: { back: { version: "6.6.1", objects: [] } },
      },
      view: "front",
      garment: { template: "tee", color: "white" },
    });
  } catch (err) {
    failMessage = err && err.message ? err.message : String(err);
  }
  await sleep(30);
  failedDisposed = constructed > 0 && disposed === constructed;
  step("failed-image-render-rejects-and-disposes", {
    ok: !!failMessage && failedDisposed && editor.getActiveView() === before.view,
    failMessage: failMessage,
    constructed: constructed,
    disposed: disposed,
  });

  restoreSpies();

  const realRender = editor.renderFrozenPreview.bind(editor);
  const realFetch = window.fetch.bind(window);
  const fetches = [];
  window.fetch = function (url, opts) {
    fetches.push({ url: String(url), body: opts && opts.body });
    return Promise.resolve(
      new Response(JSON.stringify({ ok: false, errors: { design: ["qa-stub"] } }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      })
    );
  };

  const submitBtn = document.querySelector("[data-editor-submit]");
  if (submitBtn) submitBtn.click();
  await sleep(200);
  const amount = document.getElementById("payment-amount");
  const proof = document.getElementById("payment-proof");
  const form = document.getElementById("payment-submit-form");
  if (amount) amount.value = "25.00";
  if (proof) {
    const pngB64 =
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
    const binary = atob(pngB64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const file = new File([bytes], "proof.png", { type: "image/png" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    proof.files = transfer.files;
    proof.dispatchEvent(new Event("change", { bubbles: true }));
  }

  let releaseRender;
  const renderGate = new Promise((resolve) => {
    releaseRender = resolve;
  });
  let renderCalls = 0;
  editor.renderFrozenPreview = function (opts) {
    renderCalls += 1;
    return renderGate.then(function () {
      return realRender(opts);
    });
  };

  const beforeSubmitEdit = editorSnapshot();
  if (form) form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  await sleep(150);
  const during = {
    inFlight: ss.isSubmitInFlight(),
    fetches: fetches.length,
    gen: ss.getSubmitGeneration(),
  };
  canvasApi.addText(function () {
    return editor.getCanvasJSON();
  }, { text: "DuringSubmit", skipEditing: true });
  await sleep(100);
  releaseRender();
  await sleep(800);
  const statusText = (document.querySelector("[data-editor-status]") || {}).textContent || "";
  step("live-edit-during-preview-does-not-post-mismatch", {
    ok:
      during.inFlight === true &&
      during.fetches === 0 &&
      fetches.length === 0 &&
      /changed during submission/i.test(statusText) &&
      ss.isSubmitInFlight() === false,
    during: during,
    fetches: fetches.length,
    statusText: statusText,
    renderCalls: renderCalls,
    fingerprintChanged: ss._test.readCurrentFingerprint() !== beforeSubmitEdit.fingerprint,
  });

  editor.renderFrozenPreview = function () {
    return Promise.reject(new Error("Could not load image for preview."));
  };
  if (submitBtn) submitBtn.click();
  await sleep(100);
  if (form) form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  await sleep(400);
  const failStatus = (document.querySelector("[data-editor-status]") || {}).textContent || "";
  const clientErr = (document.querySelector("[data-payment-client-error]") || {}).textContent || "";
  step("failed-preview-blocks-submit", {
    ok:
      fetches.length === 0 &&
      ss.isSubmitInFlight() === false &&
      /could not load image for preview/i.test(failStatus + " " + clientErr),
    failStatus: failStatus,
    clientErr: clientErr,
    fetches: fetches.length,
  });

  editor.renderFrozenPreview = realRender;
  const genBefore = ss.getSubmitGeneration();
  let secondFetchBlocked = true;
  let rejectHang = null;
  editor.renderFrozenPreview = function () {
    return new Promise(function (_resolve, reject) {
      rejectHang = reject;
    });
  };
  if (form) form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  await sleep(150);
  const firstGen = ss.getSubmitGeneration();
  if (form) form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  await sleep(150);
  secondFetchBlocked = fetches.length === 0 && ss.getSubmitGeneration() === firstGen && ss.isSubmitInFlight();
  step("second-submit-while-in-flight-does-not-post", {
    ok: secondFetchBlocked && firstGen === genBefore + 1,
    genBefore: genBefore,
    firstGen: firstGen,
    genNow: ss.getSubmitGeneration(),
    inFlight: ss.isSubmitInFlight(),
    fetches: fetches.length,
  });
  if (rejectHang) rejectHang(new Error("Could not create preview. Please try again."));
  await sleep(200);

  window.fetch = realFetch;
  editor.renderFrozenPreview = realRender;

  const paymentModal = document.getElementById("payment-modal");
  if (paymentModal && paymentModal.classList.contains("flex")) {
    const payClose = paymentModal.querySelector("[data-modal-close]");
    if (payClose) payClose.click();
    await sleep(150);
  }
  const previewBtn = document.querySelector("[data-editor-preview]");
  const beforePreview = editorSnapshot();
  if (previewBtn) previewBtn.click();
  let previewSrc = "";
  for (let i = 0; i < 25; i++) {
    await sleep(200);
    const img = document.querySelector("[data-design-preview-img]");
    previewSrc = img && img.getAttribute("src") ? img.getAttribute("src") : "";
    if (previewSrc.indexOf("blob:") === 0) break;
  }
  const previewClose = document.querySelector("#design-preview-modal [data-modal-close]");
  if (previewClose) previewClose.click();
  await sleep(200);
  const afterPreview = editorSnapshot();
  step("stage-h-preview-still-renders", {
    ok:
      previewSrc.indexOf("blob:") === 0 &&
      afterPreview.view === beforePreview.view &&
      afterPreview.frontCount === beforePreview.frontCount &&
      afterPreview.backCount === beforePreview.backCount &&
      afterPreview.fingerprint === beforePreview.fingerprint &&
      afterPreview.canUndo === beforePreview.canUndo &&
      afterPreview.selection === beforePreview.selection,
    srcPrefix: previewSrc.slice(0, 24),
    view: afterPreview.view,
    countSame: afterPreview.frontCount === beforePreview.frontCount,
  });

  return report;
})();
