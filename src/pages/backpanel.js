/*
 * MX Modular backpanel: connector zones on the cut-out render, numbered
 * badges, and a zoom onto the connectors of the topic you pick.
 *
 * Zones are in pixels of the original render (2000 x 1315); the build crops
 * the image to the console and passes the crop offset (ox, oy) and size.
 */
(function () {
  "use strict";
  const dataEl = document.getElementById("bp-data");
  if (!dataEl) return;
  const D = JSON.parse(dataEl.textContent);
  const $ = (s, el = document) => el.querySelector(s);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // connector zones [x0, y0, x1, y1] in original render pixels
  const ZONES = {
    master_out: [78, 495, 235, 875],
    monitor_out: [248, 455, 442, 588],
    master_insert: [248, 598, 442, 808],
    aux: [488, 455, 684, 912],
    bus: [728, 455, 924, 912],
    expander_in: [1183, 462, 1418, 552],
    pfl_link: [1242, 590, 1292, 672],
    sidechain: [1306, 590, 1384, 672],
    cv_in: [1476, 462, 1600, 672],
    cv_extra: [1392, 590, 1458, 672],
    rca: [1630, 462, 1918, 706],
    control_link: [932, 712, 1110, 912],
    insert_dsub: [1130, 712, 1372, 912],
    dsub_io: [1400, 712, 1918, 912]
  };
  // where a badge sits on a zone: top left, except the small ones
  const BADGE_BELOW = new Set(["pfl_link", "sidechain", "cv_extra"]);

  const frame = $("#frame"), zoom = $("#zoom"), photo = $("#photo"), layer = $("#layer");
  const items = [...document.querySelectorAll("#features > li")];
  const W = D.w, H = D.h;
  photo.src = D.src;
  zoom.style.aspectRatio = W + " / " + H;

  const spots = {};       // zone -> element
  const featureOf = {};   // zone -> feature key
  const numberOf = {};    // feature key -> 1-based number
  let current = null;

  const px = (x) => ((x - D.ox) / W * 100) + "%";
  const py = (y) => ((y - D.oy) / H * 100) + "%";

  items.forEach((li, i) => {
    numberOf[li.dataset.f] = i + 1;
    for (const z of li.dataset.g.split(" ")) featureOf[z] = li.dataset.f;
  });

  // zones and badges
  const shown = new Set();
  for (const [z, b] of Object.entries(ZONES)) {
    const f = featureOf[z];
    if (!f) continue;
    const s = document.createElement("button");
    s.className = "bp-spot";
    s.style.left = px(b[0]); s.style.top = py(b[1]);
    s.style.width = ((b[2] - b[0]) / W * 100) + "%";
    s.style.height = ((b[3] - b[1]) / H * 100) + "%";
    s.dataset.f = f;
    const title = items.find((li) => li.dataset.f === f).querySelector(".t").textContent;
    s.setAttribute("aria-label", title);
    if (!shown.has(f)) {             // one badge per topic, on its first zone
      const n = document.createElement("span");
      n.className = "bp-badge" + (BADGE_BELOW.has(z) ? " below" : "");
      n.textContent = numberOf[f];
      s.appendChild(n);
      shown.add(f);
    }
    s.addEventListener("click", () => select(f, { scrollList: true }));
    s.addEventListener("mouseenter", () => hover(f));
    s.addEventListener("mouseleave", () => hover(null));
    layer.appendChild(s);
    spots[z] = s;
  }

  function hover(f) {
    for (const s of Object.values(spots)) s.classList.toggle("hover", !!f && s.dataset.f === f);
  }

  // ---- zoom onto the zones of a topic ----------------------------------------
  function zoomTo(f) {
    if (!f) { zoom.style.transform = ""; return; }
    const zs = Object.entries(ZONES).filter(([z]) => featureOf[z] === f).map(([, b]) => b);
    const x0 = Math.min(...zs.map((b) => b[0])) - D.ox, y0 = Math.min(...zs.map((b) => b[1])) - D.oy;
    const x1 = Math.max(...zs.map((b) => b[2])) - D.ox, y1 = Math.max(...zs.map((b) => b[3])) - D.oy;
    const fw = frame.clientWidth, fh = frame.clientHeight, k = fw / W; // image px -> frame px at scale 1
    const pad = 1.5;
    let s = Math.min(3, fw / ((x1 - x0) * k * pad), fh / ((y1 - y0) * k * pad));
    s = Math.max(1, s);
    const cx = (x0 + x1) / 2 * k, cy = (y0 + y1) / 2 * k;
    let tx = fw / 2 - cx * s, ty = fh / 2 - cy * s;
    tx = Math.min(0, Math.max(fw - fw * s, tx));
    ty = Math.min(0, Math.max(fh - H * k * s, ty));
    zoom.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
  }

  function select(f, opts = {}) {
    current = f;
    for (const s of Object.values(spots)) s.classList.toggle("on", s.dataset.f === f);
    frame.classList.toggle("focused", !!f);
    items.forEach((li) => {
      const open = li.dataset.f === f;
      li.classList.toggle("open", open);
      li.querySelector(".bp-fhead").setAttribute("aria-expanded", open);
    });
    document.querySelectorAll("#guide tbody tr").forEach((tr) => tr.classList.toggle("on", tr.dataset.f === f));
    $("#reset").hidden = !f;
    $("#hint").hidden = !!f;
    zoomTo(f);
    if (opts.scrollList && f) {
      const li = items.find((x) => x.dataset.f === f);
      li.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
    }
    if (opts.scrollStage) {
      $("#stage").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
    }
  }

  // ---- list ------------------------------------------------------------------
  items.forEach((li, i) => {
    const body = li.querySelector(".bp-fbody");
    const inner = document.createElement("div");
    while (body.firstChild) inner.appendChild(body.firstChild);
    body.appendChild(inner);
    const head = li.querySelector(".bp-fhead");
    head.setAttribute("aria-expanded", "false");
    head.insertAdjacentHTML("afterbegin", `<span class="n">${String(i + 1).padStart(2, "0")}</span>`);
    head.addEventListener("click", () => {
      const f = li.dataset.f;
      select(current === f ? null : f, { scrollStage: window.innerWidth < 992 && current !== f });
    });
    li.addEventListener("mouseenter", () => hover(li.dataset.f));
    li.addEventListener("mouseleave", () => hover(null));
  });

  document.querySelectorAll("#guide tbody tr").forEach((tr) => {
    tr.tabIndex = 0;
    const go = () => select(tr.dataset.f, { scrollStage: true });
    tr.addEventListener("click", go);
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    tr.addEventListener("mouseenter", () => hover(tr.dataset.f));
    tr.addEventListener("mouseleave", () => hover(null));
  });

  $("#reset").addEventListener("click", () => select(null));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && current) select(null); });
  window.addEventListener("resize", () => zoomTo(current));

  // deep links: /rodec-mx-modular/backpanel-connections#h.xxxx opens that topic
  const hash = decodeURIComponent(location.hash.slice(1));
  const target = hash && items.find((li) => li.id === hash || li.querySelector(`[id="${hash}"]`));
  if (target) select(target.dataset.f, { scrollList: true });
})();
