from __future__ import annotations

import csv
import io
import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import analyzer_core as core

APP_ROOT = Path(__file__).resolve().parent
SESSION_ROOT = Path(os.environ.get("YDL_SESSION_ROOT", "/tmp/ydl-sessions"))
SESSION_ROOT.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.environ.get("YDL_MAX_UPLOAD_BYTES", str(30 * 1024 * 1024)))
SESSION_TTL_SECONDS = int(os.environ.get("YDL_SESSION_TTL_SECONDS", str(8 * 3600)))

app = FastAPI(title="YDL-7003-P data analyzer", version="1.7")
app.mount("/static", StaticFiles(directory=APP_ROOT / "static"), name="static")

_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.RLock()
_training_lock = threading.Lock()


def _cleanup_sessions() -> None:
    now = time.time()
    with _sessions_lock:
        expired = [
            sid for sid, state in _sessions.items()
            if now - state.get("touched", now) > SESSION_TTL_SECONDS
        ]
        for sid in expired:
            state = _sessions.pop(sid, None)
            if state:
                shutil.rmtree(state["dir"], ignore_errors=True)


def _state(session_id: str) -> dict[str, Any]:
    _cleanup_sessions()
    with _sessions_lock:
        state = _sessions.get(session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Analysis session not found or expired.")
        state["touched"] = time.time()
        return state


def _decode_image(raw: bytes) -> np.ndarray:
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded image is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Image exceeds the {MAX_UPLOAD_BYTES // (1024*1024)} MB upload limit.")
    arr = np.frombuffer(raw, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="The uploaded file is not a supported image.")
    return image


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _optional_positive_float(value: Any, field_name: str) -> Optional[float]:
    """Return None for an empty optional field; otherwise require a positive number."""
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a positive number or left empty.",
        ) from exc
    if not np.isfinite(parsed) or parsed <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be greater than zero or left empty.",
        )
    return parsed


def _rect_json(rect: Optional[core.Rect]) -> Optional[dict[str, int]]:
    if rect is None:
        return None
    return {"x1": rect.x1, "y1": rect.y1, "x2": rect.x2, "y2": rect.y2}


def _result_json(result: core.AnalysisResult) -> dict[str, Any]:
    fields = (
        "elongation", "max_force", "elongation_source", "max_force_source",
        "x_min", "x_max", "y_min", "y_max", "elongation_data",
        "max_force_data", "elongation_text_percent", "elongation_data_percent",
        "elastic_slope_n_per_mm", "tensile_stiffness_kn_per_m",
        "tensile_stiffness_index_knm_per_kg", "elastic_modulus_mpa",
        "modulus_r2", "break_line_x", "toughness_n_mm", "toughness_mj",
        "mechanical_note", "test_datetime", "test_datetime_source",
        "manual_break_extension", "break_is_manual",
    )
    data = {name: getattr(result, name) for name in fields}
    for key, value in list(data.items()):
        if isinstance(value, (np.floating, np.integer)):
            data[key] = value.item()
        elif isinstance(value, float) and not np.isfinite(value):
            data[key] = None
    data["elong_box"] = _rect_json(result.elong_box)
    data["maxforce_box"] = _rect_json(result.maxforce_box)
    data["graph_plot"] = _rect_json(result.graph_plot)
    data["graph_corners"] = (
        _corners_json(result.graph_corners)
        if result.graph_corners is not None else None
    )
    data["curve_points"] = 0 if result.curve_xy is None else int(len(result.curve_xy))
    return data


def _corners_json(corners: np.ndarray) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in np.asarray(corners).reshape(4, 2)]


def _write_png(path: Path, image: np.ndarray) -> None:
    ok = cv2.imwrite(str(path), image)
    if not ok:
        raise RuntimeError(f"Could not save {path.name}")


def _normalise_test_datetime(value: Any) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, "%Y/%m/%d %H:%M:%S")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Date and time must use YYYY/MM/DD HH:MM:SS.",
        ) from exc
    return parsed.strftime("%Y/%m/%d %H:%M:%S")


def _analysis_meta_json(meta: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not meta:
        return None
    result: dict[str, Any] = {}
    for key, value in meta.items():
        if isinstance(value, core.Rect):
            result[key] = _rect_json(value)
        elif isinstance(value, (np.floating, np.integer)):
            result[key] = value.item()
        else:
            result[key] = value
    return result



def _edge_lengths(corners: np.ndarray) -> tuple[float, float]:
    q = core.order_quad(np.asarray(corners, dtype=np.float32).reshape(4, 2))
    width = 0.5 * (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3]))
    height = 0.5 * (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1]))
    return float(width), float(height)


def _round_axis_guess(value: float, axis: str, current_range: float) -> float:
    if axis == "x":
        step = 0.5 if current_range <= 6 else (1.0 if current_range <= 15 else 2.0)
    else:
        step = 10.0 if current_range >= 40 else (5.0 if current_range >= 15 else 1.0)
    return float(round(value / step) * step)


def _axis_suggestions(old_corners: np.ndarray, new_corners: np.ndarray,
                      result: core.AnalysisResult) -> dict[str, float]:
    """Guess axis changes when a graph edge was moved to another gridline."""
    old_q = core.order_quad(np.asarray(old_corners, dtype=np.float32).reshape(4, 2))
    new_q = core.order_quad(np.asarray(new_corners, dtype=np.float32).reshape(4, 2))
    old_w, old_h = _edge_lengths(old_q)
    new_w, new_h = _edge_lengths(new_q)
    suggestions: dict[str, float] = {}

    x_range = result.x_max - result.x_min
    y_range = result.y_max - result.y_min
    left_move = float(np.mean(new_q[[0, 3], 0] - old_q[[0, 3], 0]))
    right_move = float(np.mean(new_q[[1, 2], 0] - old_q[[1, 2], 0]))
    top_move = float(np.mean(new_q[[0, 1], 1] - old_q[[0, 1], 1]))
    bottom_move = float(np.mean(new_q[[2, 3], 1] - old_q[[2, 3], 1]))

    if old_w > 1 and abs(new_w / old_w - 1.0) >= 0.055:
        guessed_range = x_range * new_w / old_w
        if abs(right_move) >= abs(left_move):
            suggestions["x_max"] = _round_axis_guess(result.x_min + guessed_range, "x", x_range)
        else:
            suggestions["x_min"] = _round_axis_guess(result.x_max - guessed_range, "x", x_range)

    if old_h > 1 and abs(new_h / old_h - 1.0) >= 0.055:
        guessed_range = y_range * new_h / old_h
        if abs(top_move) >= abs(bottom_move):
            suggestions["y_max"] = _round_axis_guess(result.y_min + guessed_range, "y", y_range)
        else:
            suggestions["y_min"] = _round_axis_guess(result.y_max - guessed_range, "y", y_range)

    return suggestions


def _refresh_outputs(state: dict[str, Any]) -> None:
    result = state["result"]
    core.calculate_mechanical_properties(
        result,
        state["gauge_length_mm"],
        state["sample_width_mm"],
        state["thickness_um"],
        state["grammage_g_m2"],
    )
    state["annotated"] = core.draw_annotations(state["rectified"], result)
    state["analysis_graph"], state["analysis_graph_meta"] = core.draw_analysis_graph(
        result,
        state["gauge_length_mm"],
        state["sample_width_mm"],
        state["thickness_um"],
        state["grammage_g_m2"],
    )
    _write_png(state["dir"] / "original.png", state["original"])
    _write_png(state["dir"] / "rectified.png", state["rectified"])
    _write_png(state["dir"] / "annotated.png", state["annotated"])
    _write_png(state["dir"] / "analysis_graph.png", state["analysis_graph"])


def _payload(state: dict[str, Any]) -> dict[str, Any]:
    original_h, original_w = state["original"].shape[:2]
    rect_h, rect_w = state["rectified"].shape[:2]
    return {
        "session_id": state["id"],
        "source_name": state["source_name"],
        "original_size": {"width": original_w, "height": original_h},
        "rectified_size": {"width": rect_w, "height": rect_h},
        "screen_corners": _corners_json(state["corners"]),
        "result": _result_json(state["result"]),
        "layout_validation": state.get("layout_validation", {
            "compliant": True, "score": 1.0, "issues": [], "checks": {}
        }),
        "axis_suggestions": state.pop("axis_suggestions", None),
        "axis_auto_updated": bool(state.pop("axis_auto_updated", False)),
        "axis_confirmation_required": bool(
            state.get("axis_confirmation_required", False)
        ),
        "analysis_graph_meta": _analysis_meta_json(state.get("analysis_graph_meta")),
        "settings": {
            "gauge_length_mm": state["gauge_length_mm"],
            "sample_width_mm": state["sample_width_mm"],
            "thickness_um": state["thickness_um"],
            "grammage_g_m2": state["grammage_g_m2"],
        },
        "images": {
            "original": f"/api/session/{state['id']}/image/original",
            "rectified": f"/api/session/{state['id']}/image/rectified",
            "annotated": f"/api/session/{state['id']}/image/annotated",
            "analysis_graph": f"/api/session/{state['id']}/image/analysis_graph",
        },
    }


def _apply_settings(state: dict[str, Any], payload: dict[str, Any]) -> None:
    state["gauge_length_mm"] = _safe_float(
        payload.get("gauge_length_mm"), state["gauge_length_mm"]
    ) or 50.0
    state["sample_width_mm"] = _safe_float(
        payload.get("sample_width_mm"), state["sample_width_mm"]
    ) or 15.0

    # Explicit null/empty means that the optional property is unknown.
    # If the key is absent, retain the current value for older clients.
    if "thickness_um" in payload:
        state["thickness_um"] = _optional_positive_float(
            payload.get("thickness_um"), "Thickness"
        )
    if "grammage_g_m2" in payload:
        state["grammage_g_m2"] = _optional_positive_float(
            payload.get("grammage_g_m2"), "Grammage"
        )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((APP_ROOT / "static" / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(...),
    gauge_length_mm: float = Form(50.0),
    sample_width_mm: float = Form(15.0),
    thickness_um: Optional[str] = Form(None),
    grammage_g_m2: Optional[str] = Form(None),
) -> JSONResponse:
    raw = await image.read()
    parsed_thickness_um = _optional_positive_float(thickness_um, "Thickness")
    parsed_grammage_g_m2 = _optional_positive_float(grammage_g_m2, "Grammage")
    original = _decode_image(raw)
    screen_detection_ok = True
    try:
        corners = core.detect_screen_corners(original)
    except Exception:
        screen_detection_ok = False
        h, w = original.shape[:2]
        corners = np.array([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]], dtype=np.float32)
    rectified = core.perspective_rectify(original, corners)
    layout_validation = core.validate_expected_layout(
        rectified, screen_detection_ok=screen_detection_ok
    )
    result = core.analyze_rectified(rectified)

    sid = uuid.uuid4().hex
    session_dir = SESSION_ROOT / sid
    session_dir.mkdir(parents=True, exist_ok=False)
    source_name = Path(image.filename or "tester-image").name
    state = {
        "id": sid,
        "dir": session_dir,
        "source_name": source_name,
        "source_path": session_dir / source_name,
        "original": original,
        "corners": corners,
        "rectified": rectified,
        "result": result,
        "layout_validation": layout_validation,
        "gauge_length_mm": gauge_length_mm,
        "sample_width_mm": sample_width_mm,
        "thickness_um": parsed_thickness_um,
        "grammage_g_m2": parsed_grammage_g_m2,
        "axis_confirmation_required": False,
        "touched": time.time(),
    }
    (session_dir / source_name).write_bytes(raw)
    _refresh_outputs(state)
    with _sessions_lock:
        _sessions[sid] = state
    return JSONResponse(_payload(state))


@app.post("/api/session/{session_id}/update")
async def update_session(session_id: str, payload: dict[str, Any]) -> JSONResponse:
    state = _state(session_id)
    _apply_settings(state, payload)

    screen_corners = payload.get("screen_corners")
    screen_changed = screen_corners is not None
    if screen_changed:
        state["axis_confirmation_required"] = False
        previous_datetime = state["result"].test_datetime
        previous_datetime_source = state["result"].test_datetime_source
        arr = np.asarray(screen_corners, dtype=np.float32)
        if arr.shape != (4, 2):
            raise HTTPException(status_code=400, detail="screen_corners must contain four [x,y] points.")
        state["corners"] = core.order_quad(arr)
        state["rectified"] = core.perspective_rectify(state["original"], state["corners"])
        state["layout_validation"] = core.validate_expected_layout(
            state["rectified"], screen_detection_ok=True
        )
        state["result"] = core.analyze_rectified(state["rectified"])
        if (
            previous_datetime
            and previous_datetime_source in {"user entered", "current browser time (prefilled)"}
        ):
            state["result"].test_datetime = previous_datetime
            state["result"].test_datetime_source = previous_datetime_source

    result = state["result"]

    old_graph_corners = (
        np.asarray(result.graph_corners, dtype=np.float32).copy()
        if result.graph_corners is not None
        else (core.graph_corners_from_rect(result.graph_plot) if result.graph_plot else None)
    )

    graph_corners = payload.get("graph_corners")
    graph_changed = graph_corners is not None
    if graph_changed:
        try:
            q = core.order_quad(np.asarray(graph_corners, dtype=np.float32).reshape(4, 2))
            if core.polygon_area(q) < 500:
                raise ValueError("The graph quadrilateral is too small.")
            h, w = state["rectified"].shape[:2]
            q[:, 0] = np.clip(q[:, 0], 0, w - 1)
            q[:, 1] = np.clip(q[:, 1], 0, h - 1)
            if old_graph_corners is not None:
                state["axis_suggestions"] = _axis_suggestions(old_graph_corners, q, result)
            result.graph_corners = q
            result.graph_plot = core.graph_corners_to_rect(q, w, h)
            if payload.get("manual_graph_adjustment"):
                state["axis_confirmation_required"] = True
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid graph corners: {exc}")

    # Backwards compatibility with v1/v2 clients/settings.
    graph = payload.get("graph_plot")
    if graph is not None and not graph_changed:
        try:
            rect = core.Rect(int(graph["x1"]), int(graph["y1"]), int(graph["x2"]), int(graph["y2"]))
            h, w = state["rectified"].shape[:2]
            result.graph_plot = rect.clip(w, h)
            result.graph_corners = core.graph_corners_from_rect(result.graph_plot)
            graph_changed = True
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid graph area: {exc}")

    for field in ("x_min", "x_max", "y_min", "y_max"):
        if field in payload:
            setattr(result, field, float(payload[field]))
    if not (result.x_max > result.x_min and result.y_max > result.y_min):
        raise HTTPException(status_code=400, detail="Axis maxima must exceed minima.")

    if payload.get("auto_graph"):
        state["axis_confirmation_required"] = False
        result.graph_plot = core.find_graph_plot(state["rectified"])
        result.graph_corners = core.graph_corners_from_rect(result.graph_plot)
        (
            result.x_min, result.x_max,
            result.y_min, result.y_max,
        ) = core.estimate_axis_limits(state["rectified"], result.graph_plot)
        state["axis_auto_updated"] = True
        # Auto-detection is a fresh calibration, so old manual suggestions no
        # longer apply.
        state.pop("axis_suggestions", None)
        graph_changed = True

    if result.graph_plot is not None and (
        graph_changed or payload.get("auto_graph") or payload.get("reextract") or screen_changed
    ):
        if result.graph_corners is not None:
            result.curve_xy = core.extract_green_curve_quad(
                state["rectified"], result.graph_corners,
                result.x_min, result.x_max, result.y_min, result.y_max,
            )
        else:
            result.curve_xy = core.extract_green_curve(
                state["rectified"], result.graph_plot,
                result.x_min, result.x_max, result.y_min, result.y_max,
            )

    if "elongation" in payload:
        result.elongation = _safe_float(payload.get("elongation"), result.elongation)
        result.elongation_source = "user edited"
    if "max_force" in payload:
        result.max_force = _safe_float(payload.get("max_force"), result.max_force)
        result.max_force_source = "user edited"

    if "test_datetime" in payload:
        result.test_datetime = _normalise_test_datetime(payload.get("test_datetime"))
        source = str(payload.get("test_datetime_source") or "user entered").strip()
        result.test_datetime_source = source

    if "manual_break_extension" in payload:
        value = _safe_float(payload.get("manual_break_extension"), None)
        if value is None:
            result.manual_break_extension = None
            result.break_is_manual = False
        else:
            result.manual_break_extension = float(value)

    _refresh_outputs(state)
    if payload.get("axis_confirmed"):
        state["axis_confirmation_required"] = False
    return JSONResponse(_payload(state))


@app.post("/api/session/{session_id}/train")
async def train(session_id: str, payload: dict[str, Any]) -> JSONResponse:
    state = _state(session_id)
    elongation = str(payload.get("elongation", "")).strip()
    max_force = str(payload.get("max_force", "")).strip()
    if not elongation or not max_force:
        raise HTTPException(status_code=400, detail="Enter correct extension and maximum-force values.")
    with _training_lock:
        try:
            out, added = core.add_templates_from_corrected_values(
                state["rectified"], elongation, max_force
            )
            core._DIGIT_TEMPLATES = None
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Recognizer training failed: {exc}")
    return JSONResponse({
        "status": "ok",
        "template_file": Path(out).name,
        "added": added,
        "note": "Training affects subsequent analyses made by all users of this deployment.",
    })


@app.get("/api/session/{session_id}/image/{kind}")
def image(session_id: str, kind: str) -> FileResponse:
    state = _state(session_id)
    allowed = {"original", "rectified", "annotated", "analysis_graph"}
    if kind not in allowed:
        raise HTTPException(status_code=404, detail="Unknown image type.")
    return FileResponse(state["dir"] / f"{kind}.png", media_type="image/png")


def _require_confirmed_axes(state: dict[str, Any]) -> None:
    if state.get("axis_confirmation_required", False):
        raise HTTPException(
            status_code=409,
            detail=(
                "Graph corners were adjusted manually. Confirm the axis "
                "calibration and re-extract the curve before exporting."
            ),
        )


@app.get("/api/session/{session_id}/export/csv")
def export_csv(session_id: str) -> Response:
    state = _state(session_id)
    _require_confirmed_axes(state)
    curve = state["result"].curve_xy
    if curve is None or len(curve) == 0:
        raise HTTPException(status_code=400, detail="No curve data are available.")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Extension_mm", "Force_N"])
    writer.writerows((f"{x:.8g}", f"{y:.8g}") for x, y in curve)
    filename = f"{Path(state['source_name']).stem}_curve.csv"
    return Response(
        content="\ufeff" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/session/{session_id}/export/png")
def export_png(session_id: str) -> FileResponse:
    state = _state(session_id)
    _require_confirmed_axes(state)
    filename = f"{Path(state['source_name']).stem}_rectified.png"
    return FileResponse(state["dir"] / "rectified.png", media_type="image/png", filename=filename)


@app.get("/api/session/{session_id}/export/pdf")
def export_pdf(session_id: str) -> FileResponse:
    state = _state(session_id)
    _require_confirmed_axes(state)
    path = state["dir"] / "analysis.pdf"
    core.export_analysis_pdf(
        path,
        state["source_path"],
        state["analysis_graph"],
        state["annotated"],
        state["result"].test_datetime,
    )
    filename = f"{Path(state['source_name']).stem}_analysis.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)


@app.get("/api/session/{session_id}/export/xlsx")
def export_xlsx(session_id: str) -> FileResponse:
    state = _state(session_id)
    _require_confirmed_axes(state)
    path = state["dir"] / "analysis.xlsx"
    core.export_analysis_xlsx(
        path, state["result"], state["source_path"],
        state["gauge_length_mm"], state["sample_width_mm"],
        state["thickness_um"], state["grammage_g_m2"],
        state["analysis_graph"],
    )
    filename = f"{Path(state['source_name']).stem}_analysis.xlsx"
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@app.get("/api/session/{session_id}/settings")
def export_settings(session_id: str) -> Response:
    state = _state(session_id)
    payload = {
        "version": 3,
        "kind": "mechanical_tester_sample_settings",
        "sample": {
            "gauge_length_mm": state["gauge_length_mm"],
            "sample_width_mm": state["sample_width_mm"],
            "thickness_um": state["thickness_um"],
            "grammage_g_m2": state["grammage_g_m2"],
        },
    }
    filename = f"{Path(state['source_name']).stem}_settings.json"
    return Response(
        json.dumps(payload, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
