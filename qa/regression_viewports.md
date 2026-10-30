# Viewport before/after pairs

## Setup

1. Fresh browser context, `Network.setCacheDisabled(true)`.
2. Open the editor page.
3. Paste `qa/gate.js`, run `await blytzGate({ expect: { ...disk sha256... } })`.
4. Emulate each viewport: 390×844, 768×1024, 1024×768, 1440×900, 1920×1080.

## Console snippet

Paste once, then call `await blytzViewportPairs()` at each viewport after changing device metrics.

```js
async function blytzViewportPairs() {
  function snap() {
    var wrap = document.getElementById("editor-canvas-wrap");
    var shell = document.querySelector(".editor-shell");
    var wr = wrap.getBoundingClientRect();
    return {
      logical: BlytzCanvas.LOGICAL_SIZE,
      wrapClient: wrap.clientWidth,
      wrapOffset: wrap.offsetWidth,
      wrap: [Math.round(wr.width), Math.round(wr.height)],
      shellH: Math.round(shell.getBoundingClientRect().height),
      scrollH: document.documentElement.scrollHeight,
      hOverflow:
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth + 1,
      canPersist: BlytzEditor.canPersist(),
    };
  }
  function eq(a, b) {
    return JSON.stringify(a) === JSON.stringify(b);
  }
  var c = BlytzCanvas.getFabricCanvas();
  BlytzCanvas.commitEdit(
    "clear",
    function () {
      c.getObjects()
        .slice()
        .forEach(function (o) {
          c.remove(o);
        });
      c.discardActiveObject();
      c.requestRenderAll();
      return true;
    },
    function () {
      return BlytzEditor.getCanvasJSON();
    }
  );
  BlytzEditorTools.closePanel();
  if (BlytzEditorProps.closeSheet) BlytzEditorProps.closeSheet();
  await new Promise(function (r) {
    setTimeout(r, 80);
  });
  var base = snap();
  BlytzCanvas.insertElement(
    "v",
    function (p) {
      return BlytzEditorTools.fabricObjectFromShape("rect", p);
    },
    function () {
      return BlytzEditor.getCanvasJSON();
    },
    "Rectangle"
  );
  var obj = c.getActiveObject();
  c.setActiveObject(obj);
  BlytzEditorProps.syncFromSelection();
  if (matchMedia("(max-width:1023px)").matches) BlytzEditorProps.openSheet();
  await new Promise(function (r) {
    setTimeout(r, 50);
  });
  var afterSelect = snap();
  var sw = document.querySelector('[data-prop-swatch="fill"]');
  if (sw) sw.click();
  await new Promise(function (r) {
    setTimeout(r, 40);
  });
  var afterProp = snap();
  BlytzEditorTools.openPanel("layers");
  await new Promise(function (r) {
    setTimeout(r, 50);
  });
  var afterLayers = snap();
  var snaps = [base, afterSelect, afterProp, afterLayers];
  var names = ["base", "select", "prop", "layers"];
  var pairs = {};
  var allEqual = true;
  for (var i = 0; i < names.length - 1; i++) {
    var e = eq(snaps[i], snaps[i + 1]);
    if (!e) allEqual = false;
    pairs[names[i + 1]] = { before: snaps[i], after: snaps[i + 1], equal: e };
  }
  return { vp: [innerWidth, innerHeight], allEqual: allEqual, pairs: pairs };
}
```

All pairs must be equal for actions that must not change layout.
