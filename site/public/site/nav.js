(function () {
  const header = document.querySelector(".site-header");
  const inner = document.querySelector(".topbar");
  const menu = document.getElementById("site-menu");
  if (!header || !inner || !menu) return;

  let rafId = 0;

  function updateLayout() {
    header.classList.add("is-measuring");
    header.classList.add("is-wide");
    const fits = inner.scrollWidth <= inner.clientWidth;
    header.classList.toggle("is-wide", fits);
    if (rafId) cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(function () {
      header.classList.remove("is-measuring");
      rafId = 0;
    });
  }

  menu.addEventListener("click", function (event) {
    const link = event.target.closest("a");
    if (link && menu.matches(":popover-open")) {
      menu.hidePopover();
    }
  });

  if (typeof ResizeObserver === "function") {
    const observer = new ResizeObserver(updateLayout);
    observer.observe(header);
    observer.observe(inner);
  } else {
    window.addEventListener("resize", updateLayout);
  }

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(updateLayout);
  }

  updateLayout();
})();
