let attire = "black";
const ATTIRE = {
  black: "Classic black suit", navy: "Navy suit", charcoal: "Charcoal suit",
  dress: "Black formal dress", blouse: "Blazer & blouse",
  clerical: "Clerical collar", custom: "Upload my own suit"
};
const $ = id => document.getElementById(id);
const setStatus = t => $("status").textContent = t;

function renderAttire() {
  const grid = $("attireGrid");
  grid.innerHTML = "";
  Object.keys(ATTIRE).forEach(id => {
    const d = document.createElement("div");
    d.className = "attire" + (id === attire ? " selected" : "");
    d.textContent = ATTIRE[id];
    d.onclick = () => {
      attire = id; renderAttire();
      $("suitUploadWrap").style.display = id === "custom" ? "block" : "none";
    };
    grid.appendChild(d);
  });
}

async function refreshMe() {
  const r = await fetch("/api/me");
  const j = await r.json();
  if (!j.user) {
    $("loginCard").style.display = "block";
    $("dash").style.display = "none";
    return null;
  }
  $("loginCard").style.display = "none";
  $("dash").style.display = "block";
  $("bizName").textContent = j.user.business;
  $("inactiveCard").style.display = j.user.active ? "none" : "block";
  return j.user;
}

async function loadHistory() {
  const r = await fetch("/api/staff/jobs");
  if (!r.ok) return;
  const jobs = await r.json();
  const h = $("history");
  h.innerHTML = "";
  jobs.forEach(job => {
    const d = document.createElement("div");
    d.className = "attire";
    d.innerHTML = `<img src="${job.image_url}" style="width:100%;border-radius:6px"><br>
      <small>${job.created.slice(0, 10)} · ${job.product}</small><br>
      <a href="${job.download_url}" style="color:var(--gold)">Download</a>`;
    h.appendChild(d);
  });
  if (!jobs.length) h.innerHTML = "<p class='hint'>No portraits yet.</p>";
}

$("loginBtn").onclick = async () => {
  const r = await fetch("/api/login", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ email: $("email").value, password: $("pw").value })
  });
  const j = await r.json();
  if (!r.ok) { $("loginStatus").textContent = j.error; return; }
  await refreshMe();
  await loadHistory();
};

$("logoutBtn").onclick = async () => {
  await fetch("/api/logout", { method: "POST" });
  location.reload();
};

const openPortal = async () => {
  const r = await fetch("/api/portal", { method: "POST" });
  const j = await r.json();
  if (j.url) window.location.href = j.url;
};
$("portalBtn").onclick = openPortal;
$("portalBtn2").onclick = openPortal;

$("photo").onchange = e => {
  const f = e.target.files[0];
  if (!f) return;
  const img = $("photoThumb");
  img.src = URL.createObjectURL(f);
  img.style.display = "block";
};

$("generateBtn").onclick = async () => {
  const photo = $("photo").files[0];
  if (!photo) { setStatus("Please upload a photo first."); return; }
  const style = document.querySelector('input[name=style]:checked').value;
  const btn = $("generateBtn");
  btn.disabled = true;
  setStatus("Creating portrait… about 30 seconds.");
  const fd = new FormData();
  fd.append("photo", photo);
  fd.append("attire", attire);
  fd.append("style", style);
  if (attire === "custom") {
    const ref = $("suitPhoto").files[0];
    if (!ref) { setStatus("Please upload the suit photo."); btn.disabled = false; return; }
    fd.append("suit_photo", ref);
  }
  try {
    const r = await fetch("/api/staff/generate", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "failed");
    $("resultImg").src = j.image_url + "?t=" + Date.now();
    $("resultImg").style.display = "block";
    const dl = $("dlLink");
    dl.href = "/download/" + j.job_id;
    dl.style.display = "inline-block";
    setStatus("");
    await loadHistory();
  } catch (e) {
    setStatus("Something went wrong: " + e.message);
  }
  btn.disabled = false;
};

(async () => {
  renderAttire();
  const user = await refreshMe();
  if (user) await loadHistory();
})();
