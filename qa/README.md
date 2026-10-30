# Blytz Capstone — QA scripts

Console-pasteable measurement scripts for Stage 3d/3e. They are **not** loaded by the app.

## Rules (every script)

1. Self-contained and pasteable into the DevTools console on the editor page.
2. Returns a plain result object (or prints PASS/FAIL lines).
3. Mutates nothing permanent (clear temporary canvas objects when done).
4. Starts with the in-page gate checks from `gate.js` (or embeds equivalent checks).

## Standard measurement method

1. Fresh browser context with `Network.setCacheDisabled(true)` (CDP) or a hard reload with cache disabled.
2. Open the editor (e.g. `http://127.0.0.1:8000/app/designs/<id>/editor/`).
3. Paste `gate.js`, then run:

```js
await blytzGate({
  expect: {
    "editor_canvas.js": "<disk sha256>",
    "editor_tools.js": "<disk sha256>",
    "editor_properties.js": "<disk sha256>",
    // after Part 2:
    // "editor_garments.js": "<disk sha256>",
  },
});
```

Abort if the gate throws. Compute disk hashes with:

```bash
python -c "import hashlib,pathlib; r=pathlib.Path('static/js');
for n in ['editor_canvas.js','editor_tools.js','editor_properties.js']:
 b=(r/n).read_bytes(); print(n, hashlib.sha256(b).hexdigest())"
```

4. Standard viewports: 390×844, 768×1024, 1024×768, 1440×900, 1920×1080.

## Files

| File | Purpose |
|------|---------|
| `gate.js` | Shared GATE (sha256 + typeof + console errors) |
| `regression_commits.js` | Stage 3c/3d commit-count regression (Task 6) |
| `regression_viewports.md` | How to run before/after layout pairs |
| `manual_device_checklist.md` | Real-phone checklist |
| `garment_checks.js` | Garment / Front-Back / preview PNG checks (layers, CSS-var bake, 800×800 mock-ups) |
| `blytz_stage3a_*` | Copied from Desktop (Stage 3a) |
| `blytz_stage3b_*` | Copied from Desktop (Stage 3b) |
| `blytz_stage3c_rerun_notes.txt` | Copied notes |
| `blytz_stage3_audit_probe.html` | Copied audit probe |

## Missing from Desktop

None of the named Stage 3a/3b scripts were missing at copy time. Extra Desktop notes (`blytz_stage3a_verify_NOTES.md`, `blytz_stage3b_notes.txt`, `blytz_stage3c_rerun_notes.txt`, `blytz_stage3a_verify.b64.txt`, `blytz_stage3_audit_probe.html`) were also copied.
