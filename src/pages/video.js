/* Click-to-play YouTube: the player (and its cookies) load only after a click. */
document.querySelectorAll(".yt[data-yt]").forEach((b) => {
  b.addEventListener("click", () => {
    const f = document.createElement("iframe");
    f.src = "https://www.youtube-nocookie.com/embed/" + b.dataset.yt + "?autoplay=1&rel=0";
    f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
    f.allowFullscreen = true;
    f.title = b.dataset.title;
    const box = document.createElement("div");
    box.className = "yt";
    box.appendChild(f);
    b.replaceWith(box);
    f.focus();
  }, { once: true });
});
