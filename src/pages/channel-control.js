/*
 * MX-F-101 / 102 interactive front panel, built from layered 3D renders.
 *
 * The panel data (canvas size, layer crops, LED / button / knob / fader
 * coordinates in render pixels) is put in the page by tools/build.py from
 * src/img/channel-control/mx-f-10x.json. Everything is placed in percent of
 * the render canvas, so it scales with the stage.
 */
(function () {
  "use strict";

  const dataEl = document.getElementById("panels");
  const stage = document.getElementById("stage");
  if (!dataEl || !stage) return;
  const PANELS = JSON.parse(dataEl.textContent);
  const canvas = document.getElementById("canvas");
  const layer = document.getElementById("layer");
  const photo = document.getElementById("photo");
  const $ = (s, el = document) => el.querySelector(s);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const FEATURES = [
    ["on", "left"], ["solo", "left"], ["pan", "left"], ["aux", "left"],
    ["fader", "left"], ["lit", "right"], ["xf", "right"], ["vu", "right"]
  ];
  const DB = { "+24": 24, "+15": 15, "+6": 6, "0": 0, "-6": -6, "-15": -15, "-21": -21 };
  const BTN = { "MOM": "mom", "PFL": "pfl", "BUS 1": "bus1", "BUS 2": "bus2", "MASTER": "master" };
  const DESTS = [["master", "Master"], ["bus1", "Bus 1"], ["bus2", "Bus 2"], ["aux1", "AUX 1"], ["aux2", "AUX 2"], ["pfl", "PFL"]];
  const KNOB_RANGE = 150; // degrees each side of 12 o'clock

  const state = {
    model: "101", on: true, solo: false, mom: false, pfl: false,
    bus1: false, bus2: false, master: true, xf: "thru", signal: false,
    held: { on: false, solo: false },  // momentary mode: active while held
    press: { on: false, solo: false }, // finger / mouse on the key right now
    focus: null,
    fader: 7.5,                       // printed scale, 0..10
    knob: { pan: 0, aux1: -60, aux2: -150 } // degrees, 0 = 12 o'clock
  };
  let P, W, H, els;

  // ---- geometry helpers (render px -> % of the canvas) -----------------------
  const px = (x) => (x / W * 100) + "%";
  const py = (y) => (y / H * 100) + "%";
  function rect(el, x0, y0, x1, y1) {
    el.style.left = px(x0); el.style.top = py(y0);
    el.style.width = px(x1 - x0); el.style.height = py(y1 - y0);
  }
  function mk(cls, tag = "div", parent = layer) {
    const e = document.createElement(tag); e.className = cls; parent.appendChild(e); return e;
  }
  function layerImg(name, parent = layer, cls = "") {
    const L = P.layers_web[name];
    const img = mk("cc-img " + cls, "img", parent);
    img.src = L.src; img.alt = ""; img.draggable = false;
    rect(img, ...L.box);
    return img;
  }
  // a round window on a layer: shows only the part of `name` inside the circle
  function windowOn(name, cx, cy, r, cls) {
    const L = P.layers_web[name];
    const w = mk("cc-win " + cls);
    rect(w, cx - r, cy - r, cx + r, cy + r);
    const img = mk("cc-img", "img", w);
    img.src = L.src; img.alt = ""; img.draggable = false;
    const b = L.box, d = 2 * r;
    img.style.left = ((b[0] - (cx - r)) / d * 100) + "%";
    img.style.top = ((b[1] - (cy - r)) / d * 100) + "%";
    img.style.width = ((b[2] - b[0]) / d * 100) + "%";
    img.style.height = ((b[3] - b[1]) / d * 100) + "%";
    return w;
  }

  // ---- build ---------------------------------------------------------------------
  function featureBoxes() {
    const k = P.knobs, f = P.fader, b = P.buttons, sw = P.xfader_switch.patch;
    const leds = P.leds, lx = leds.map((l) => l.cx), ly = leds.map((l) => l.cy);
    const lr = leds[0].r;
    const ON = P.keycaps.ON.patch, SOLO = P.keycaps.SOLO.patch;
    const capBox = P.layers_web["fader-cap"].box;
    return {
      on: [ON[0] - 6, ON[1] - 6, ON[2] + 6, ON[3] + 6],
      solo: [SOLO[0] - 6, SOLO[1] - 6, SOLO[2] + 6, SOLO[3] + 6],
      pan: [k.pan.pivot[0] - 125, k.pan.pivot[1] - 125, k.pan.pivot[0] + 115, k.pan.pivot[1] + 95],
      aux: [k.aux1.pivot[0] - 125, k.aux1.pivot[1] - 120, k.aux1.pivot[0] + 115, k.aux2.pivot[1] + 100],
      fader: [capBox[0] - 4, f.slot_px[0] - 20, f.cap_centre_top[0] + (f.cap_centre_top[0] - capBox[0]) * 0.75, f.slot_px[1] + 20],
      lit: [b[0].cx - b[0].r - 18, b[0].cy - b[0].r - 45, b[0].cx + b[0].r + 18, b[b.length - 1].cy + b[0].r + 14],
      xf: [sw[0] - 90, sw[1] - 8, sw[2] + 12, sw[3] + 8],
      vu: [Math.min(...lx) - lr - 14, Math.min(...ly) - lr - 14, Math.max(...lx) + lr + (P.stereo ? 14 : 70), Math.max(...ly) + lr + 14]
    };
  }

  function build() {
    P = PANELS[state.model];
    P.stereo = P.leds.some((l) => l.column === "L");
    W = P.image.width; H = P.image.height;
    photo.src = P.layers_web.base.src;
    photo.alt = P.module + " front panel";
    canvas.style.aspectRatio = W + " / " + H;
    layer.innerHTML = "";
    els = { lit: {}, leds: [], boxes: {}, badges: {}, knobs: {}, sw: {} };

    // X-fader switch patches (THRU is the base render)
    for (const pos of ["x", "y"]) els.sw[pos] = layerImg("switch-" + pos, layer, "cc-sw");
    // keycaps pressed
    // keycap states: pressed, lit, pressed + lit (opaque patches over base)
    els.key = {};
    for (const k of ["on", "solo"]) {
      els.key[k] = {};
      for (const v of ["down", "lit", "down-lit"]) {
        if (P.layers_web[`${k}-${v}`]) els.key[k][v] = layerImg(`${k}-${v}`, layer, "cc-down");
      }
    }
    stage.classList.toggle("has-key-light", !!(P.layers_web["on-lit"] && P.layers_web["solo-lit"]));
    // meter LEDs: a round window on the "all lit" layer per LED
    for (const l of P.leds) {
      const w = windowOn("leds-on", l.cx, l.cy, l.r * 2.3, "cc-led");
      els.leds.push({ el: w, ch: l.column === "R" ? 1 : 0, db: DB[l.value] });
    }
    // lit buttons: a round window on the "all lit" layer per button
    for (const b of P.buttons) {
      const k = BTN[b.name];
      els.lit[k] = { glow: windowOn("buttons-lit", b.cx, b.cy, b.r * 1.9, "cc-glow") };
    }
    // knobs
    for (const k of ["pan", "aux1", "aux2"]) {
      const img = layerImg("knob-" + k, layer, "cc-knob");
      const L = P.layers_web["knob-" + k].box, pv = P.knobs[k].pivot;
      img.style.transformOrigin = ((pv[0] - L[0]) / (L[2] - L[0]) * 100) + "% " + ((pv[1] - L[1]) / (L[3] - L[1]) * 100) + "%";
      els.knobs[k] = img;
    }
    // fader cap
    els.cap = layerImg("fader-cap", layer, "cc-cap");
    els.capBox = P.layers_web["fader-cap"].box.slice();

    // focus outlines
    const FB = featureBoxes();
    const fw = mk("cc-focuswrap");
    for (const [f] of FEATURES) {
      const b = mk("cc-focus", "div", fw); rect(b, ...FB[f]); els.boxes[f] = b;
    }

    // ---- hit areas (on top) ----
    for (const [k, key] of [["on", "ON"], ["solo", "SOLO"]]) {
      const h = mk("cc-hit cc-key", "button"); rect(h, ...P.keycaps[key].patch);
      h.setAttribute("aria-label", key); h.dataset.k = k; els[k] = h;
    }
    for (const b of P.buttons) {
      const k = BTN[b.name];
      const h = mk("cc-hit cc-round", "button");
      rect(h, b.cx - b.r * 1.15, b.cy - b.r * 1.15, b.cx + b.r * 1.15, b.cy + b.r * 1.15);
      h.setAttribute("aria-label", b.name); h.dataset.k = k;
      els.lit[k].hit = h;
    }
    const sw = P.xfader_switch.patch;
    els.xf = mk("cc-hit cc-xf", "button"); rect(els.xf, sw[0] - 70, sw[1], sw[2] + 6, sw[3]);
    els.xf.setAttribute("aria-label", "X-fader switch");
    for (const k of ["pan", "aux1", "aux2"]) {
      const pv = P.knobs[k].pivot, r = 62;
      const h = mk("cc-hit cc-round cc-knobhit", "div"); rect(h, pv[0] - r, pv[1] - r, pv[0] + r, pv[1] + r);
      h.tabIndex = 0; h.setAttribute("role", "slider"); h.dataset.k = k;
      h.setAttribute("aria-label", P.knobs[k].label);
      els.knobs[k + "Hit"] = h;
    }
    const cb = els.capBox;
    els.capHit = mk("cc-hit cc-caphit", "div");
    els.capHit.tabIndex = 0; els.capHit.setAttribute("role", "slider");
    els.capHit.setAttribute("aria-label", "Fader"); els.capHit.setAttribute("aria-orientation", "vertical");
    els.slotHit = mk("cc-hit cc-slothit", "div");
    rect(els.slotHit, cb[0], P.fader.slot_px[0], cb[2], P.fader.slot_px[1]);

    // numbered badges, in the gutter beside the panel
    FEATURES.forEach(([f, side], i) => {
      const b = FB[f];
      const e = mk("cc-badge " + side, "button");
      e.textContent = i + 1; e.dataset.f = f;
      e.setAttribute("aria-label", "Feature " + (i + 1));
      e.style.top = py((b[1] + b[3]) / 2);
      els.badges[f] = e;
    });

    wire();
    render();
  }

  // ---- interaction ---------------------------------------------------------------
  function engaged(k) { return state.mom ? state.held[k] : state[k]; }

  function capY(v) { // cap layer offset (px) for fader value v
    const f = P.fader;
    return (f.cap_centre_bottom[1] - f.cap_centre_top[1]) * (10 - v) / 10;
  }
  function valueFromY(clientY) {
    const r = canvas.getBoundingClientRect();
    const y = (clientY - r.top) / r.height * H;
    const f = P.fader;
    const v = 10 - (y - f.cap_centre_top[1]) / (f.cap_centre_bottom[1] - f.cap_centre_top[1]) * 10;
    return Math.max(0, Math.min(10, Math.round(v * 10) / 10));
  }

  function dragKnob(el, k) {
    let startY = 0, startA = 0, active = false;
    el.addEventListener("pointerdown", (e) => {
      active = true; startY = e.clientY; startA = state.knob[k];
      el.setPointerCapture(e.pointerId); e.preventDefault();
      openFeature(k === "pan" ? "pan" : "aux", false);
    });
    el.addEventListener("pointermove", (e) => {
      if (!active) return;
      state.knob[k] = Math.max(-KNOB_RANGE, Math.min(KNOB_RANGE, startA + (startY - e.clientY) * 1.6));
      render();
    });
    const end = () => { active = false; };
    el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
    el.addEventListener("wheel", (e) => {
      e.preventDefault();
      state.knob[k] = Math.max(-KNOB_RANGE, Math.min(KNOB_RANGE, state.knob[k] - Math.sign(e.deltaY) * 10));
      render();
    }, { passive: false });
    el.addEventListener("keydown", (e) => {
      const d = { ArrowUp: 10, ArrowRight: 10, ArrowDown: -10, ArrowLeft: -10 }[e.key];
      if (d) { e.preventDefault(); state.knob[k] = Math.max(-KNOB_RANGE, Math.min(KNOB_RANGE, state.knob[k] + d)); render(); }
    });
  }

  function wire() {
    for (const k of ["on", "solo"]) {
      const b = els[k];
      b.addEventListener("pointerdown", (e) => {
        state.press[k] = true; b.setPointerCapture(e.pointerId);
        if (state.mom) state.held[k] = true;
        render();
      });
      const up = () => {
        if (!state.press[k] && !state.held[k]) return;
        state.press[k] = false;
        if (state.mom) state.held[k] = false;
        render();
      };
      b.addEventListener("pointerup", up); b.addEventListener("pointercancel", up);
      b.addEventListener("click", () => { if (!state.mom) state[k] = !state[k]; openFeature(k, false); render(); });
      b.addEventListener("keydown", (e) => {
        if (e.key === " " || e.key === "Enter") { state.press[k] = true; if (state.mom) { e.preventDefault(); state.held[k] = true; } render(); }
      });
      b.addEventListener("keyup", (e) => {
        if (e.key === " " || e.key === "Enter") { state.press[k] = false; if (state.mom) state.held[k] = false; render(); }
      });
    }
    for (const [k, o] of Object.entries(els.lit)) {
      o.hit.addEventListener("click", () => {
        state[k] = !state[k];
        if (k === "mom") state.held.on = state.held.solo = false;
        openFeature("lit", false); render();
      });
    }
    els.xf.addEventListener("click", () => {
      state.xf = { x: "thru", thru: "y", y: "x" }[state.xf];
      openFeature("xf", false); render();
    });
    for (const k of ["pan", "aux1", "aux2"]) dragKnob(els.knobs[k + "Hit"], k);

    // fader: drag the cap, or press anywhere on the slot
    let dragging = false;
    const start = (e) => {
      dragging = true; e.currentTarget.setPointerCapture(e.pointerId); e.preventDefault();
      state.fader = valueFromY(e.clientY); openFeature("fader", false); render();
    };
    const move = (e) => { if (dragging) { state.fader = valueFromY(e.clientY); render(); } };
    const end = () => { dragging = false; };
    for (const h of [els.capHit, els.slotHit]) {
      h.addEventListener("pointerdown", start); h.addEventListener("pointermove", move);
      h.addEventListener("pointerup", end); h.addEventListener("pointercancel", end);
    }
    els.capHit.addEventListener("keydown", (e) => {
      const d = { ArrowUp: 0.5, ArrowRight: 0.5, ArrowDown: -0.5, ArrowLeft: -0.5, PageUp: 2, PageDown: -2 }[e.key];
      if (d) { e.preventDefault(); state.fader = Math.max(0, Math.min(10, state.fader + d)); render(); }
    });

    for (const [f, e] of Object.entries(els.badges)) {
      e.addEventListener("click", () => openFeature(f, true));
      e.addEventListener("mouseenter", () => highlight(f));
      e.addEventListener("mouseleave", () => highlight(state.focus));
    }
  }

  // ---- logic -----------------------------------------------------------------------
  const knobPct = (k) => (state.knob[k] + KNOB_RANGE) / (2 * KNOB_RANGE); // 0..1
  function routes() {
    const live = state.signal, on = engaged("on"), lvl = state.fader / 10;
    return {
      master: live && on && state.master ? lvl : 0,
      bus1: live && on && state.bus1 ? lvl : 0,
      bus2: live && on && state.bus2 ? lvl : 0,
      aux1: live && on ? lvl * knobPct("aux1") : 0,   // post-fader
      aux2: live && on ? lvl * knobPct("aux2") : 0,
      pfl: live && state.pfl ? 1 : 0                   // pre-fader
    };
  }

  function panText() {
    const a = state.knob.pan;
    if (Math.abs(a) < 8) return "C";
    return (a < 0 ? "L " : "R ") + Math.round(Math.abs(a) / KNOB_RANGE * 100);
  }

  function render() {
    for (const k of ["on", "solo"]) {
      const lit = engaged(k), down = state.press[k], L = els.key[k];
      // without lit layers (older renders) "engaged" falls back to the pressed look
      const want = L.lit ? (down ? (lit ? "down-lit" : "down") : (lit ? "lit" : null))
                         : ((down || lit) ? "down" : null);
      for (const [v, img] of Object.entries(L)) img.classList.toggle("show", v === want);
    }
    els.on.classList.toggle("engaged", engaged("on"));
    els.solo.classList.toggle("engaged", engaged("solo"));
    els.on.setAttribute("aria-pressed", engaged("on"));
    els.solo.setAttribute("aria-pressed", engaged("solo"));
    for (const [k, o] of Object.entries(els.lit)) {
      o.glow.classList.toggle("show", !!state[k]);
      o.hit.setAttribute("aria-pressed", !!state[k]);
    }
    els.sw.x.classList.toggle("show", state.xf === "x");
    els.sw.y.classList.toggle("show", state.xf === "y");

    for (const k of ["pan", "aux1", "aux2"]) {
      els.knobs[k].style.transform = `rotate(${state.knob[k]}deg)`;
      const h = els.knobs[k + "Hit"];
      h.setAttribute("aria-valuemin", -KNOB_RANGE); h.setAttribute("aria-valuemax", KNOB_RANGE);
      h.setAttribute("aria-valuenow", Math.round(state.knob[k]));
      h.setAttribute("aria-valuetext", k === "pan" ? panText() : Math.round(knobPct(k) * 100) + "%");
    }
    const dy = capY(state.fader), cb = els.capBox;
    rect(els.cap, cb[0], cb[1] + dy, cb[2], cb[3] + dy);
    rect(els.capHit, cb[0], cb[1] + dy, cb[2], cb[3] + dy);
    els.capHit.setAttribute("aria-valuemin", 0); els.capHit.setAttribute("aria-valuemax", 10);
    els.capHit.setAttribute("aria-valuenow", state.fader);

    const r = routes();
    // "set": the channel is routed there (button lit, send turned up);
    // "on": audio is actually flowing there right now
    const set = {
      master: state.master, bus1: state.bus1, bus2: state.bus2, pfl: state.pfl,
      aux1: knobPct("aux1") > 0.02, aux2: knobPct("aux2") > 0.02
    };
    $("#route").innerHTML = DESTS.map(([k, label]) =>
      `<span class="cc-chip${set[k] ? " set" : ""}${r[k] > 0.005 ? " on" : ""}" style="--amt:${r[k].toFixed(2)}"><span class="led"></span>${label}</span>`).join("");
    $("#readout").innerHTML =
      `<span><b>${P.stereo ? "BAL" : "PAN"}</b> ${panText()}</span>` +
      `<span><b>AUX 1</b> ${Math.round(knobPct("aux1") * 100)}%</span>` +
      `<span><b>AUX 2</b> ${Math.round(knobPct("aux2") * 100)}%</span>` +
      `<span><b>Fader</b> ${state.fader.toFixed(1)}${state.fader >= 10 ? " (0 dB)" : ""}</span>`;

    const notes = [];
    if (!state.signal) notes.push("Press <b>Signal in</b> to send audio into the channel.");
    else if (!engaged("on")) notes.push(state.mom ? "Momentary mode: hold <b>ON</b> to open the channel." : "The channel is <b>off</b>: muted, but the VU meter still shows the incoming level and PFL still listens.");
    else if (state.fader === 0) notes.push("Fader at <b>0</b>: nothing reaches master, busses or the post-fader AUX sends.");
    if (engaged("solo")) notes.push("<b>SOLO</b>: all other channels are muted.");
    if (state.mom) notes.push("<b>MOM</b> is lit: ON and SOLO only act while held.");
    notes.push({
      x: "X-fader switch on <b>X</b>: audible with the crossfader at X or in the middle.",
      y: "X-fader switch on <b>Y</b>: audible with the crossfader at Y or in the middle.",
      thru: "X-fader switch on <b>THRU</b>: the crossfader has no effect on this channel."
    }[state.xf]);
    $("#routeNote").innerHTML = notes.join(" ");

    const sig = $("#signal");
    sig.setAttribute("aria-pressed", state.signal);
    sig.classList.toggle("on", state.signal);
    $(".cc-features [data-f='pan'] .t").textContent = P.stereo ? "Balance control" : "Pan control";
    if (!state.signal) for (const l of els.leds) l.el.style.opacity = 0;
  }

  // ---- meter (pre-fader: shows the incoming level, on or off) ----------------------
  let level = [-60, -60], t0 = performance.now(), raf = 0;
  function tick(now) {
    const t = (now - t0) / 1000;
    for (let ch = 0; ch < 2; ch++) {
      const beat = Math.pow(Math.max(0, Math.sin(t * Math.PI * 2 * 2.05 + ch * 0.4)), 8);
      const body = Math.sin(t * 1.7 + ch) * 3 + Math.sin(t * 0.31) * 4;
      const target = -12 + body + beat * 18 + (Math.random() - 0.5) * 4;
      level[ch] = target > level[ch] ? target : level[ch] - 0.9;
    }
    for (const l of els.leds) {
      const v = level[l.ch] - l.db;
      l.el.style.opacity = v >= 0 ? 1 : Math.max(0, 1 + v / 2.5) * 0.9;
    }
    raf = requestAnimationFrame(tick);
  }
  function startMeter() {
    cancelAnimationFrame(raf);
    if (!state.signal) return;
    if (reduceMotion) { for (const l of els.leds) l.el.style.opacity = l.db <= 0 ? 1 : 0; return; }
    t0 = performance.now(); raf = requestAnimationFrame(tick);
  }

  // ---- feature list --------------------------------------------------------------------
  function highlight(f) {
    for (const [k, b] of Object.entries(els.boxes)) b.classList.toggle("on", k === f);
    for (const [k, b] of Object.entries(els.badges)) b.classList.toggle("on", k === f);
  }
  function openFeature(f, scroll) {
    state.focus = f;
    document.querySelectorAll("#features > li").forEach((li) => {
      const open = li.dataset.f === f;
      li.classList.toggle("open", open);
      li.querySelector(".cc-fhead").setAttribute("aria-expanded", open);
    });
    highlight(f);
    if (scroll && window.innerWidth < 992) {
      const li = document.querySelector(`#features > li[data-f='${f}']`);
      li && li.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
    }
  }
  document.querySelectorAll("#features > li").forEach((li, i) => {
    const body = li.querySelector(".cc-fbody");
    const inner = document.createElement("div");
    while (body.firstChild) inner.appendChild(body.firstChild);
    body.appendChild(inner);
    const head = li.querySelector(".cc-fhead");
    head.setAttribute("aria-expanded", "false");
    head.insertAdjacentHTML("afterbegin", `<span class="n">${String(i + 1).padStart(2, "0")}</span>`);
    head.addEventListener("click", () => {
      const f = li.dataset.f;
      if (state.focus === f) { state.focus = null; li.classList.remove("open"); head.setAttribute("aria-expanded", "false"); highlight(null); }
      else openFeature(f, false);
    });
    li.addEventListener("mouseenter", () => highlight(li.dataset.f));
    li.addEventListener("mouseleave", () => highlight(state.focus));
  });

  $("#signal").addEventListener("click", () => { state.signal = !state.signal; render(); startMeter(); });
  document.querySelectorAll(".cc-model [data-model]").forEach((b) => {
    b.addEventListener("click", () => {
      if (state.model === b.dataset.model) return;
      state.model = b.dataset.model;
      document.querySelectorAll(".cc-model [data-model]").forEach((x) => x.setAttribute("aria-selected", x === b));
      build(); startMeter(); if (state.focus) highlight(state.focus);
    });
  });

  build();
})();
