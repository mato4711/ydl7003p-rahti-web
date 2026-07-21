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

app = FastAPI(title="YDL-7003-P data analyzer", version="1.0")
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
        "mechanical_note",
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
    data["curve_points"] = 0 if result.curve_xy is None else int(len(result.curve_xy))
    return data


def _corners_json(corners: np.ndarray) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in np.asarray(corners).reshape(4, 2)]


def _write_png(path: Path, image: np.ndarray) -> None:
    ok = cv2.imwrite(str(path), image)
    if not ok:
        raise RuntimeError(f"Could not save {path.name}")


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
    state["gauge_length_mm"] = _safe_float(payload.get("gauge_length_mm"), state["gauge_length_mm"]) or 50.0
    state["sample_width_mm"] = _safe_float(payload.get("sample_width_mm"), state["sample_width_mm"]) or 15.0
    state["thickness_um"] = _safe_float(payload.get("thickness_um"), state["thickness_um"])
    state["grammage_g_m2"] = _safe_float(payload.get("grammage_g_m2"), state["grammage_g_m2"])


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
    thickness_um: Optional[float] = Form(120.0),
    grammage_g_m2: Optional[float] = Form(100.0),
) -> JSONResponse:
    raw = await image.read()
    original = _decode_image(raw)
    try:
        corners = core.detect_screen_corners(original)
    except Exception:
        h, w = original.shape[:2]
        corners = np.array([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]], dtype=np.float32)
    rectified = core.perspective_rectify(original, corners)
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
        "gauge_length_mm": gauge_length_mm,
        "sample_width_mm": sample_width_mm,
        "thickness_um": thickness_um,
        "grammage_g_m2": grammage_g_m2,
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

    corners = payload.get("screen_corners")
    if corners is not None:
        arr = np.asarray(corners, dtype=np.float32)
        if arr.shape != (4, 2):
            raise HTTPException(status_code=400, detail="screen_corners must contain four [x,y] points.")
        state["corners"] = core.order_quad(arr)
        state["rectified"] = core.perspective_rectify(state["original"], state["corners"])
        state["result"] = core.analyze_rectified(state["rectified"])

    result = state["result"]
    graph = payload.get("graph_plot")
    if graph is not None:
        try:
            rect = core.Rect(int(graph["x1"]), int(graph["y1"]), int(graph["x2"]), int(graph["y2"]))
            h, w = state["rectified"].shape[:2]
            result.graph_plot = rect.clip(w, h)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid graph area: {exc}")

    for field in ("x_min", "x_max", "y_min", "y_max"):
        if field in payload:
            setattr(result, field, float(payload[field]))
    if not (result.x_max > result.x_min and result.y_max > result.y_min):
        raise HTTPException(status_code=400, detail="Axis maxima must exceed minima.")

    if payload.get("auto_graph"):
        result.graph_plot = core.find_graph_plot(state["rectified"])

    if result.graph_plot is not None and (
        graph is not None or payload.get("auto_graph") or payload.get("reextract") or corners is not None
    ):
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

    _refresh_outputs(state)
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


@app.get("/api/session/{session_id}/export/csv")
def export_csv(session_id: str) -> Response:
    state = _state(session_id)
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
    filename = f"{Path(state['source_name']).stem}_rectified.png"
    return FileResponse(state["dir"] / "rectified.png", media_type="image/png", filename=filename)


@app.get("/api/session/{session_id}/export/pdf")
def export_pdf(session_id: str) -> FileResponse:
    state = _state(session_id)
    path = state["dir"] / "analysis.pdf"
    core.export_analysis_pdf(path, state["source_path"], state["analysis_graph"], state["annotated"])
    filename = f"{Path(state['source_name']).stem}_analysis.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)


@app.get("/api/session/{session_id}/export/xlsx")
def export_xlsx(session_id: str) -> FileResponse:
    state = _state(session_id)
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
    r = state["result"].graph_plot
    h, w = state["rectified"].shape[:2]
    payload = {
        "version": 1,
        "kind": "mechanical_tester_sample_settings",
        "source_image": state["source_name"],
        "sample": {
            "gauge_length_mm": state["gauge_length_mm"],
            "sample_width_mm": state["sample_width_mm"],
            "thickness_um": state["thickness_um"],
            "grammage_g_m2": state["grammage_g_m2"],
        },
        "graph_plot_norm": core.rect_to_norm(r, w, h) if r else None,
    }
    filename = f"{Path(state['source_name']).stem}_settings.json"
    return Response(
        json.dumps(payload, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
