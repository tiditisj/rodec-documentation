/* Annotated pages: link the numbered badges on the panel to the legend.
 * Hover or focus shows the zone; a click keeps it selected. */
(function () {
  "use strict";
  document.querySelectorAll(".an-panel").forEach((panel) => {
    const badges = [...panel.querySelectorAll(".an-badge")];
    const zones = [...panel.querySelectorAll(".an-zone")];
    const items = [...panel.querySelectorAll(".an-legend li")];
    let selected = null;

    function show(n) {
      const on = (el) => el.dataset.n === n;
      for (const b of badges) b.classList.toggle("on", on(b));
      for (const z of zones) z.classList.toggle("on", on(z));
      for (const li of items) li.classList.toggle("on", on(li));
    }
    function select(n, from) {
      selected = selected === n ? null : n;
      show(selected);
      if (selected && from === "badge") {
        const li = items.find((x) => x.dataset.n === selected);
        const r = li.getBoundingClientRect();
        if (r.top < 70 || r.bottom > window.innerHeight) li.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }
    for (const b of badges) {
      b.addEventListener("click", () => select(b.dataset.n, "badge"));
      b.addEventListener("mouseenter", () => show(b.dataset.n));
      b.addEventListener("mouseleave", () => show(selected));
      b.addEventListener("focus", () => show(b.dataset.n));
      b.addEventListener("blur", () => show(selected));
    }
    for (const li of items) {
      const n = li.dataset.n;
      li.querySelector(".an-item").addEventListener("click", () => select(n, "legend"));
      li.addEventListener("mouseenter", () => show(n));
      li.addEventListener("mouseleave", () => show(selected));
    }
  });
})();
