let lang = "fr";
let attire = "black";
let jobId = null;
let product = "digital";

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

document.getElementById("generateBtn").onclick = async () => {
  const photo = document.getElementById("photo").files[0];
  if (!photo) { setStatus(lang === "en" ? "Please upload a photo first." : "Veuillez d'abord téléverser une photo."); return; }
  const style = document.querySelector('input[name=style]:checked').value;
  product = style === "painting" ? "painted" : style === "refine" ? "refined" : "digital";
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
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "failed");
    jobId = j.job_id;
    document.getElementById("previewImg").src = j.preview_url + "?t=" + Date.now();
    document.getElementById("step4").style.display = "block";
    const payBtn = document.getElementById("payBtn");
    payBtn.textContent = product === "painted"
      ? (lang === "en" ? "Purchase — $25" : "Acheter — 25 $")
      : product === "refined"
      ? (lang === "en" ? "Purchase — $4.99" : "Acheter — 4,99 $")
      : (lang === "en" ? "Purchase — $10" : "Acheter — 10 $");
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
    body: JSON.stringify({ job_id: jobId, product })
  });
  const j = await r.json();
  if (j.url) window.location.href = j.url;
};

// After Stripe redirect (?paid=1&job=...)
(async () => {
  const q = new URLSearchParams(location.search);
  if (q.get("paid") === "1" && q.get("job")) {
    jobId = q.get("job");
    document.getElementById("step4").style.display = "block";
    for (let i = 0; i < 20; i++) {
      const r = await fetch("/api/status/" + jobId);
      const j = await r.json();
      if (j.paid) {
        document.getElementById("payBtn").style.display = "none";
        const dl = document.getElementById("dlBtn");
        dl.style.display = "inline-block";
        dl.onclick = () => window.location.href = "/download/" + jobId;
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
