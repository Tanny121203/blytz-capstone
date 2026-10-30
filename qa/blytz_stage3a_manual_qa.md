# Blytz Stage 3a — Manual QA checklist

Probe script: `C:\Users\acer\Desktop\blytz_stage3a_probe.html`  
(Playwright was not installed; no `requirements-dev.txt` exists — CDP/manual path used.)

## Setup
1. `.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000`
2. Sign in as `customer1@blytz.demo` / `demo-pass-123`
3. Open any design editor URL under `/app/designs/<id>/editor/`

## Layout (each viewport)
Viewports: 390×844, 768×1024, 1024×768, 1440×900, 1920×1080

- [ ] `#editor-toolbar` is a **sibling** of `#editor-root` (not inside it)
- [ ] Logical Fabric size stays 800×800 (`canvas.width` / `canvas.height`)
- [ ] Bottom toolbar (≤1023px) does not increase `document.documentElement.scrollHeight` when opening AI candidates
- [ ] After AI prompt → preview → switch candidate: wrap CSS width/height unchanged; shell height unchanged
- [ ] No horizontal overflow (`scrollWidth <= clientWidth`)
- [ ] No Export/Download controls

## Commits (DevTools console)
```js
let n = 0; BlytzEditor.onCommittedChange(() => n++);
// then perform action, read n
```
- [ ] One drag/scale/rotate → `n` increases by 1
- [ ] Multi-select 3 objects → Delete → `n` increases by 1
- [ ] Type in text, exit edit → `n` increases by 1 (not per keystroke)
- [ ] Select / deselect / multi-select toggle → `n` unchanged
- [ ] AI preview / switch candidate → `n` unchanged; `BlytzEditor.canPersist()` true when ready
- [ ] First drag after AI preview → sibling candidate discarded (one candidate remains)

## blytzId
```js
const a = BlytzEditor.getCanvasJSON();
BlytzEditor.loadCanvasJSON(a);
await BlytzEditor.whenReady();
const b = BlytzEditor.getCanvasJSON();
// a.canvas.objects.map(o=>o.blytzId) === b.canvas.objects.map(o=>o.blytzId)
```

## ActiveSelection
Select two objects, move+scale the group, `getCanvasJSON()` during selection vs after deselect — compare left/top/scaleX/scaleY.
