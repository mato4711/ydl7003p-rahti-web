
const $ = id => document.getElementById(id);

let session = null;
let selectedFile = null;
let originalImage = new Image();
let rectifiedImage = new Image();
let screenImage = new Image();
let analysisImage = new Image();
let corners = [];
let graphCorners = [];
let drag = null;
let previewUrl = null;
let analysisSerial = 0;
let analysisMeta = null;

function status(message, kind="ready") {
  const el = $("status");
  el.textContent = message;
  el.className = `status ${kind}`;
}

function setBusy(busy) {
  document.body.classList.toggle("busy", busy);
}

function setTab(panelId) {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === panelId);
  });
  document.querySelectorAll(".panel").forEach(panel => {
    panel.classList.toggle("active", panel.id === panelId);
  });
  setTimeout(redrawAll, 40);
}

function num(id, fallback=null) {
  const value = parseFloat($(id).value);
  return Number.isFinite(value) ? value : fallback;
}

function settingsPayload() {
  return {
    gauge_length_mm: num("gauge", 50),
    sample_width_mm: num("width", 15),
    thickness_um: num("thickness", null),
    grammage_g_m2: num("grammage", null)
  };
}

async function api(url, options={}) {
  status("Working — please wait…", "working");
  setBusy(true);
  try {
    const response = await fetch(url, options);
    const type = response.headers.get("content-type") || "";
    const data = type.includes("json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = data?.detail;
      const message = typeof detail === "string" ? detail : (detail?.message || data || `HTTP ${response.status}`);
      status(message, "error");
      throw new Error(message);
    }
    return data;
  } finally {
    setBusy(false);
  }
}

function loadImage(image, url) {
  return new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = reject;
    image.src = url + (url.includes("?") ? "&" : "?") + "t=" + Date.now();
  });
}

function loadLocalPreview(file) {
  return new Promise((resolve, reject) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    originalImage.onload = resolve;
    originalImage.onerror = reject;
    originalImage.src = previewUrl;
  });
}

function renderValidation(validation) {
  const box = $("layoutNotice");
  if (!validation) {
    box.className = "layout-notice hidden";
    box.innerHTML = "";
    return;
  }
  if (validation.compliant) {
    box.className = "layout-notice ok";
    box.innerHTML = "<strong>Expected layout confirmed:</strong> Force/extension graph, Elongation and MaxForce detected.";
  } else {
    const issues = (validation.issues || []).map(x => `<li>${escapeHtml(x)}</li>`).join("");
    box.className = "layout-notice warning";
    box.innerHTML = `<strong>Layout warning:</strong><ul>${issues}</ul>`;
  }
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, c => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  })[c]);
}

function clearAxisSuggestion() {
  $("axisCard").classList.remove("needs-confirmation", "auto-updated");
  $("axisHint").classList.add("hidden");
  $("axisHint").textContent = "";
}

function applyAxisSuggestions(suggestions) {
  if (!suggestions || !Object.keys(suggestions).length) {
    return false;
  }
  const mapping = {x_min:"xmin", x_max:"xmax", y_min:"ymin", y_max:"ymax"};
  const labels = [];
  let first = null;
  Object.entries(suggestions).forEach(([key, value]) => {
    const id = mapping[key];
    if (!id) return;
    $(id).value = value;
    labels.push(`${key.replace("_", " ")} = ${value}`);
    if (!first) first = $(id);
  });
  $("axisHint").textContent =
    `The graph boundary changed substantially. Suggested ${labels.join(", ")}. Confirm these values, then click “Confirm axes and re-extract curve”.`;
  $("axisHint").classList.remove("hidden");
  $("axisCard").classList.add("needs-confirmation");
  $("axisCard").scrollIntoView({behavior:"smooth", block:"center"});
  if (first) setTimeout(() => first.focus({preventScroll:true}), 350);
  status("Graph corners updated. Please confirm the highlighted axis calibration.", "warning");
  return true;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function currentLocalDateTimeText() {
  const now = new Date();
  return `${now.getFullYear()}/${pad2(now.getMonth()+1)}/${pad2(now.getDate())} ` +
         `${pad2(now.getHours())}:${pad2(now.getMinutes())}:${pad2(now.getSeconds())}`;
}

function setDateTimeInputs(text) {
  const match = String(text || "").match(
    /^(\d{4})\/(\d{2})\/(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/
  );
  if (!match) return false;
  $("testDate").value = `${match[1]}-${match[2]}-${match[3]}`;
  $("testTime").value = `${match[4]}:${match[5]}:${match[6]}`;
  return true;
}

function dateTimeFromInputs() {
  const date = $("testDate").value;
  let time = $("testTime").value;
  if (!date || !time) return null;
  if (/^\d{2}:\d{2}$/.test(time)) time += ":00";
  return `${date.replaceAll("-", "/")} ${time}`;
}

async function applyResponse(data, options={}) {
  session = data;
  analysisMeta = data.analysis_graph_meta || null;
  corners = (data.screen_corners || []).map(p => [...p]);
  if (data.result.graph_corners) {
    graphCorners = data.result.graph_corners.map(p => [...p]);
  } else if (data.result.graph_plot) {
    const r = data.result.graph_plot;
    graphCorners = [[r.x1,r.y1],[r.x2,r.y1],[r.x2,r.y2],[r.x1,r.y2]];
  } else {
    graphCorners = [];
  }

  $("xmin").value = data.result.x_min;
  $("xmax").value = data.result.x_max;
  $("ymin").value = data.result.y_min;
  $("ymax").value = data.result.y_max;
  $("gauge").value = data.settings.gauge_length_mm ?? "";
  $("width").value = data.settings.sample_width_mm ?? "";
  $("thickness").value = data.settings.thickness_um ?? "";
  $("grammage").value = data.settings.grammage_g_m2 ?? "";
  $("elongation").value = data.result.elongation ?? "";
  $("maxForce").value = data.result.max_force ?? "";

  if (setDateTimeInputs(data.result.test_datetime)) {
    $("datetimeHint").textContent =
      data.result.test_datetime_source === "timestamp detected"
        ? "Detected from the tester screen."
        : "Using the entered or pre-filled date and time.";
  }

  showResults(data.result);
  renderValidation(data.layout_validation);

  await Promise.all([
    loadImage(originalImage, data.images.original),
    loadImage(rectifiedImage, data.images.rectified),
    loadImage(screenImage, data.images.annotated),
    loadImage(analysisImage, data.images.analysis_graph)
  ]);
  redrawAll();

  const suggested = applyAxisSuggestions(data.axis_suggestions);
  if (!suggested) {
    clearAxisSuggestion();
    if (data.axis_auto_updated) {
      $("axisHint").textContent =
        `Graph and axes auto-detected: X ${data.result.x_min}–${data.result.x_max} mm, ` +
        `Y ${data.result.y_min}–${data.result.y_max} N.`;
      $("axisHint").classList.remove("hidden");
      $("axisCard").classList.add("auto-updated");
      setTimeout(() => $("axisCard").classList.remove("auto-updated"), 2400);
      status("Graph area and axis calibration updated automatically.", "ready");
    } else if (options.initial) {
      if (data.layout_validation?.compliant) {
        setTab("screenPanel");
        status("Analysis ready. Review the corrected screen and graph corners.", "ready");
      } else {
        setTab("originalPanel");
        status("Image analysed, but the expected completed-test layout was not confirmed.", "warning");
      }
    } else {
      status("Ready.", "ready");
    }
  }
}

function f(value, digits=2) {
  return value == null || !Number.isFinite(Number(value)) ? "—" : Number(value).toFixed(digits);
}

function showResults(r) {
  const manual = r.break_is_manual ? " (manual)" : "";
  $("results").textContent =
`Test date and time: ${r.test_datetime || "Not detected"}

Instrument extension: ${f(r.elongation)} mm
Instrument strain: ${f(r.elongation_text_percent)} %
Curve break extension${manual}: ${f(r.elongation_data)} mm
Curve strain at break${manual}: ${f(r.elongation_data_percent)} %

Instrument max force: ${f(r.max_force)} N
Curve maximum force: ${f(r.max_force_data)} N

Initial slope: ${f(r.elastic_slope_n_per_mm,3)} N/mm
Fit R²: ${f(r.modulus_r2,4)}
Tensile stiffness: ${f(r.tensile_stiffness_kn_per_m,3)} kN/m
Stiffness index: ${f(r.tensile_stiffness_index_knm_per_kg,3)} kN·m/kg
Tensile modulus: ${f(r.elastic_modulus_mpa,3)} MPa

Tensile energy: ${f(r.toughness_n_mm,3)} N·mm (${f(r.toughness_mj,3)} mJ)
Curve points: ${r.curve_points}
${r.mechanical_note ? "\nNote: " + r.mechanical_note : ""}`;
}

function fitCanvas(canvas, image) {
  if (!image.naturalWidth || !image.naturalHeight) return 1;
  const wrap = canvas.parentElement;
  const scale = Math.min(
    wrap.clientWidth / image.naturalWidth,
    wrap.clientHeight / image.naturalHeight
  );
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
  return scale;
}

function handle(ctx, x, y) {
  ctx.beginPath();
  ctx.arc(x, y, 8, 0, Math.PI * 2);
  ctx.fillStyle = "#ffd400";
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#111";
  ctx.stroke();
}

function drawOriginal() {
  if (!originalImage.naturalWidth) return;
  const canvas = $("originalCanvas");
  const scale = fitCanvas(canvas, originalImage);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(originalImage, 0, 0, canvas.width, canvas.height);

  if (corners.length === 4) {
    ctx.strokeStyle = "#ffd400";
    ctx.lineWidth = 3;
    ctx.beginPath();
    corners.forEach((point, i) => {
      const x = point[0] * scale;
      const y = point[1] * scale;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.closePath();
    ctx.stroke();
    corners.forEach(point => handle(ctx, point[0] * scale, point[1] * scale));
  }
  canvas.dataset.scale = scale;
}

function drawScreen() {
  if (!screenImage.naturalWidth) return;
  const canvas = $("screenCanvas");
  const scale = fitCanvas(canvas, screenImage);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(screenImage, 0, 0, canvas.width, canvas.height);

  if (graphCorners.length === 4) {
    ctx.strokeStyle = "#ffd400";
    ctx.lineWidth = 3;
    ctx.beginPath();
    graphCorners.forEach((point, i) => {
      const x = point[0] * scale;
      const y = point[1] * scale;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.closePath();
    ctx.stroke();
    graphCorners.forEach(point => handle(ctx, point[0] * scale, point[1] * scale));
  }
  canvas.dataset.scale = scale;
}

function drawAnalysis() {
  if (!analysisImage.naturalWidth) return;
  const canvas = $("analysisCanvas");
  const scale = fitCanvas(canvas, analysisImage);
  canvas.getContext("2d").drawImage(analysisImage, 0, 0, canvas.width, canvas.height);
  canvas.dataset.scale = scale;
}

function redrawAll() {
  drawOriginal();
  drawScreen();
  drawAnalysis();
}

function nearest(points, x, y, limit=18) {
  let best = -1;
  let distance = Infinity;
  points.forEach((point, i) => {
    const d = Math.hypot(point[0] - x, point[1] - y);
    if (d < distance) {
      distance = d;
      best = i;
    }
  });
  return distance <= limit ? best : -1;
}

function drawMagnifier(containerId, image, sourceX, sourceY) {
  const box = $(containerId);
  const canvas = box.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const cropW = 90;
  const cropH = 66;
  const sx = Math.max(0, Math.min(image.naturalWidth - cropW, sourceX - cropW / 2));
  const sy = Math.max(0, Math.min(image.naturalHeight - cropH, sourceY - cropH / 2));
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(image, sx, sy, cropW, cropH, 0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#ffd400";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(canvas.width / 2, 0);
  ctx.lineTo(canvas.width / 2, canvas.height);
  ctx.moveTo(0, canvas.height / 2);
  ctx.lineTo(canvas.width, canvas.height / 2);
  ctx.stroke();
  box.classList.add("visible");
}

function hideMagnifier(id) {
  $(id).classList.remove("visible");
}

function barycentric(point, a, b, c) {
  const v0 = [b[0]-a[0], b[1]-a[1]];
  const v1 = [c[0]-a[0], c[1]-a[1]];
  const v2 = [point[0]-a[0], point[1]-a[1]];
  const d00 = v0[0]*v0[0] + v0[1]*v0[1];
  const d01 = v0[0]*v1[0] + v0[1]*v1[1];
  const d11 = v1[0]*v1[0] + v1[1]*v1[1];
  const d20 = v2[0]*v0[0] + v2[1]*v0[1];
  const d21 = v2[0]*v1[0] + v2[1]*v1[1];
  const den = d00*d11 - d01*d01;
  if (Math.abs(den) < 1e-9) return null;
  const v = (d11*d20 - d01*d21) / den;
  const w = (d00*d21 - d01*d20) / den;
  const u = 1 - v - w;
  if (u < -0.002 || v < -0.002 || w < -0.002) return null;
  return [u,v,w];
}

function graphUv(point) {
  if (graphCorners.length !== 4) return null;
  const [tl,tr,br,bl] = graphCorners;
  let bc = barycentric(point, tl, tr, br);
  if (bc) {
    const [a,b,c] = bc;
    return [b + c, c];
  }
  bc = barycentric(point, tl, br, bl);
  if (bc) {
    const [a,b,c] = bc;
    return [b, b + c];
  }
  return null;
}

function showGraphReadout(event) {
  if (!session || graphCorners.length !== 4) return;
  const canvas = $("screenCanvas");
  const scale = Number(canvas.dataset.scale || 1);
  const rect = canvas.getBoundingClientRect();
  const displayX = event.clientX - rect.left;
  const displayY = event.clientY - rect.top;
  const source = [displayX / scale, displayY / scale];
  const uv = graphUv(source);
  const box = $("graphReadout");
  if (!uv) {
    box.classList.add("hidden");
    hideMagnifier("screenMagnifier");
    return;
  }
  const xMin = num("xmin", 0), xMax = num("xmax", 5);
  const yMin = num("ymin", 0), yMax = num("ymax", 120);
  const extension = xMin + uv[0] * (xMax - xMin);
  const force = yMax - uv[1] * (yMax - yMin);
  box.textContent = `Extension ${extension.toFixed(3)} mm   Force ${force.toFixed(2)} N`;
  const wrapRect = canvas.parentElement.getBoundingClientRect();
  box.style.left = `${Math.min(wrapRect.width - 235, Math.max(8, event.clientX - wrapRect.left + 14))}px`;
  box.style.top = `${Math.min(wrapRect.height - 40, Math.max(8, event.clientY - wrapRect.top + 14))}px`;
  box.classList.remove("hidden");
  drawMagnifier("screenMagnifier", rectifiedImage, source[0], source[1]);
}

$("originalCanvas").addEventListener("pointerdown", event => {
  if (corners.length !== 4) return;
  const canvas = event.currentTarget;
  const scale = Number(canvas.dataset.scale);
  const rect = canvas.getBoundingClientRect();
  const index = nearest(
    corners.map(p => [p[0]*scale, p[1]*scale]),
    event.clientX - rect.left,
    event.clientY - rect.top
  );
  if (index >= 0) {
    drag = {type:"screen", index};
    canvas.setPointerCapture(event.pointerId);
  }
});

$("originalCanvas").addEventListener("pointermove", event => {
  if (!drag || drag.type !== "screen") return;
  const canvas = event.currentTarget;
  const scale = Number(canvas.dataset.scale);
  const rect = canvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) / scale;
  const y = (event.clientY - rect.top) / scale;
  corners[drag.index] = [x,y];
  drawOriginal();
  drawMagnifier("originalMagnifier", originalImage, x, y);
});

$("originalCanvas").addEventListener("pointerup", () => {
  drag = null;
  hideMagnifier("originalMagnifier");
});
$("originalCanvas").addEventListener("pointerleave", () => {
  if (!drag) hideMagnifier("originalMagnifier");
});

$("screenCanvas").addEventListener("pointerdown", event => {
  if (graphCorners.length !== 4) return;
  const canvas = event.currentTarget;
  const scale = Number(canvas.dataset.scale);
  const rect = canvas.getBoundingClientRect();
  const index = nearest(
    graphCorners.map(p => [p[0]*scale, p[1]*scale]),
    event.clientX - rect.left,
    event.clientY - rect.top
  );
  if (index >= 0) {
    drag = {type:"graph", index};
    canvas.setPointerCapture(event.pointerId);
    $("graphReadout").classList.add("hidden");
  }
});

$("screenCanvas").addEventListener("pointermove", event => {
  if (drag && drag.type === "graph") {
    const canvas = event.currentTarget;
    const scale = Number(canvas.dataset.scale);
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) / scale;
    const y = (event.clientY - rect.top) / scale;
    graphCorners[drag.index] = [x,y];
    drawScreen();
    drawMagnifier("screenMagnifier", rectifiedImage, x, y);
  } else {
    showGraphReadout(event);
  }
});

$("screenCanvas").addEventListener("pointerup", () => {
  drag = null;
  hideMagnifier("screenMagnifier");
});
$("screenCanvas").addEventListener("pointerleave", () => {
  if (!drag) hideMagnifier("screenMagnifier");
  $("graphReadout").classList.add("hidden");
});

async function runAnalysis(file) {
  if (!file) {
    status("Choose an image first.", "error");
    return;
  }
  const serial = ++analysisSerial;
  const form = new FormData();
  form.append("image", file);
  Object.entries(settingsPayload()).forEach(([key,value]) => {
    if (value !== null) form.append(key, value);
  });
  try {
    let data = await api("/api/analyze", {method:"POST", body:form});
    if (serial !== analysisSerial) return;

    // When the tester timestamp cannot be read, use the user's current local
    // date and time as an immediately editable default, and save it server-side
    // so it is included in the graph and all exports.
    if (!data.result.test_datetime) {
      const fallbackDateTime = currentLocalDateTimeText();
      const payload = {
        ...data.settings,
        x_min:data.result.x_min, x_max:data.result.x_max,
        y_min:data.result.y_min, y_max:data.result.y_max,
        test_datetime:fallbackDateTime,
        test_datetime_source:"current browser time (prefilled)"
      };
      data = await api(`/api/session/${data.session_id}/update`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
      });
    }

    if (serial !== analysisSerial) return;
    await applyResponse(data, {initial:true});
  } catch (error) {
    console.error(error);
  }
}

$("imageFile").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  selectedFile = file;
  $("analyzeBtn").disabled = false;
  session = null;
  corners = [];
  graphCorners = [];
  renderValidation(null);
  clearAxisSuggestion();
  $("results").textContent = "Analysis in progress…";
  setTab("originalPanel");
  try {
    await loadLocalPreview(file);
    drawOriginal();
    status("Image loaded. Uploading and analysing automatically…", "working");
    runAnalysis(file);
  } catch (error) {
    status("The selected image could not be displayed.", "error");
  }
});

$("analyzeBtn").addEventListener("click", () => runAnalysis(selectedFile));

async function update(extra={}) {
  if (!session) {
    status("Analyse an image first.", "error");
    return;
  }
  const payload = {
    ...settingsPayload(),
    x_min:num("xmin",0), x_max:num("xmax",5),
    y_min:num("ymin",0), y_max:num("ymax",120),
    ...extra
  };
  try {
    const data = await api(`/api/session/${session.session_id}/update`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload)
    });
    await applyResponse(data);
  } catch (error) {
    console.error(error);
  }
}

$("applyCornersBtn").onclick = () => update({screen_corners:corners});
$("applyGraphBtn").onclick = () => update({graph_corners:graphCorners, reextract:true});
$("autoGraphBtn").onclick = () => update({auto_graph:true, reextract:true});
$("reextractBtn").onclick = async () => {
  clearAxisSuggestion();
  await update({reextract:true});
};
$("updateCalcBtn").onclick = () => update({});
$("editedBtn").onclick = () => update({
  elongation:num("elongation",null),
  max_force:num("maxForce",null)
});

["xmin","xmax","ymin","ymax"].forEach(id => {
  $(id).addEventListener("input", clearAxisSuggestion);
});

$("trainBtn").onclick = async () => {
  if (!session) return;
  if (!confirm("Teach the shared recognizer from these corrected values?")) return;
  try {
    const data = await api(`/api/session/${session.session_id}/train`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        elongation:$("elongation").value,
        max_force:$("maxForce").value
      })
    });
    status(`Recognizer updated. Added ${JSON.stringify(data.added)}.`, "ready");
  } catch (error) {
    console.error(error);
  }
};

$("updateDateTimeBtn").onclick = async () => {
  const value = dateTimeFromInputs();
  if (!value) {
    status("Enter both a date and a time.", "error");
    return;
  }
  await update({
    test_datetime:value,
    test_datetime_source:"user entered"
  });
};

$("analysisCanvas").addEventListener("click", async event => {
  if (!event.ctrlKey || event.button !== 0 || !session || !analysisMeta?.plot) return;

  event.preventDefault();
  const canvas = event.currentTarget;
  const scale = Number(canvas.dataset.scale || 1);
  const rect = canvas.getBoundingClientRect();
  const imageX = (event.clientX - rect.left) / scale;
  const imageY = (event.clientY - rect.top) / scale;
  const plot = analysisMeta.plot;

  if (
    imageX < plot.x1 || imageX > plot.x2 ||
    imageY < plot.y1 || imageY > plot.y2
  ) {
    return;
  }

  const fraction = (imageX - plot.x1) / Math.max(1, plot.x2 - plot.x1);
  const strainPercent =
    analysisMeta.x_min_pct +
    fraction * (analysisMeta.x_max_pct - analysisMeta.x_min_pct);
  const extensionMm = strainPercent * num("gauge", 50) / 100.0;

  status(`Manual break point selected at approximately ${extensionMm.toFixed(3)} mm.`, "working");
  await update({manual_break_extension:extensionMm});
  setTab("graphPanel");
});

window.addEventListener("resize", () => setTimeout(redrawAll, 100));

document.querySelectorAll(".tab").forEach(button => {
  button.onclick = () => setTab(button.dataset.tab);
});

document.querySelectorAll("[data-export]").forEach(button => {
  button.onclick = () => {
    if (!session) {
      status("Analyse an image first.", "error");
      return;
    }
    window.location = `/api/session/${session.session_id}/export/${button.dataset.export}`;
  };
});

$("saveSettingsBtn").onclick = () => {
  if (!session) {
    status("Analyse an image first.", "error");
    return;
  }
  window.location = `/api/session/${session.session_id}/settings`;
};

$("settingsFile").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    const cfg = JSON.parse(await file.text());
    const settings = cfg.sample || cfg;
    if (settings.gauge_length_mm != null) $("gauge").value = settings.gauge_length_mm;
    if (settings.sample_width_mm != null) $("width").value = settings.sample_width_mm;
    if (settings.thickness_um != null) $("thickness").value = settings.thickness_um;
    if (settings.grammage_g_m2 != null) $("grammage").value = settings.grammage_g_m2;

    if (session && cfg.graph_corners_norm) {
      const w = session.rectified_size.width;
      const h = session.rectified_size.height;
      graphCorners = cfg.graph_corners_norm.map(p => [p[0]*w, p[1]*h]);
      await update({graph_corners:graphCorners, reextract:true});
    } else if (session && cfg.graph_plot_norm) {
      const n = cfg.graph_plot_norm;
      const w = session.rectified_size.width;
      const h = session.rectified_size.height;
      graphCorners = [
        [n[0]*w,n[1]*h],[n[2]*w,n[1]*h],
        [n[2]*w,n[3]*h],[n[0]*w,n[3]*h]
      ];
      await update({graph_corners:graphCorners, reextract:true});
    } else if (session) {
      await update({});
    }
    status("Settings loaded.", "ready");
  } catch (error) {
    status("Could not load settings: " + error.message, "error");
  }
});


/* ------------------ User-customizable information panel layout ------------------ */

const PANEL_LAYOUT_KEY = "ydl7003p.panelLayout.v1";
let panelLayoutEditing = false;
let draggedPanel = null;
let dragArmedPanel = null;
let savePanelLayoutTimer = null;

function dashboardCards() {
  return [...document.querySelectorAll(".dashboard-card")];
}

function dashboardColumns() {
  return [...document.querySelectorAll(".panel-column")];
}

function savePanelLayout() {
  const layout = {
    columns: dashboardColumns().map(column => ({
      id: column.id,
      panels: [...column.querySelectorAll(".dashboard-card")].map(card => card.id)
    })),
    heights: Object.fromEntries(
      dashboardCards().map(card => [card.id, card.style.height || ""])
    )
  };
  localStorage.setItem(PANEL_LAYOUT_KEY, JSON.stringify(layout));
}

function schedulePanelLayoutSave() {
  clearTimeout(savePanelLayoutTimer);
  savePanelLayoutTimer = setTimeout(savePanelLayout, 180);
}

function restorePanelLayout() {
  let layout = null;
  try {
    layout = JSON.parse(localStorage.getItem(PANEL_LAYOUT_KEY) || "null");
  } catch (_) {
    layout = null;
  }
  if (!layout) return;

  (layout.columns || []).forEach(savedColumn => {
    const column = $(savedColumn.id);
    if (!column) return;
    (savedColumn.panels || []).forEach(panelId => {
      const panel = $(panelId);
      if (panel) column.appendChild(panel);
    });
  });

  Object.entries(layout.heights || {}).forEach(([panelId, height]) => {
    const panel = $(panelId);
    if (panel && height) panel.style.height = height;
  });
}

function setPanelLayoutEditing(enabled) {
  panelLayoutEditing = enabled;
  document.body.classList.toggle("layout-editing", enabled);
  $("customizeLayoutBtn").textContent = enabled ? "Finish panel layout" : "Customize panels";
  $("resetLayoutBtn").classList.toggle("hidden", !enabled);

  dashboardCards().forEach(card => {
    card.draggable = false;
  });

  if (enabled) {
    status("Panel layout mode: drag panels by ⋮⋮ and resize them from the lower edge. Changes are saved in this browser.", "warning");
  } else {
    savePanelLayout();
    status("Panel layout saved in this browser.", "ready");
    setTimeout(redrawAll, 80);
  }
}

function resetPanelLayout() {
  localStorage.removeItem(PANEL_LAYOUT_KEY);
  const controls = $("controlColumn");
  const results = $("resultColumn");
  ["axisCard", "sampleCard", "instrumentCard"].forEach(id => controls.appendChild($(id)));
  ["datetimeCard", "resultCard"].forEach(id => results.appendChild($(id)));
  dashboardCards().forEach(card => {
    card.style.height = "";
  });
  savePanelLayout();
  status("Default panel layout restored.", "ready");
  setTimeout(redrawAll, 80);
}

dashboardCards().forEach(card => {
  const handle = card.querySelector(".drag-handle");
  if (handle) {
    handle.addEventListener("pointerdown", () => {
      if (!panelLayoutEditing) return;
      dragArmedPanel = card;
      card.draggable = true;
    });
    handle.addEventListener("pointerup", () => {
      if (!draggedPanel) {
        card.draggable = false;
        dragArmedPanel = null;
      }
    });
  }

  card.addEventListener("dragstart", event => {
    if (!panelLayoutEditing || dragArmedPanel !== card) {
      event.preventDefault();
      return;
    }
    draggedPanel = card;
    card.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.id);
  });

  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
    card.draggable = false;
    draggedPanel = null;
    dragArmedPanel = null;
    dashboardColumns().forEach(column => column.classList.remove("drag-over"));
    savePanelLayout();
    setTimeout(redrawAll, 80);
  });
});

dashboardColumns().forEach(column => {
  column.addEventListener("dragover", event => {
    if (!panelLayoutEditing || !draggedPanel) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    column.classList.add("drag-over");

    const candidates = [...column.querySelectorAll(".dashboard-card:not(.dragging)")];
    const before = candidates.find(card => {
      const rect = card.getBoundingClientRect();
      return event.clientY < rect.top + rect.height / 2;
    });
    column.insertBefore(draggedPanel, before || null);
  });

  column.addEventListener("dragleave", event => {
    if (!column.contains(event.relatedTarget)) column.classList.remove("drag-over");
  });

  column.addEventListener("drop", event => {
    event.preventDefault();
    column.classList.remove("drag-over");
    savePanelLayout();
  });
});

if ("ResizeObserver" in window) {
  const panelResizeObserver = new ResizeObserver(() => {
    if (panelLayoutEditing) schedulePanelLayoutSave();
  });
  dashboardCards().forEach(card => panelResizeObserver.observe(card));
}

$("customizeLayoutBtn").addEventListener("click", () => {
  setPanelLayoutEditing(!panelLayoutEditing);
});

$("resetLayoutBtn").addEventListener("click", resetPanelLayout);

restorePanelLayout();
