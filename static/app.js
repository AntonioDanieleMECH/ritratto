let lang = "fr";
let attire = "black";
let jobId = null;
let product = "digital";
let versions = 0;
let currentVersion = 1;
let attemptsLeft = 0;
let paidMode = false;
const MAX_ATTEMPTS = 15;

// Parse a JSON response, but show a friendly message if the server
// answered with an HTML error page (e.g. mid-deploy) instead.
async function safeJson(r) {
  const text = await r.text();
  try { return JSON.parse(text); }
  catch (e) {
    throw new Error(lang === "en"
      ? "The server is briefly updating — please try again in a minute."
      : "Le serveur est brièvement en mise à jour — réessayez dans une minute.");
  }
}

const ATTIRE_LABELS = {
  en: { black: "Classic black suit", navy: "Navy suit", charcoal: "Charcoal suit",
        dress: "Black formal dress", blouse: "Blazer & blouse", clerical: "Clerical collar",
        custom: "Upload my own suit" },
  fr: { black: "Complet noir classique", navy: "Complet bleu marine", charcoal: "Complet gris anthracite",
        dress: "Robe noire de cérémonie", blouse: "Veston et chemisier", clerical: "Col romain",
        custom: "Téléverser mon propre complet" }
};

function applyLang() {
  document.querySelectorAll("[data-en]").forEach(el => {
    el.textContent = el.dataset[lang];
  });
  document.documentElement.lang = lang;
  document.getElementById("langToggle").textContent = lang === "en" ? "FR" : "EN";
  document.getElementById("regenNote").placeholder = lang === "en"
    ? "E.g. make the suit darker, fix the smile…"
    : "Ex. : complet plus foncé, corriger le sourire…";
  updateRegenUI();
  renderAttire();
}
document.getElementById("langToggle").onclick = () => {
  lang = lang === "en" ? "fr" : "en";
  applyLang();
};

function renderAttire() {
  const grid = document.getElementById("attireGrid");
  grid.innerHTML = "";
  Object.keys(ATTIRE_LABELS[lang]).forEach(id => {
    const d = document.createElement("div");
    d.className = "attire" + (id === attire ? " selected" : "");
    d.textContent = ATTIRE_LABELS[lang][id];
    d.onclick = () => {
      attire = id;
      renderAttire();
      document.getElementById("suitUploadWrap").style.display =
        id === "custom" ? "block" : "none";
    };
    grid.appendChild(d);
  });
}

document.getElementById("photo").onchange = e => {
  const f = e.target.files[0];
  if (!f) return;
  const img = document.getElementById("photoThumb");
  img.src = URL.createObjectURL(f);
  img.style.display = "block";
};

const statusEl = document.getElementById("status");
const setStatus = t => statusEl.textContent = t;

// ---------- version browsing ----------
function showVersion(v) {
  currentVersion = Math.min(Math.max(v, 1), versions);
  document.getElementById("previewImg").src =
    `/preview/${jobId}?v=${currentVersion}&t=${Date.now()}`;
  document.getElementById("verLabel").textContent = lang === "en"
    ? `Version ${currentVersion} of ${versions}`
    : `Version ${currentVersion} sur ${versions}`;
  document.getElementById("prevVer").disabled = currentVersion <= 1;
  document.getElementById("nextVer").disabled = currentVersion >= versions;
  if (paidMode) {
    document.getElementById("dlBtn").onclick = () =>
      window.location.href = `/download/${jobId}?v=${currentVersion}`;
  }
}

function updateRegenUI() {
  const left = attemptsLeft;
  document.getElementById("attemptsLabel").textContent = lang === "en"
    ? `${left} regeneration${left === 1 ? "" : "s"} left`
    : `${left} régénération${left === 1 ? "" : "s"} restante${left === 1 ? "" : "s"}`;
  if (left <= 0 && !paidMode) {
    document.getElementById("regenBox").style.display = "none";
    document.getElementById("sorryBox").style.display = "block";
  }
}

document.getElementById("prevVer").onclick = () => showVersion(currentVersion - 1);
document.getElementById("nextVer").onclick = () => showVersion(currentVersion + 1);

document.getElementById("regenBtn").onclick = async () => {
  const btn = document.getElementById("regenBtn");
  const note = document.getElementById("regenNote").value.trim();
  const rs = document.getElementById("regenStatus");
  btn.disabled = true;
  rs.textContent = lang === "en"
    ? "Creating a new version… about 30 seconds."
    : "Création d'une nouvelle version… environ 30 secondes.";
  try {
    const r = await fetch("/api/regenerate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, note })
    });
    const j = await safeJson(r);
    if (!r.ok) throw new Error(j.error || "failed");
    versions = j.version;
    attemptsLeft = j.attempts_left;
    document.getElementById("regenNote").value = "";
    rs.textContent = "";
    showVersion(j.version);
    updateRegenUI();
  } catch (e) {
    rs.textContent = (lang === "en" ? "Something went wrong: " : "Une erreur est survenue : ") + e.message;
  }
  btn.disabled = false;
};

// ---------- first generation ----------
document.getElementById("generateBtn").onclick = async () => {
  const photo = document.getElementById("photo").files[0];
  if (!photo) { setStatus(lang === "en" ? "Please upload a photo first." : "Veuillez d'abord téléverser une photo."); return; }
  const style = document.querySelector('input[name=style]:checked').value;
  product = style === "refine" ? "refined" : "digital";
  const btn = document.getElementById("generateBtn");
  btn.disabled = true;
  setStatus(lang === "en" ? "Creating your portrait… about 30 seconds." : "Création de votre portrait… environ 30 secondes.");

  const fd = new FormData();
  fd.append("photo", photo);
  fd.append("attire", attire);
  fd.append("style", style);
  if (attire === "custom") {
    const ref = document.getElementById("suitPhoto").files[0];
    if (!ref) { setStatus(lang === "en" ? "Please upload the suit photo." : "Veuillez téléverser la photo du complet."); btn.disabled = false; return; }
    fd.append("suit_photo", ref);
  }
  try {
    const r = await fetch("/api/generate", { method: "POST", body: fd });
    const j = await safeJson(r);
    if (!r.ok) throw new Error(j.error || "failed");
    jobId = j.job_id;
    versions = j.version;
    attemptsLeft = j.attempts_left;
    paidMode = false;
    document.getElementById("step4").style.display = "block";
    document.getElementById("regenBox").style.display = "block";
    document.getElementById("sorryBox").style.display = "none";
    document.getElementById("payBtn").style.display = "inline-block";
    document.getElementById("dlBtn").style.display = "none";
    const payBtn = document.getElementById("payBtn");
    payBtn.textContent = product === "refined"
      ? (lang === "en" ? "Purchase — $4.99" : "Acheter — 4,99 $")
      : (lang === "en" ? "Purchase — $9.99" : "Acheter — 9,99 $");
    showVersion(1);
    updateRegenUI();
    document.getElementById("step4").scrollIntoView({ behavior: "smooth" });
    setStatus("");
  } catch (e) {
    setStatus((lang === "en" ? "Something went wrong: " : "Une erreur est survenue : ") + e.message);
  }
  btn.disabled = false;
};

document.getElementById("payBtn").onclick = async () => {
  const r = await fetch("/api/checkout", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, product, version: currentVersion })
  });
  const j = await safeJson(r);
  if (j.url) window.location.href = j.url;
  else if (j.error) setStatus((lang === "en" ? "Something went wrong: " : "Une erreur est survenue : ") + j.error);
};

// ---- Custom lamp designer ----
const lampSides = [null, null, null, null]; // {kind:'gallery',id,name,img} | {kind:'upload',file,img}
let activeSide = 0;
const sideSlots = [...document.querySelectorAll(".side-slot")];

function renderSides() {
  sideSlots.forEach((slot, i) => {
    slot.classList.toggle("active", i === activeSide);
    const prev = slot.querySelector(".side-prev");
    const s = lampSides[i];
    prev.innerHTML = s ? `<img src="${s.img}" alt="">` : `<span class="empty">${lang === "en" ? "tap a saint or upload" : "touchez un saint ou téléversez"}</span>`;
  });
}
sideSlots.forEach((slot, i) => {
  slot.addEventListener("click", e => {
    if (e.target.closest(".side-upload") || e.target.closest(".side-file")) return;
    activeSide = i;
    renderSides();
  });
  const upBtn = slot.querySelector(".side-upload");
  const fileInput = slot.querySelector(".side-file");
  upBtn.onclick = () => fileInput.click();
  fileInput.onchange = async () => {
    const f = fileInput.files[0];
    if (!f) return;
    upBtn.disabled = true;
    upBtn.textContent = lang === "en" ? "Uploading…" : "Téléversement…";
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch("/api/lamp-upload", { method: "POST", body: fd });
      const j = await safeJson(r);
      if (!r.ok) throw new Error(j.error || "failed");
      lampSides[i] = { kind: "upload", file: j.file, img: j.url, name: lang === "en" ? "your photo" : "votre photo" };
      slot.querySelector(".side-ai-check").checked = false;
      activeSide = Math.min(i + 1, 3);
      renderSides();
    } catch (e) {
      alert((lang === "en" ? "Upload failed: " : "Échec du téléversement : ") + e.message);
    }
    upBtn.disabled = false;
    upBtn.textContent = lang === "en" ? "Upload photo" : "Téléverser une photo";
    fileInput.value = "";
  };
});
document.querySelectorAll("#saintGallery .gal").forEach(card => {
  card.addEventListener("click", () => {
    if (card.dataset.upload) { // "Photo of your loved one" -> upload for active side
      sideSlots[activeSide].querySelector(".side-file").click();
      return;
    }
    lampSides[activeSide] = {
      kind: "gallery",
      id: card.dataset.gid,
      name: lang === "en" ? card.dataset.nameEn : card.dataset.nameFr,
      img: card.querySelector("img").src
    };
    sideSlots[activeSide].querySelector(".side-ai-check").checked = false;
    activeSide = Math.min(activeSide + 1, 3);
    renderSides();
  });
});

// "Use my AI portrait" checkbox in each side slot: uses the customer's
// paid, currently-selected portrait version for that side.
sideSlots.forEach((slot, i) => {
  const check = slot.querySelector(".side-ai-check");
  check.addEventListener("change", async () => {
    if (!check.checked) {
      if (lampSides[i] && lampSides[i].kind === "portrait") lampSides[i] = null;
      renderSides();
      return;
    }
    if (!jobId) {
      alert(lang === "en"
        ? "Generate a portrait above first, then tick this box."
        : "Générez d'abord un portrait ci-dessus, puis cochez cette case.");
      check.checked = false;
      return;
    }
    check.disabled = true;
    try {
      const r = await fetch("/api/status/" + jobId);
      const j = await safeJson(r);
      if (!j.paid || !j.versions) throw new Error(lang === "en"
        ? "That portrait hasn't been purchased yet — buy it above first."
        : "Ce portrait n'a pas encore été acheté — achetez-le ci-dessus d'abord.");
      lampSides[i] = {
        kind: "portrait", job: jobId, version: currentVersion,
        img: `/preview/${jobId}?v=${currentVersion}`,
        name: lang === "en" ? "my AI portrait" : "mon portrait IA"
      };
      renderSides();
    } catch (e) {
      alert((lang === "en" ? "Can't use that portrait: " : "Impossible d'utiliser ce portrait : ") + e.message);
      check.checked = false;
    }
    check.disabled = false;
  });
});

async function buyLamp(pack, btn) {
  if (lampSides.some(s => !s)) {
    alert(lang === "en" ? "Please choose all 4 sides first." : "Veuillez d'abord choisir les 4 faces.");
    return;
  }
  btn.disabled = true;
  try {
    const r = await fetch("/api/lamp-checkout", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pack,
        sides: lampSides.map(s => s.kind === "gallery"
          ? { kind: "gallery", id: s.id }
          : s.kind === "portrait"
            ? { kind: "portrait", job: s.job, version: s.version }
            : { kind: "upload", file: s.file })
      })
    });
    const j = await safeJson(r);
    if (!r.ok) throw new Error(j.error || "failed");
    if (j.url) window.location.href = j.url;
  } catch (e) {
    alert((lang === "en" ? "Something went wrong: " : "Une erreur est survenue : ") + e.message);
  }
  btn.disabled = false;
}
const buyLampSingle = document.getElementById("buyLampSingle");
const buyLampSet4 = document.getElementById("buyLampSet4");
if (buyLampSingle) {
  buyLampSingle.onclick = () => buyLamp("single", buyLampSingle);
  buyLampSet4.onclick = () => buyLamp("set4", buyLampSet4);
  renderSides();
}

// After lamp purchase (?lamp_paid=1)
(() => {
  const q = new URLSearchParams(location.search);
  if (q.get("lamp_paid") === "1") {
    const t = document.getElementById("lampThanks");
    if (t) {
      t.style.display = "block";
      document.getElementById("shop").scrollIntoView({ behavior: "smooth" });
    }
  }
})();

// After Stripe redirect (?paid=1&job=...&v=...)
(async () => {
  const q = new URLSearchParams(location.search);
  if (q.get("paid") === "1" && q.get("job")) {
    jobId = q.get("job");
    const v = parseInt(q.get("v") || "1", 10);
    document.getElementById("step4").style.display = "block";
    for (let i = 0; i < 20; i++) {
      const r = await fetch("/api/status/" + jobId);
      const j = await safeJson(r);
      if (j.paid) {
        paidMode = true;
        versions = j.versions || 1;
        attemptsLeft = j.attempts_left || 0;
        document.getElementById("payBtn").style.display = "none";
        document.getElementById("regenBox").style.display = "none";
        document.getElementById("sorryBox").style.display = "none";
        const dl = document.getElementById("dlBtn");
        dl.style.display = "inline-block";
        showVersion(Math.min(v, versions));
        break;
      }
      await new Promise(r => setTimeout(r, 1500));
    }
  }
})();

// Refinement needs no attire choice — hide step 2 when it's selected
document.querySelectorAll('input[name=style]').forEach(r => {
  r.addEventListener("change", () => {
    const style = document.querySelector('input[name=style]:checked').value;
    document.getElementById("step2").style.display = style === "refine" ? "none" : "block";
  });
});

applyLang();
