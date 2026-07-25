
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
let pendingSettingsConfig = null;
let graphCornersEdited = false;
let axisConfirmationRequired = false;
let resultsProvisional = false;

function status(message, kind="ready") {
  const el = $("status");
  el.textContent = message;
  el.className = `status ${kind}`;
  setBusy(kind === "working");
}

function setBusy(busy) {
  document.documentElement.classList.toggle("busy", busy);
  document.body.classList.toggle("busy", busy);
}

function setTab(panelId) {
  if (panelId === "graphPanel" && resultsProvisional) {
    panelId = "screenPanel";
    status(
      "Analysis graph unavailable until the adjusted graph corners and axis calibration are confirmed.",
      "warning"
    );
  }
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


function settingsFilename() {
  const source = session?.source_name || selectedFile?.name || "mechanical_tester";
  const stem = source.replace(/\.[^.]+$/, "").replace(/[^\w.-]+/g, "_");
  const now = new Date();
  const stamp =
    `${now.getFullYear()}${pad2(now.getMonth()+1)}${pad2(now.getDate())}_` +
    `${pad2(now.getHours())}${pad2(now.getMinutes())}${pad2(now.getSeconds())}`;
  return `${stem}_settings_${stamp}.json`;
}

function currentSettingsConfig() {
  return YDLSettingsIO.buildSettingsConfig({
    sample: settingsPayload()
  });
}

async function saveSettingsWithPrompt(config) {
  const text = JSON.stringify(config, null, 2) + "\n";
  const suggestedName = settingsFilename();

  if (window.showSaveFilePicker && window.isSecureContext) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName,
        types: [{
          description: "JSON settings",
          accept: {"application/json": [".json"]}
        }]
      });
      const writable = await handle.createWritable();
      await writable.write(text);
      await writable.close();
      status(`Settings saved as ${handle.name}.`, "ready");
      return;
    } catch (error) {
      if (error?.name === "AbortError") {
        status("Saving settings was cancelled.", "warning");
        return;
      }
      console.warn("Native Save As dialog unavailable:", error);
    }
  }

  // Fallback for browsers without the File System Access API.
  const blob = new Blob([text], {type:"application/json;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = suggestedName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  status(
    "Settings download started. In browsers without a Save As API, the browser's download settings control whether a location is requested.",
    "ready"
  );
}

function putSettingsIntoControls(config) {
  const settings = config.sample || {};

  if (settings.gauge_length_mm !== null) {
    $("gauge").value = settings.gauge_length_mm;
  }
  if (settings.sample_width_mm !== null) {
    $("width").value = settings.sample_width_mm;
  }
  $("thickness").value = settings.thickness_um ?? "";
  $("grammage").value = settings.grammage_g_m2 ?? "";
}

function updatePayloadFromSettingsConfig(config) {
  putSettingsIntoControls(config);

  // Deliberately send only sample properties. The existing image retains its
  // own detected graph/axes, and every newly selected photograph is analysed
  // with fresh screen, graph and axis detection.
  return settingsPayload();
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

function setPanelLoading(id, active, message=null, detail=null) {
  const overlay = $(id);
  if (!overlay) return;
  overlay.classList.toggle("hidden", !active);
  if (message) {
    const strong = overlay.querySelector("strong");
    if (strong) strong.textContent = message;
  }
  if (detail) {
    const span = overlay.querySelector("span");
    if (span) span.textContent = detail;
  }
}

function setResultsProvisional(active) {
  resultsProvisional = Boolean(active);

  const graphNotice = $("graphProvisional");
  const resultNotice = $("resultProvisional");
  const resultCard = $("resultCard");
  const analysisTab = $("analysisTab");
  const analysisCanvas = $("analysisCanvas");

  if (graphNotice) graphNotice.classList.toggle("hidden", !resultsProvisional);
  if (resultNotice) resultNotice.classList.toggle("hidden", !resultsProvisional);
  if (resultCard) resultCard.classList.toggle("results-provisional", resultsProvisional);

  if (analysisTab) {
    analysisTab.disabled = resultsProvisional;
    analysisTab.title = resultsProvisional
      ? "Confirm axis calibration after applying the adjusted graph corners."
      : "";
  }

  document.querySelectorAll("[data-export]").forEach(button => {
    button.disabled = resultsProvisional;
    button.title = resultsProvisional
      ? "Exports are unavailable until axis calibration is confirmed."
      : "";
  });

  if (analysisCanvas) {
    analysisCanvas.style.pointerEvents = resultsProvisional ? "none" : "";
  }

  const graphPanel = document.querySelector("#graphPanel");
  if (resultsProvisional && graphPanel?.classList.contains("active")) {
    setTab("screenPanel");
  }
}

function clearAxisSuggestion(force=false) {
  // Manual graph-corner changes must remain visibly unconfirmed until the user
  // clicks the confirmation button.
  if (axisConfirmationRequired && !force) return;
  $("axisCard").classList.remove("needs-confirmation", "auto-updated");
  $("axisHint").classList.add("hidden");
  $("axisHint").textContent = "";
}

function requireAxisConfirmation(message=null) {
  axisConfirmationRequired = true;
  setResultsProvisional(true);
  $("axisHint").textContent = message ||
    "Graph corners were changed manually. Verify X min, X max, Y min and Y max, then click “Confirm axes and re-extract curve”.";
  $("axisHint").classList.remove("hidden");
  $("axisCard").classList.remove("auto-updated");
  $("axisCard").classList.add("needs-confirmation");
  $("axisCard").scrollIntoView({behavior:"smooth", block:"center"});

  // X max is normally the most likely value to need attention after the
  // horizontal graph boundary changes.
  setTimeout(() => {
    $("xmax").focus({preventScroll:true});
    $("xmax").select();
  }, 350);

  status("Graph corners applied. Please confirm the highlighted axis calibration.", "warning");
}

function applyAxisSuggestions(suggestions) {
  if (!suggestions || !Object.keys(suggestions).length) {
    return false;
  }
  axisConfirmationRequired = true;
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

function imageAppearsBlankOrDark(image) {
  if (!image?.naturalWidth || !image?.naturalHeight) return true;
  const sample = document.createElement("canvas");
  sample.width = 32;
  sample.height = 20;
  const ctx = sample.getContext("2d", {willReadFrequently:true});
  ctx.drawImage(image, 0, 0, sample.width, sample.height);
  const pixels = ctx.getImageData(0, 0, sample.width, sample.height).data;
  let brightness = 0;
  let nonBlack = 0;
  const count = pixels.length / 4;
  for (let i = 0; i < pixels.length; i += 4) {
    const value = (pixels[i] + pixels[i+1] + pixels[i+2]) / 3;
    brightness += value;
    if (value > 12) nonBlack += 1;
  }
  return brightness / count < 8 || nonBlack / count < 0.04;
}

async function loadCorrectedScreenImage(data) {
  try {
    await loadImage(screenImage, data.images.annotated);
    if (!imageAppearsBlankOrDark(screenImage)) return;
    console.warn("Annotated corrected-screen image was blank/dark; using rectified image.");
  } catch (error) {
    console.warn("Could not load annotated corrected-screen image:", error);
  }
  await loadImage(screenImage, data.images.rectified);
}

async function applyResponse(data, options={}) {
  session = data;
  analysisMeta = data.analysis_graph_meta || null;
  if (data.axis_confirmation_required) {
    axisConfirmationRequired = true;
    setResultsProvisional(true);
  }
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

  showResults(data.result, data.settings);
  renderValidation(data.layout_validation);

  // Results are already available. Show loading guidance while image files are
  // still being transferred to the browser.
  setPanelLoading(
    "screenLoading",
    true,
    "Loading corrected screen…",
    "The image analysis is ready. The corrected screen image is being transferred and rendered."
  );
  setPanelLoading(
    "graphLoading",
    true,
    "Loading analysis graph…",
    "The numerical results are already available. The graph image may take a little longer to appear."
  );

  await Promise.all([
    loadImage(originalImage, data.images.original),
    loadImage(rectifiedImage, data.images.rectified)
  ]);
  drawOriginal();

  const correctedPromise = (async () => {
    await loadCorrectedScreenImage(data);
    if (options.initial) {
      if (data.layout_validation?.compliant && !axisConfirmationRequired) {
        setTab("screenPanel");
      } else if (!data.layout_validation?.compliant) {
        setTab("originalPanel");
      }
    }
    requestAnimationFrame(() => requestAnimationFrame(drawScreen));
    setPanelLoading("screenLoading", false);

    if (options.initial && data.layout_validation?.compliant && !axisConfirmationRequired) {
      status("Corrected screen ready. Loading analysis graph…", "ready");
    }
  })();

  const analysisPromise = (async () => {
    await loadImage(analysisImage, data.images.analysis_graph);
    requestAnimationFrame(() => requestAnimationFrame(drawAnalysis));
    setPanelLoading("graphLoading", false);
  })();

  const suggested = applyAxisSuggestions(data.axis_suggestions);
  if (!suggested) {
    clearAxisSuggestion();
    if (axisConfirmationRequired) {
      requireAxisConfirmation();
    } else if (data.axis_auto_updated) {
      $("axisHint").textContent =
        `Graph and axes auto-detected: X ${data.result.x_min}–${data.result.x_max} mm, ` +
        `Y ${data.result.y_min}–${data.result.y_max} N.`;
      $("axisHint").classList.remove("hidden");
      $("axisCard").classList.add("auto-updated");
      setTimeout(() => $("axisCard").classList.remove("auto-updated"), 2400);
    }
  }

  await correctedPromise;

  if (options.initial) {
    if (!data.layout_validation?.compliant) {
      status("Image analysed, but the expected completed-test layout was not confirmed.", "warning");
    }
  } else if (!axisConfirmationRequired && !data.axis_auto_updated && !suggested) {
    status("Corrected screen ready. Loading analysis graph…", "ready");
  }

  await analysisPromise;

  if (!suggested) {
    if (axisConfirmationRequired) {
      requireAxisConfirmation();
    } else if (data.axis_auto_updated) {
      status("Graph area and axis calibration updated automatically.", "ready");
    } else if (options.initial) {
      if (data.layout_validation?.compliant && !axisConfirmationRequired) {
        status("Analysis ready. Review the corrected screen and graph corners.", "ready");
      }
    } else {
      status("Ready.", "ready");
    }
  }

  requestAnimationFrame(() => requestAnimationFrame(redrawAll));
}

function f(value, digits=2) {
  return value == null || !Number.isFinite(Number(value)) ? "—" : Number(value).toFixed(digits);
}

function showResults(r, settings={}) {
  const manual = r.break_is_manual ? " (manual)" : "";
  const stiffnessIndexText = settings.grammage_g_m2 == null
    ? "not calculated (grammage not provided)"
    : `${f(r.tensile_stiffness_index_knm_per_kg,3)} kN·m/kg`;
  const modulusText = settings.thickness_um == null
    ? "not calculated (thickness not provided)"
    : `${f(r.elastic_modulus_mpa,3)} MPa`;

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
Stiffness index: ${stiffnessIndexText}
Tensile modulus: ${modulusText}

Tensile energy: ${f(r.toughness_n_mm,3)} N·mm (${f(r.toughness_mj,3)} mJ)
Curve points: ${r.curve_points}
${r.mechanical_note ? "\nNote: " + r.mechanical_note : ""}`;
}

function fitCanvas(canvas, image) {
  if (!image.naturalWidth || !image.naturalHeight) return null;
  const wrap = canvas.parentElement;
  const availableWidth = wrap.clientWidth;
  const availableHeight = wrap.clientHeight;

  // A display:none tab reports zero dimensions. Leave that canvas untouched
  // and redraw it after the tab becomes visible.
  if (availableWidth < 2 || availableHeight < 2) return null;

  const scale = Math.min(
    availableWidth / image.naturalWidth,
    availableHeight / image.naturalHeight
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
  if (scale == null) return;
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
  if (scale == null) return;
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
  if (scale == null) return;
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
    if (!graphCornersEdited) {
      graphCornersEdited = true;
      setResultsProvisional(true);
      status(
        "Graph corner adjusted. Apply the graph corners, then confirm the axis calibration.",
        "warning"
      );
    }
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
  graphCornersEdited = false;
  axisConfirmationRequired = false;
  setResultsProvisional(false);
  clearAxisSuggestion(true);

  rectifiedImage = new Image();
  screenImage = new Image();
  analysisImage = new Image();

  const serial = ++analysisSerial;
  const form = new FormData();
  form.append("image", file);
  Object.entries(settingsPayload()).forEach(([key,value]) => {
    // Submit optional fields even when empty, so blank values are preserved.
    if (key === "thickness_um" || key === "grammage_g_m2") {
      form.append(key, value == null ? "" : value);
    } else if (value !== null) {
      form.append(key, value);
    }
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

    if (pendingSettingsConfig) {
      const config = pendingSettingsConfig;
      const payload = updatePayloadFromSettingsConfig(config);
      data = await api(`/api/session/${data.session_id}/update`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
      });
      pendingSettingsConfig = null;
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
  graphCornersEdited = false;
  axisConfirmationRequired = false;
  setResultsProvisional(false);
  renderValidation(null);
  clearAxisSuggestion(true);
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
    return data;
  } catch (error) {
    console.error(error);
    return null;
  }
}

$("applyCornersBtn").onclick = () => update({screen_corners:corners});

$("applyGraphBtn").onclick = async () => {
  const wasEdited = graphCornersEdited;
  const data = await update({
    graph_corners:graphCorners,
    reextract:true,
    manual_graph_adjustment:wasEdited
  });
  if (data && wasEdited) {
    graphCornersEdited = false;
    requireAxisConfirmation(
      "Graph corners were changed manually and have now been applied. Verify all four axis values, then click “Confirm axes and re-extract curve”."
    );
  }
};

$("autoGraphBtn").onclick = async () => {
  graphCornersEdited = false;
  const data = await update({auto_graph:true, reextract:true});
  if (data) {
    axisConfirmationRequired = false;
    clearAxisSuggestion(true);
    setResultsProvisional(false);
    status("Graph area and axis calibration updated automatically.", "ready");
  }
};

$("reextractBtn").onclick = async () => {
  const confirmingManualCorners =
    axisConfirmationRequired || session?.axis_confirmation_required;
  const data = await update({
    reextract:true,
    axis_confirmed:confirmingManualCorners
  });
  if (data) {
    axisConfirmationRequired = false;
    clearAxisSuggestion(true);
    setResultsProvisional(false);
    status("Axis calibration confirmed and curve re-extracted.", "ready");
  }
};
$("updateCalcBtn").onclick = () => update({});
$("editedBtn").onclick = () => update({
  elongation:num("elongation",null),
  max_force:num("maxForce",null)
});

["xmin","xmax","ymin","ymax"].forEach(id => {
  $(id).addEventListener("input", () => clearAxisSuggestion(false));
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
  if (
    resultsProvisional ||
    !event.ctrlKey || event.button !== 0 ||
    !session || !analysisMeta?.plot
  ) return;

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
    if (resultsProvisional || session?.axis_confirmation_required) {
      status(
        "Exports are unavailable until the adjusted graph corners and axis calibration are confirmed.",
        "warning"
      );
      return;
    }
    if (!session) {
      status("Analyse an image first.", "error");
      return;
    }
    window.location = `/api/session/${session.session_id}/export/${button.dataset.export}`;
  };
});

$("saveSettingsBtn").onclick = async () => {
  try {
    const config = currentSettingsConfig();
    await saveSettingsWithPrompt(config);
  } catch (error) {
    console.error(error);
    status("Could not save settings: " + error.message, "error");
  }
};

$("settingsFile").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;

  try {
    const parsed = JSON.parse(await file.text());
    const config = YDLSettingsIO.validateSettingsConfig(parsed);
    putSettingsIntoControls(config);

    if (session) {
      const payload = updatePayloadFromSettingsConfig(config);
      const data = await api(`/api/session/${session.session_id}/update`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
      });
      await applyResponse(data);
      status(`Settings loaded from ${file.name}.`, "ready");
    } else {
      pendingSettingsConfig = config;
      status(
        `Settings loaded from ${file.name}. They will be applied automatically to the next analysed image.`,
        "ready"
      );
    }
  } catch (error) {
    status("Could not load settings: " + error.message, "error");
  } finally {
    // Permit the user to select the same file again.
    event.target.value = "";
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
