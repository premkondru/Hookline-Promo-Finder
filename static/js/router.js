// Minimal hash router: "#/path?query". Each route's mount(outlet, params, query)
// renders into the outlet and returns an optional cleanup function.

export function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const qIndex = raw.indexOf("?");
  const path = (qIndex === -1 ? raw : raw.slice(0, qIndex)) || "/";
  const query = new URLSearchParams(qIndex === -1 ? "" : raw.slice(qIndex + 1));
  return { path, query };
}

export function navigate(path) {
  if (location.hash !== `#${path}`) location.hash = path;
}

export function startRouter(routes, outlet, { notFound = "/" } = {}) {
  let cleanup = null;

  function render() {
    if (typeof cleanup === "function") {
      try { cleanup(); } catch (err) { console.error(err); }
    }
    cleanup = null;
    outlet.replaceChildren();
    const { path, query } = parseHash();
    for (const route of routes) {
      const match = path.match(route.pattern);
      if (match) {
        cleanup = route.mount(outlet, match.slice(1), query) || null;
        window.scrollTo(0, 0);
        return;
      }
    }
    navigate(notFound);
  }

  window.addEventListener("hashchange", render);
  render();
}
