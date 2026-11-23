(function () {
  if (window.__protoKit) return;
  window.__protoKit = true;
  var doc = document, trail = [], toastTimer = 0, lastFocus = null, state = {};
  var CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>';
  var PLACEHOLDER = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 360"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
    '<stop offset="0" stop-color="#f8f1f4"/><stop offset="1" stop-color="#eef1f6"/></linearGradient></defs>' +
    '<rect width="480" height="360" fill="url(#g)"/><g fill="none" stroke="#c9ced6" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">' +
    '<rect x="186" y="128" width="108" height="86" rx="14"/><circle cx="216" cy="156" r="10"/><path d="m196 204 30-30 22 20 14-12 22 22"/></g></svg>');

  function all(sel, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(sel)); }
  function screens() { return all(".screen[data-scr]"); }
  function current() { var s = doc.querySelector(".screen.is-active[data-scr]"); return s ? s.getAttribute("data-scr") : null; }

  function show(id, remember) {
    var target = null, from = current();
    screens().forEach(function (s) { if (s.getAttribute("data-scr") === id) target = s; });
    if (!target) return;
    if (remember && from && from !== id) trail.push(from);
    screens().forEach(function (s) { var on = s === target; s.classList.toggle("is-active", on); s.hidden = !on; });
    all(".tabbar [data-go]").forEach(function (t) {
      var on = t.getAttribute("data-go") === id;
      t.classList.toggle("is-active", on);
      if (on) t.setAttribute("aria-current", "page"); else t.removeAttribute("aria-current");
    });
    var title = doc.querySelector(".appbar-title"), name = target.getAttribute("data-title");
    if (title && name) title.textContent = name;
    syncBack();
    window.scrollTo(0, 0);
    onScroll();
  }

  function syncBack() {
    var back = doc.querySelector(".appbar-back"), flow = activeFlow();
    if (back) back.hidden = trail.length === 0 && !(flow && flowAt(flow) > 0);
  }

  function toast(message) {
    var el = doc.querySelector(".toast");
    if (!el) {
      el = doc.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      doc.body.appendChild(el);
    }
    el.innerHTML = CHECK;
    el.appendChild(doc.createTextNode(message));
    el.classList.add("is-shown");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("is-shown"); }, 2400);
  }

  function openSheet(id) {
    var sheet = doc.getElementById(id);
    if (!sheet) return;
    lastFocus = doc.activeElement;
    sheet.hidden = false;
    requestAnimationFrame(function () { sheet.classList.add("is-open"); });
    var first = sheet.querySelector(".sheet-panel button, .sheet-panel input, .sheet-panel select");
    if (first) first.focus();
  }

  function closeSheet(sheet) {
    if (!sheet) return;
    sheet.classList.remove("is-open");
    setTimeout(function () { sheet.hidden = true; }, 260);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function step(btn) {
    var box = btn.closest(".stepper"), out = box && box.querySelector("output");
    if (!out) return;
    var min = Number(box.getAttribute("data-min") || 0), max = Number(box.getAttribute("data-max") || 99);
    var next = Math.min(max, Math.max(min, Number(out.textContent || 0) + Number(btn.getAttribute("data-step"))));
    out.textContent = String(next);
    var key = box.getAttribute("data-store");
    if (key) set(key, String(next));
  }

  // --- shared state: data-store writes, data-bind / data-show-if read (memory only, no storage) ---
  function keyOf(input) { return input.getAttribute("data-store") || (input.type === "radio" ? input.name : ""); }

  function labelOf(input) {
    var wrap = input.closest("label"), title = wrap && wrap.querySelector(".choice-title, span");
    var label = input.getAttribute("data-label") || (title || wrap || {}).textContent || input.value;
    return String(label).trim();
  }

  function capture(input) {
    var key = keyOf(input);
    if (!key) return false;
    if (input.type === "radio") {
      if (!input.checked) return false;
      state[key] = labelOf(input);
    } else if (input.type === "checkbox") {
      state[key] = all("input[type=checkbox][data-store]")
        .filter(function (c) { return c.checked && c.getAttribute("data-store") === key; }).map(labelOf).join(", ");
    } else if (input.tagName === "SELECT") {
      var opt = input.options[input.selectedIndex];
      state[key] = opt ? opt.textContent.trim() : "";
    } else {
      state[key] = String(input.value || "").trim();
    }
    return true;
  }

  function matches(expr) {
    var negate = expr.charAt(0) === "!", body = negate ? expr.slice(1) : expr, at = body.indexOf("=");
    var ok = at < 0 ? !!state[body] : String(state[body.slice(0, at)] || "") === body.slice(at + 1);
    return negate ? !ok : ok;
  }

  function render() {
    all("[data-bind]").forEach(function (el) {
      var value = state[el.getAttribute("data-bind")], filled = value !== undefined && value !== "";
      if (el.matches("input, textarea")) {
        if (filled && el !== doc.activeElement) el.value = value;
        return;
      }
      if (!el.hasAttribute("data-fallback")) el.setAttribute("data-fallback", el.textContent);
      el.textContent = filled ? value : el.getAttribute("data-fallback");
    });
    all("[data-show-if]").forEach(function (el) { el.hidden = !matches(el.getAttribute("data-show-if")); });
  }

  function set(key, value) { state[key] = value; render(); }

  function applySet(spec) {
    spec.split(";").forEach(function (pair) {
      var at = pair.indexOf("=");
      if (at > 0) state[pair.slice(0, at).trim()] = pair.slice(at + 1).trim();
    });
    render();
  }

  function seed() {
    var el = doc.getElementById("proto-seed");
    if (!el) return;
    try {
      var data = JSON.parse(el.textContent || "{}");
      Object.keys(data).forEach(function (k) { if (state[k] === undefined) state[k] = String(data[k]); });
    } catch (err) {
      doc.documentElement.setAttribute("data-seed-error", "1");
    }
  }

  // --- step flow: <div data-flow><div class="flow-step" data-title>…</div>…</div> + data-next / data-prev ---
  function steps(flow) { return all(".flow-step", flow).filter(function (s) { return s.closest("[data-flow]") === flow; }); }
  function flowAt(flow) { return Number(flow.getAttribute("data-at") || 0); }
  function activeFlow() { var s = doc.querySelector(".screen.is-active"); return s ? s.querySelector("[data-flow]") : null; }

  function progress(flow) {
    var bar = flow.querySelector(".flow-progress");
    if (!bar) {
      bar = doc.createElement("div");
      bar.className = "flow-progress";
      bar.setAttribute("role", "progressbar");
      bar.innerHTML = '<p class="flow-count"></p><div class="progress"><span></span></div>';
      flow.insertBefore(bar, flow.firstChild);
    }
    return bar;
  }

  function flowShow(flow, index) {
    var list = steps(flow), at = Math.max(0, Math.min(list.length - 1, index));
    list.forEach(function (s, i) { s.hidden = i !== at; s.classList.toggle("is-active", i === at); });
    flow.setAttribute("data-at", String(at));
    var bar = progress(flow), name = list[at] ? list[at].getAttribute("data-title") || "" : "";
    bar.setAttribute("aria-valuemin", "1");
    bar.setAttribute("aria-valuemax", String(list.length));
    bar.setAttribute("aria-valuenow", String(at + 1));
    bar.setAttribute("aria-valuetext", (at + 1) + "/" + list.length + " " + name);
    bar.querySelector(".flow-count").textContent = (at + 1) + " / " + list.length + (name ? " · " + name : "");
    bar.querySelector(".progress > span").style.width = Math.round((at + 1) / list.length * 100) + "%";
    syncBack();
    window.scrollTo(0, 0);
  }

  function fieldMissing(field) {
    var req = field.querySelector("[required]");
    if (!req || req.closest("[hidden]")) return null;
    if (req.type === "radio") return field.querySelector("input[type=radio]:checked") ? null : req;
    if (req.type === "checkbox") return req.checked ? null : req;
    return String(req.value || "").trim() ? null : req;
  }

  function validStep(stepEl) {
    var first = null;
    all(".field", stepEl).forEach(function (f) {
      var missing = fieldMissing(f);
      f.classList.toggle("is-error", !!missing);
      if (missing && !first) first = missing;
    });
    if (first) first.focus();
    return !first;
  }

  function flowMove(btn, delta) {
    var flow = btn.closest("[data-flow]");
    if (!flow) return;
    var at = flowAt(flow);
    if (delta > 0 && !validStep(steps(flow)[at])) return;
    flowShow(flow, at + delta);
  }

  function images() {
    all("img[data-img]").forEach(function (img) {
      if (!img.getAttribute("src")) { img.src = PLACEHOLDER; img.classList.add("is-placeholder"); }
    });
  }

  doc.addEventListener("click", function (e) {
    var el = e.target.closest("[data-go], [data-back], [data-toast], [data-sheet], [data-close], [data-step], [data-set], [data-next], [data-prev]");
    if (!el) return;
    if (el.hasAttribute("data-next")) { flowMove(el, 1); return; }
    if (el.hasAttribute("data-prev")) flowMove(el, -1);
    if (el.hasAttribute("data-set")) applySet(el.getAttribute("data-set"));
    if (el.hasAttribute("data-close")) closeSheet(el.closest(".sheet"));
    if (el.hasAttribute("data-step")) step(el);
    if (el.hasAttribute("data-sheet")) openSheet(el.getAttribute("data-sheet"));
    if (el.hasAttribute("data-back")) {
      var flow = activeFlow();
      if (flow && flowAt(flow) > 0) flowShow(flow, flowAt(flow) - 1);
      else if (trail.length) show(trail.pop(), false);
    }
    if (el.hasAttribute("data-go")) {
      var fromTab = !!el.closest(".tabbar");
      if (fromTab) trail = [];
      show(el.getAttribute("data-go"), !fromTab);
    }
    if (el.hasAttribute("data-toast")) toast(el.getAttribute("data-toast"));
  });
  function onInput(e) {
    var t = e.target;
    if (!t.matches || !t.matches("input, select, textarea")) return;
    var field = t.closest(".field.is-error");
    if (field && !fieldMissing(field)) field.classList.remove("is-error");
    if (capture(t)) render();
  }
  doc.addEventListener("change", onInput);
  doc.addEventListener("input", onInput);
  doc.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSheet(doc.querySelector(".sheet.is-open"));
    if (e.key === "D" && e.shiftKey && !e.target.matches("input, textarea, select")) doc.documentElement.classList.toggle("pk-dev");
  });

  function onScroll() {
    var bar = doc.querySelector(".appbar");
    if (bar) bar.classList.toggle("is-scrolled", window.scrollY > 56);
  }
  window.addEventListener("scroll", onScroll, { passive: true });

  window.protoKit = { state: state, set: set, get: function (k) { return state[k]; } };

  function init() {
    seed();
    all("input[type=radio]:checked, input[type=checkbox]:checked, select[data-store], [data-store]:is(input, textarea)")
      .forEach(function (el) { if (el.checked || el.value) capture(el); });
    render();
    images();
    all("[data-flow]").forEach(function (flow) { flowShow(flow, 0); });
    var start = doc.querySelector(".screen.is-active[data-scr]") || screens()[0];
    if (start) show(start.getAttribute("data-scr"), false);
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", init); else init();
})();
