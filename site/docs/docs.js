// vakforge docs: theme toggle, mobile sidebar, on-page contents highlight, search, code copy.
// Diagrams are inline SVG drawn at build time; they follow the theme through CSS variables
// and need no script at all.
(function () {
  var root = document.documentElement;
  var osLight = window.matchMedia("(prefers-color-scheme: light)");
  function isLight() {
    var t = root.getAttribute("data-theme");
    return t ? t === "light" : osLight.matches;
  }

  // ---- theme ----
  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = isLight() ? "dark" : "light";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("vakforge-theme", next); } catch (e) {}
    });
  }

  // ---- mobile sidebar ----
  var menuBtn = document.getElementById("menu-btn");
  var sidebar = document.getElementById("sidebar");
  if (menuBtn && sidebar) {
    menuBtn.addEventListener("click", function () {
      var open = sidebar.classList.toggle("open");
      menuBtn.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", function (e) {
      if (sidebar.classList.contains("open") && !sidebar.contains(e.target) && !menuBtn.contains(e.target)) {
        sidebar.classList.remove("open");
        menuBtn.setAttribute("aria-expanded", "false");
      }
    });
  }

  // ---- on-page contents: mark the heading nearest the top ----
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".toc a"));
  if (tocLinks.length) {
    var heads = tocLinks.map(function (a) { return document.getElementById(a.getAttribute("href").slice(1)); });
    function spy() {
      var line = window.scrollY + 90;
      var idx = 0;
      heads.forEach(function (h, i) { if (h && h.offsetTop <= line) idx = i; });
      tocLinks.forEach(function (a, i) { a.classList.toggle("active", i === idx); });
    }
    window.addEventListener("scroll", spy, { passive: true });
    spy();
  }

  // ---- copy buttons on code blocks ----
  document.querySelectorAll(".code-copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var code = btn.parentNode.querySelector("code");
      var text = code ? code.textContent : "";
      var done = function () { btn.textContent = "copied"; btn.classList.add("done"); setTimeout(function () { btn.textContent = "copy"; btn.classList.remove("done"); }, 1400); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done);
      else { var ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); done(); }
    });
  });

  // ---- search: a small index built at build time, matched in the browser ----
  var input = document.getElementById("search-input");
  var results = document.getElementById("search-results");
  if (input && results) {
    var index = null, selected = -1;
    function load() {
      if (index) return Promise.resolve(index);
      return fetch("search.json").then(function (r) { return r.json(); }).then(function (d) { index = d; return d; });
    }
    function href(hit) { return (hit.page === "index" ? "./" : hit.page + ".html") + "#" + hit.anchor; }
    function mark(text, terms) {
      var out = text;
      terms.forEach(function (t) { out = out.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<b>$1</b>"); });
      return out;
    }
    function snippet(text, terms) {
      var lower = text.toLowerCase(), at = -1;
      terms.forEach(function (t) { var i = lower.indexOf(t); if (i >= 0 && (at < 0 || i < at)) at = i; });
      var start = Math.max(0, at - 50);
      return (start > 0 ? "…" : "") + text.slice(start, start + 140) + (text.length > start + 140 ? "…" : "");
    }
    function render(q) {
      var terms = q.toLowerCase().split(/\s+/).filter(Boolean);
      if (!terms.length) { results.hidden = true; results.innerHTML = ""; return; }
      var hits = index.map(function (h) {
        var hay = (h.title + " " + h.heading + " " + h.text).toLowerCase();
        var score = 0;
        terms.forEach(function (t) {
          if (h.heading.toLowerCase().indexOf(t) >= 0) score += 3;
          if (h.title.toLowerCase().indexOf(t) >= 0) score += 2;
          if (hay.indexOf(t) >= 0) score += 1;
        });
        return { h: h, score: score, all: terms.every(function (t) { return hay.indexOf(t) >= 0; }) };
      }).filter(function (x) { return x.all; }).sort(function (a, b) { return b.score - a.score; }).slice(0, 10);
      selected = -1;
      if (!hits.length) { results.innerHTML = '<div class="empty">No matches</div>'; results.hidden = false; return; }
      results.innerHTML = hits.map(function (x) {
        var h = x.h;
        return '<a href="' + href(h) + '" role="option"><span>' + mark(h.heading, terms) + '</span><small><b>' + h.title + '</b> · ' + mark(snippet(h.text, terms), terms) + "</small></a>";
      }).join("");
      results.hidden = false;
    }
    input.addEventListener("input", function () { load().then(function () { render(input.value); }); });
    input.addEventListener("focus", function () { load(); });
    input.addEventListener("keydown", function (e) {
      var items = results.querySelectorAll("a");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        selected = (selected + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach(function (a, i) { a.setAttribute("aria-selected", String(i === selected)); });
        items[selected].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && items.length) {
        e.preventDefault();
        items[selected < 0 ? 0 : selected].click();
      } else if (e.key === "Escape") {
        results.hidden = true; input.blur();
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement !== input && !/input|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); input.focus(); }
    });
    document.addEventListener("click", function (e) { if (!e.target.closest("#search")) results.hidden = true; });
  }
})();
