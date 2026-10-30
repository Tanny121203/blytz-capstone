"""Stage D: layer rename / duplicate / visibility / lock + curve UI hardening."""

from __future__ import annotations

import unittest
from pathlib import Path

from apps.designs.canvas_safety import scan_canvas_payload


ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _v1(objects):
    return {
        "schema_version": 1,
        "width": 800,
        "height": 800,
        "canvas": {"version": "6.6.1", "objects": objects},
        "views": {"back": {"version": "6.6.1", "objects": []}},
    }


class CurveUiHardeningTests(unittest.TestCase):
    def test_sync_clears_body_when_no_selection(self):
        props = _read("static/js/editor_properties.js")
        sync = props[props.index("function syncFromSelection") : props.index("function patchValues")]
        self.assertIn("discardCurveSessionIfStale", sync)
        self.assertIn("clearPropertiesBody", sync)
        self.assertIn("if (!obj)", sync)
        # Must clear even when the panel is already hidden (stale Apply/Cancel).
        self.assertLess(sync.index("if (!obj)"), sync.index("if (!panel || panel.hidden)"))
        self.assertIn("clearPropertiesBody()", sync)

    def test_curve_handlers_reject_stale_or_multi_selection(self):
        props = _read("static/js/editor_properties.js")
        click = props[
            props.index("function runCurvePanelClick") : props.index(
                "function selectionHasLocked"
            )
        ]
        self.assertIn("curveSupportsObject(obj)", click)
        self.assertIn("obj.blytzId !== curveSession.objectId", click)
        self.assertIn("discardCurvePreview()", click)
        self.assertIn("isActiveSelection", props)
        self.assertIn("curveSupportsObject", props)

    def test_preview_discard_helpers_exported(self):
        props = _read("static/js/editor_properties.js")
        self.assertIn("discardCurveSessionIfStale", props)
        self.assertIn("clearPropertiesBody", props)
        self.assertIn("getCurveSessionObjectId", props)
        contract = _read("static/js/editor_contract.js")
        self.assertIn("discardCurvePreview", contract)


class LayerRenameTests(unittest.TestCase):
    def test_rename_api_and_limits(self):
        canvas = _read("static/js/editor_canvas.js")
        self.assertIn("layerNameMax: 60", canvas)
        self.assertIn("function normalizeLayerName", canvas)
        self.assertIn("function renameObjectById", canvas)
        rename = canvas[
            canvas.index("function renameObjectById") : canvas.index(
                "function setObjectVisibleById"
            )
        ]
        self.assertIn('commitEdit(\n      "rename"', rename)
        self.assertIn("obj.blytzName = next", rename)
        self.assertNotIn("blytzId =", rename)
        self.assertIn("normalizeLayerName", rename)

    def test_empty_name_rejected_no_id_change(self):
        canvas = _read("static/js/editor_canvas.js")
        norm = canvas[
            canvas.index("function normalizeLayerName") : canvas.index(
                "function applyLockInteraction"
            )
        ]
        self.assertIn("if (!trimmed) return null", norm)
        tools = _read("static/js/editor_tools.js")
        self.assertIn("beginLayerRename", tools)
        self.assertIn('e.key === "Enter"', tools)
        self.assertIn('e.key === "Escape"', tools)
        self.assertIn("renameObjectById", tools)
        # Selection-driven layer refresh must not destroy an open rename input.
        self.assertIn('querySelector("[data-layer-rename-input]")', tools)


class LayerDuplicateTests(unittest.TestCase):
    def test_duplicate_mints_id_and_name(self):
        canvas = _read("static/js/editor_canvas.js")
        # Stage F: single + multi share finalizeDuplicatedClone (fresh id/name).
        helper = canvas[
            canvas.index("function finalizeDuplicatedClone") : canvas.index(
                "function duplicateActive"
            )
        ]
        dup = canvas[
            canvas.index("function duplicateActive") : canvas.index(
                "function deleteSelection"
            )
        ]
        self.assertIn("forceBlytzId(cloned)", helper)
        self.assertIn("duplicateLayerName(source)", helper)
        self.assertIn("cloned.visible = true", helper)
        self.assertIn("cloned.blytzLocked = false", helper)
        self.assertIn("copyCurveMeta(source, cloned)", helper)
        curve_helper = canvas[
            canvas.index("function copyCurveMeta") : canvas.index(
                "function finalizeDuplicatedClone"
            )
        ]
        self.assertIn("blytzCurve", curve_helper)
        self.assertIn('commitEdit(\n        "duplicate"', dup)
        self.assertIn("duplicate-selection", dup)
        self.assertIn("finalizeDuplicatedClone", dup)

    def test_duplicate_layer_name_helper(self):
        canvas = _read("static/js/editor_canvas.js")
        self.assertIn('return base + " copy"', canvas)
        tools = _read("static/js/editor_tools.js")
        self.assertIn('iconBtn("duplicate"', tools)
        self.assertIn('layerActionBtn("duplicate"', tools)
        self.assertIn("data-layer-row-action", tools)


class LayerVisibilityTests(unittest.TestCase):
    def test_visibility_api_clears_selection_when_hiding(self):
        canvas = _read("static/js/editor_canvas.js")
        vis = canvas[
            canvas.index("function setObjectVisibleById") : canvas.index(
                "function setObjectLockedById"
            )
        ]
        self.assertIn('commitEdit(\n      next ? "show" : "hide"', vis)
        self.assertIn("obj.visible = next", vis)
        self.assertIn("discardActiveObject", vis)
        tools = _read("static/js/editor_tools.js")
        self.assertIn('iconBtn(\n        "visibility"', tools)
        self.assertIn("Show layer", tools)
        self.assertIn("Hide layer", tools)

    def test_visible_round_trips_in_fabric_json(self):
        """visible is a Fabric built-in; envelope with hidden object stays valid."""
        payload = _v1(
            [
                {
                    "type": "Rect",
                    "blytzId": "r1",
                    "blytzName": "Box",
                    "visible": False,
                    "fill": "#111",
                    "width": 40,
                    "height": 40,
                }
            ]
        )
        self.assertTrue(scan_canvas_payload(payload)["ok"])


class LayerLockTests(unittest.TestCase):
    def test_lock_serialize_and_apply_on_load(self):
        canvas = _read("static/js/editor_canvas.js")
        self.assertIn('"blytzLocked"', canvas)
        ser = canvas[canvas.index("var SERIALIZE_PROPS") : canvas.index("var CURVE_AMOUNT_MIN")]
        self.assertIn('"blytzLocked"', ser)
        self.assertIn("function applyLockInteraction", canvas)
        self.assertIn("function applyLockStateToCanvas", canvas)
        self.assertIn("applyLockStateToCanvas(canvas)", canvas)
        lock = canvas[
            canvas.index("function setObjectLockedById") : canvas.index(
                "function selectObjectById"
            )
        ]
        self.assertIn('commitEdit(\n      next ? "lock" : "unlock"', lock)
        self.assertIn("obj.blytzLocked = next", lock)
        self.assertIn("applyLockInteraction(obj)", lock)
        self.assertIn("selectable: false", canvas)
        self.assertIn("evented: false", canvas)
        self.assertIn("lockMovementX: true", canvas)
        self.assertIn("hasControls: false", canvas)

    def test_layer_panel_vs_canvas_selection(self):
        canvas = _read("static/js/editor_canvas.js")
        self.assertIn("function selectObjectById", canvas)
        self.assertIn("management selection", canvas)
        tools = _read("static/js/editor_tools.js")
        self.assertIn("selectObjectById", tools)
        self.assertIn("is-locked", tools)
        props = _read("static/js/editor_properties.js")
        self.assertIn("isObjectLocked", props)

    def test_locked_object_in_envelope_accepted(self):
        payload = _v1(
            [
                {
                    "type": "IText",
                    "text": "Hi",
                    "blytzId": "t1",
                    "blytzName": "Headline",
                    "blytzLocked": True,
                    "selectable": False,
                    "evented": False,
                }
            ]
        )
        self.assertTrue(scan_canvas_payload(payload)["ok"])


class LayerUiChromeTests(unittest.TestCase):
    def test_css_layer_controls(self):
        css = _read("static/css/responsive.css")
        self.assertIn(".editor-layer-icon-btn", css)
        self.assertIn(".editor-layer-rename-input", css)
        self.assertIn(".editor-layer-row.is-hidden", css)
        self.assertIn(".editor-layer-row.is-locked", css)
        self.assertIn("aria-pressed", _read("static/js/editor_tools.js"))

    def test_docs_mention_layer_ops(self):
        docs = _read("docs/SYSTEM_ARCHITECTURE.md")
        self.assertIn("Layer management (Stage D)", docs)
        self.assertIn("blytzLocked", docs)
        self.assertIn("selectObjectById", docs)
        self.assertIn("layerNameMax", docs)


if __name__ == "__main__":
    unittest.main()
