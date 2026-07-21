
const $ = id => document.getElementById(id);
let session = null;
let originalImage = new Image();
let screenImage = new Image();
let analysisImage = new Image();
let corners = [];
let graphRect = null;
let drag = null;

function status(msg, error=false) {
  $("status").textContent = msg;
  $("status").style.color = error ? "#b42318" : "";
}
function num(id, fallback=null) {
  const v = parseFloat($(id).value);
  return Number.isFinite(v) ? v : fallback;
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
  status("Working…");
  const res = await fetch(url, options);
  let data;
  const ct = res.headers.get("content-type") || "";
  data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = data?.detail || data || `HTTP ${res.status}`;
    status(msg, true);
    throw new Error(msg);
  }
  status("Ready.");
  return data;
}
function loadImage(img, url) {
  return new Promise((resolve,reject)=>{
    img.onload=resolve; img.onerror=reject;
    img.src=url + (url.includes("?")?"&":"?") + "t=" + Date.now();
  });
}
async function applyResponse(data) {
  session = data;
  corners = data.screen_corners.map(p => [...p]);
  graphRect = data.result.graph_plot ? {...data.result.graph_plot} : null;
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
  showResults(data.result);
  await Promise.all([
    loadImage(originalImage, data.images.original),
    loadImage(screenImage, data.images.annotated),
    loadImage(analysisImage, data.images.analysis_graph)
  ]);
  redrawAll();
}
function f(v,d=2) { return v==null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(d); }
function showResults(r) {
  $("results").textContent =
`Instrument extension: ${f(r.elongation)} mm
Instrument strain: ${f(r.elongation_text_percent)} %
Curve break extension: ${f(r.elongation_data)} mm
Curve strain at break: ${f(r.elongation_data_percent)} %

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
function fitCanvas(canvas, img) {
  const wrap = canvas.parentElement;
  const scale = Math.min(wrap.clientWidth/img.naturalWidth, wrap.clientHeight/img.naturalHeight);
  canvas.width = Math.max(1, Math.round(img.naturalWidth*scale));
  canvas.height = Math.max(1, Math.round(img.naturalHeight*scale));
  return scale;
}
function handle(ctx,x,y) {
  ctx.beginPath(); ctx.arc(x,y,8,0,Math.PI*2);
  ctx.fillStyle="#ffd400"; ctx.fill();
  ctx.lineWidth=2; ctx.strokeStyle="#111"; ctx.stroke();
}
function drawOriginal() {
  if (!session || !originalImage.complete) return;
  const c=$("originalCanvas"), s=fitCanvas(c,originalImage), ctx=c.getContext("2d");
  ctx.drawImage(originalImage,0,0,c.width,c.height);
  ctx.strokeStyle="#ffd400"; ctx.lineWidth=3;
  ctx.beginPath();
  corners.forEach((p,i)=>{ const x=p[0]*s,y=p[1]*s; i?ctx.lineTo(x,y):ctx.moveTo(x,y); });
  ctx.closePath(); ctx.stroke();
  corners.forEach(p=>handle(ctx,p[0]*s,p[1]*s));
  c.dataset.scale=s;
}
function graphPoints() {
  if (!graphRect) return [];
  return [
    [graphRect.x1,graphRect.y1],[graphRect.x2,graphRect.y1],
    [graphRect.x2,graphRect.y2],[graphRect.x1,graphRect.y2]
  ];
}
function drawScreen() {
  if (!session || !screenImage.complete) return;
  const c=$("screenCanvas"), s=fitCanvas(c,screenImage), ctx=c.getContext("2d");
  ctx.drawImage(screenImage,0,0,c.width,c.height);
  const pts=graphPoints();
  if (pts.length) {
    ctx.strokeStyle="#ffd400"; ctx.lineWidth=3;
    ctx.strokeRect(graphRect.x1*s,graphRect.y1*s,(graphRect.x2-graphRect.x1)*s,(graphRect.y2-graphRect.y1)*s);
    pts.forEach(p=>handle(ctx,p[0]*s,p[1]*s));
  }
  c.dataset.scale=s;
}
function drawAnalysis() {
  if (!session || !analysisImage.complete) return;
  const c=$("analysisCanvas"); fitCanvas(c,analysisImage);
  c.getContext("2d").drawImage(analysisImage,0,0,c.width,c.height);
}
function redrawAll(){ drawOriginal(); drawScreen(); drawAnalysis(); }
function nearest(points,x,y,limit=18) {
  let best=-1,dist=Infinity;
  points.forEach((p,i)=>{ const d=Math.hypot(p[0]-x,p[1]-y); if(d<dist){dist=d;best=i;} });
  return dist<=limit?best:-1;
}
$("originalCanvas").addEventListener("pointerdown",e=>{
  const c=e.currentTarget,s=Number(c.dataset.scale),r=c.getBoundingClientRect();
  const idx=nearest(corners.map(p=>[p[0]*s,p[1]*s]),e.clientX-r.left,e.clientY-r.top);
  if(idx>=0){drag={type:"corner",idx};c.setPointerCapture(e.pointerId);}
});
$("originalCanvas").addEventListener("pointermove",e=>{
  if(!drag||drag.type!=="corner")return;
  const c=e.currentTarget,s=Number(c.dataset.scale),r=c.getBoundingClientRect();
  corners[drag.idx]=[(e.clientX-r.left)/s,(e.clientY-r.top)/s]; drawOriginal();
});
$("originalCanvas").addEventListener("pointerup",()=>drag=null);

$("screenCanvas").addEventListener("pointerdown",e=>{
  const c=e.currentTarget,s=Number(c.dataset.scale),r=c.getBoundingClientRect();
  const idx=nearest(graphPoints().map(p=>[p[0]*s,p[1]*s]),e.clientX-r.left,e.clientY-r.top);
  if(idx>=0){drag={type:"graph",idx};c.setPointerCapture(e.pointerId);}
});
$("screenCanvas").addEventListener("pointermove",e=>{
  if(!drag||drag.type!=="graph"||!graphRect)return;
  const c=e.currentTarget,s=Number(c.dataset.scale),r=c.getBoundingClientRect();
  const x=(e.clientX-r.left)/s,y=(e.clientY-r.top)/s;
  if(drag.idx===0){graphRect.x1=x;graphRect.y1=y;}
  if(drag.idx===1){graphRect.x2=x;graphRect.y1=y;}
  if(drag.idx===2){graphRect.x2=x;graphRect.y2=y;}
  if(drag.idx===3){graphRect.x1=x;graphRect.y2=y;}
  if(graphRect.x1>graphRect.x2)[graphRect.x1,graphRect.x2]=[graphRect.x2,graphRect.x1];
  if(graphRect.y1>graphRect.y2)[graphRect.y1,graphRect.y2]=[graphRect.y2,graphRect.y1];
  drawScreen();
});
$("screenCanvas").addEventListener("pointerup",()=>drag=null);

$("analyzeBtn").onclick=async()=>{
  const file=$("imageFile").files[0];
  if(!file){status("Choose an image first.",true);return;}
  const form=new FormData(); form.append("image",file);
  Object.entries(settingsPayload()).forEach(([k,v])=>{if(v!==null)form.append(k,v);});
  try{await applyResponse(await api("/api/analyze",{method:"POST",body:form}));}
  catch(e){console.error(e);}
};
async function update(extra={}) {
  if(!session){status("Analyse an image first.",true);return;}
  const payload={...settingsPayload(),
    x_min:num("xmin",0),x_max:num("xmax",5),y_min:num("ymin",0),y_max:num("ymax",120),...extra};
  try{await applyResponse(await api(`/api/session/${session.session_id}/update`,{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}));}
  catch(e){console.error(e);}
}
$("applyCornersBtn").onclick=()=>update({screen_corners:corners});
$("applyGraphBtn").onclick=()=>update({graph_plot:graphRect,reextract:true});
$("autoGraphBtn").onclick=()=>update({auto_graph:true,reextract:true});
$("reextractBtn").onclick=()=>update({reextract:true});
$("updateCalcBtn").onclick=()=>update({});
$("editedBtn").onclick=()=>update({elongation:num("elongation",null),max_force:num("maxForce",null)});
$("trainBtn").onclick=async()=>{
  if(!session)return;
  if(!confirm("Teach the shared recognizer from these corrected values?"))return;
  try{
    const data=await api(`/api/session/${session.session_id}/train`,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({elongation:$("elongation").value,max_force:$("maxForce").value})
    });
    status(`Recognizer updated. Added: ${JSON.stringify(data.added)}`);
  }catch(e){console.error(e);}
};
$("fitBtn").onclick=redrawAll;
window.addEventListener("resize",()=>setTimeout(redrawAll,100));
document.querySelectorAll(".tab").forEach(btn=>btn.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(".panel").forEach(x=>x.classList.remove("active"));
  btn.classList.add("active"); $(btn.dataset.tab).classList.add("active");
  setTimeout(redrawAll,50);
});
document.querySelectorAll("[data-export]").forEach(btn=>btn.onclick=()=>{
  if(!session){status("Analyse an image first.",true);return;}
  window.location=`/api/session/${session.session_id}/export/${btn.dataset.export}`;
});
$("saveSettingsBtn").onclick=()=>{
  if(!session){status("Analyse an image first.",true);return;}
  window.location=`/api/session/${session.session_id}/settings`;
};
$("settingsFile").addEventListener("change",async e=>{
  const file=e.target.files[0]; if(!file)return;
  try{
    const cfg=JSON.parse(await file.text());
    const s=cfg.sample||cfg;
    if(s.gauge_length_mm!=null)$("gauge").value=s.gauge_length_mm;
    if(s.sample_width_mm!=null)$("width").value=s.sample_width_mm;
    if(s.thickness_um!=null)$("thickness").value=s.thickness_um;
    if(s.grammage_g_m2!=null)$("grammage").value=s.grammage_g_m2;
    if(session && cfg.graph_plot_norm){
      const n=cfg.graph_plot_norm,w=session.rectified_size.width,h=session.rectified_size.height;
      graphRect={x1:n[0]*w,y1:n[1]*h,x2:n[2]*w,y2:n[3]*h};
      await update({graph_plot:graphRect,reextract:true});
    } else if(session) await update({});
    status("Settings loaded.");
  }catch(err){status("Could not load settings: "+err.message,true);}
});
