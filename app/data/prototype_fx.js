(function () {
  // Visual effects for the prototype kit. One animation loop drives every effect, and only effects on the
  // visible screen draw. Without window.THREE or WebGL the 3D stage keeps its CSS gradient.
  var doc = document;
  var reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var effects = [];

  function all(sel, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(sel)); }
  function shown(el) { return el.getClientRects().length > 0; }
  function accent() {
    var v = getComputedStyle(doc.documentElement).getPropertyValue("--accent").trim();
    return /^#[0-9a-f]{6}$/i.test(v) ? v : "#3157e0";
  }
  function rgb(hex) { var n = parseInt(hex.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
  function rgba(c, a) { return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + a + ")"; }
  function mix(c, d, t) { return [0, 1, 2].map(function (i) { return Math.round(c[i] + (d[i] - c[i]) * t); }); }
  function ratio() { return Math.min(2, window.devicePixelRatio || 1); }
  function canvasIn(el) {
    var c = el.querySelector(":scope > canvas.fx-canvas");
    if (!c) {
      c = doc.createElement("canvas");
      c.className = "fx-canvas";
      c.setAttribute("aria-hidden", "true");
      el.insertBefore(c, el.firstChild);
    }
    return c;
  }
  // Size a 2D canvas to its box; returns true when the size changed.
  function fit2d(c, ctx, box) {
    var d = ratio(), w = Math.max(1, Math.round(box.width * d)), h = Math.max(1, Math.round(box.height * d));
    if (c.width === w && c.height === h) return false;
    c.width = w; c.height = h; ctx.setTransform(d, 0, 0, d, 0, 0);
    return true;
  }

  // --- 2D: drifting points joined by thin lines ------------------------------------------------------
  function particles(el) {
    var c = canvasIn(el), ctx = c.getContext("2d"), pts = [], w = 0, h = 0, col = rgb(accent());
    function seed() {
      pts = [];
      var n = Math.round(Math.min(80, Math.max(24, w * h / 5200)));
      for (var i = 0; i < n; i++) {
        pts.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .35,
                   vy: (Math.random() - .5) * .35, r: 1 + Math.random() * 2.2 });
      }
    }
    return {
      el: el,
      frame: function () {
        var box = el.getBoundingClientRect();
        if (fit2d(c, ctx, box) || !pts.length) { w = box.width; h = box.height; seed(); }
        ctx.clearRect(0, 0, w, h);
        pts.forEach(function (p) {
          if (!reduce) { p.x += p.vx; p.y += p.vy; }
          if (p.x < 0 || p.x > w) p.vx *= -1;
          if (p.y < 0 || p.y > h) p.vy *= -1;
        });
        for (var i = 0; i < pts.length; i++) {
          for (var j = i + 1; j < pts.length; j++) {
            var dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y, dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 120) {
              ctx.strokeStyle = rgba(col, (1 - dist / 120) * .28);
              ctx.lineWidth = 1;
              ctx.beginPath(); ctx.moveTo(pts[i].x, pts[i].y); ctx.lineTo(pts[j].x, pts[j].y); ctx.stroke();
            }
          }
        }
        pts.forEach(function (p) {
          ctx.fillStyle = rgba(col, .65);
          ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
        });
      }
    };
  }

  // --- 3D (three.js): orb · rings · wave · cards ----------------------------------------------------
  function scene3d(el) {
    var T = window.THREE;
    if (!T) return null;
    var c = canvasIn(el), renderer;
    try {
      renderer = new T.WebGLRenderer({ canvas: c, alpha: true, antialias: true });
    } catch (e) {
      return null;
    }
    renderer.setPixelRatio(ratio());
    var kind = el.getAttribute("data-fx3d") || "orb";
    var base = new T.Color(accent());
    var scene = new T.Scene(), cam = new T.PerspectiveCamera(38, 1, .1, 100);
    cam.position.set(0, 0, 7);
    scene.add(new T.AmbientLight(0xffffff, .8));
    var key = new T.DirectionalLight(0xffffff, 2.2); key.position.set(3, 5, 6); scene.add(key);
    var glow = new T.PointLight(base.clone().offsetHSL(.08, 0, .1), 40, 30); glow.position.set(-4, -2, 4); scene.add(glow);
    var group = new T.Group(); scene.add(group);
    var tint = function (h, l) { return base.clone().offsetHSL(h, 0, l); };
    var parts = [], wave = null, waveBase = null;

    if (kind === "rings") {
      for (var i = 0; i < 3; i++) {
        var ring = new T.Mesh(new T.TorusGeometry(1.25 + i * .5, .07, 24, 160),
          new T.MeshStandardMaterial({ color: tint(i * .05, i * .08), metalness: .65, roughness: .22 }));
        ring.rotation.set(1.1 + i * .35, i * .5, 0);
        group.add(ring); parts.push(ring);
      }
      group.add(new T.Mesh(new T.SphereGeometry(.55, 48, 48),
        new T.MeshPhysicalMaterial({ color: tint(.02, .15), roughness: .1, clearcoat: 1 })));
    } else if (kind === "wave") {
      var geo = new T.PlaneGeometry(11, 6, 90, 45);
      wave = new T.Points(geo, new T.PointsMaterial({ color: base, size: .045, transparent: true, opacity: .85 }));
      waveBase = geo.attributes.position.array.slice();
      wave.rotation.x = -1.05;
      group.add(wave);
    } else if (kind === "cards") {
      for (var k = 0; k < 4; k++) {
        var card = new T.Mesh(new T.BoxGeometry(1.6, 1, .06),
          new T.MeshPhysicalMaterial({ color: k % 2 ? 0xffffff : tint(k * .04, .12), roughness: .25, clearcoat: 1,
                                       transparent: true, opacity: k % 2 ? .85 : 1 }));
        card.position.set((k - 1.5) * .7, (k % 2 ? .45 : -.35), -k * .5);
        card.rotation.set(-.2, .5, .08 * k);
        group.add(card); parts.push(card);
      }
    } else {
      var orb = new T.Mesh(new T.IcosahedronGeometry(1.35, 6),
        new T.MeshPhysicalMaterial({ color: base, roughness: .18, metalness: .1, clearcoat: 1, clearcoatRoughness: .08 }));
      var shell = new T.Mesh(new T.IcosahedronGeometry(1.9, 1),
        new T.MeshBasicMaterial({ color: tint(.04, .1), wireframe: true, transparent: true, opacity: .28 }));
      group.add(orb); group.add(shell); parts.push(shell);
      for (var m = 0; m < 5; m++) {
        var moon = new T.Mesh(new T.SphereGeometry(.09 + m * .025, 24, 24),
          new T.MeshStandardMaterial({ color: tint(m * .04, .2), metalness: .3, roughness: .3 }));
        moon.userData = { r: 2.3 + m * .22, speed: .35 + m * .08, tilt: m * .6 };
        group.add(moon); parts.push(moon);
      }
    }

    var aim = { x: 0, y: 0 }, size = { w: 0, h: 0 };
    el.addEventListener("pointermove", function (e) {
      var b = el.getBoundingClientRect();
      aim.x = ((e.clientX - b.left) / b.width - .5) * .6;
      aim.y = ((e.clientY - b.top) / b.height - .5) * .4;
    });
    return {
      el: el,
      frame: function (t) {
        var b = el.getBoundingClientRect();
        if (b.width !== size.w || b.height !== size.h) {
          size = { w: b.width, h: b.height };
          renderer.setSize(b.width, b.height, false);
          cam.aspect = b.width / Math.max(1, b.height);
          cam.updateProjectionMatrix();
          // Wide stage: the scene sits on the right and the text keeps the left; narrow: top centre.
          // Half the visible width at the scene's depth; the text keeps the left ~58% (prototype_fx.css).
          var wide = cam.aspect > 1.4 && b.width >= 600, half = Math.tan(cam.fov * Math.PI / 360) * cam.position.z * cam.aspect;
          group.position.set(wide ? half * .62 : 0, wide ? .1 : .9, 0);
          group.scale.setScalar(wide ? Math.min(1, half * .2) : .78);
        }
        var s = reduce ? 0 : t / 1000;
        group.rotation.y += ((aim.x + s * .15) - group.rotation.y) * .05;
        group.rotation.x += (aim.y - group.rotation.x) * .05;
        if (kind === "orb") {
          group.children[0].position.y = Math.sin(s * 1.2) * .08;
          parts.forEach(function (p) {
            if (!p.userData.r) { p.rotation.y = s * .2; p.rotation.x = s * .12; return; }
            var a = s * p.userData.speed + p.userData.tilt;
            p.position.set(Math.cos(a) * p.userData.r, Math.sin(a * 1.3) * .6, Math.sin(a) * p.userData.r * .5);
          });
        } else if (kind === "rings") {
          parts.forEach(function (p, i) { p.rotation.z = s * (.25 + i * .12); });
        } else if (kind === "cards") {
          parts.forEach(function (p, i) { p.position.y += Math.sin(s * 1.4 + i) * .002; p.rotation.y = .5 + Math.sin(s * .6 + i) * .12; });
        } else if (wave) {
          var pos = wave.geometry.attributes.position;
          for (var v = 0; v < pos.count; v++) {
            var x = waveBase[v * 3], y = waveBase[v * 3 + 1];
            pos.array[v * 3 + 2] = Math.sin(x * .9 + s * 1.4) * .32 + Math.cos(y * 1.3 + s) * .22;
          }
          pos.needsUpdate = true;
        }
        renderer.render(scene, cam);
      }
    };
  }

  // --- charts: data-chart="line|bar|donut" data-values="…" (data-labels="…") ---------------------
  function chart(el) {
    var c = doc.createElement("canvas"), ctx = c.getContext("2d"), col = rgb(accent());
    c.setAttribute("role", "img");
    c.setAttribute("aria-label", el.getAttribute("aria-label") || "그래프");
    el.appendChild(c);
    var kind = el.getAttribute("data-chart") || "line";
    var values = (el.getAttribute("data-values") || "").split(",").map(Number).filter(function (n) { return !isNaN(n); });
    var labels = (el.getAttribute("data-labels") || "").split(",").map(function (s) { return s.trim(); });
    var start = null, wasShown = false;
    return {
      el: el,
      frame: function (t) {
        if (!values.length) return;
        if (!wasShown) { start = t; wasShown = true; }
        var p = reduce ? 1 : Math.min(1, (t - start) / 900), e = 1 - Math.pow(1 - p, 3);
        var box = el.getBoundingClientRect(); fit2d(c, ctx, box);
        var w = box.width, h = box.height, max = Math.max.apply(null, values) || 1, padB = labels[0] ? 22 : 6;
        ctx.clearRect(0, 0, w, h);
        ctx.font = "12px " + getComputedStyle(doc.body).fontFamily;
        ctx.fillStyle = "#8b95a1"; ctx.textAlign = "center";
        if (kind === "donut") {
          var total = values.reduce(function (a, b) { return a + b; }, 0) || 1, r = Math.min(w, h) / 2 - 8, at = -Math.PI / 2;
          values.forEach(function (v, i) {
            var span = v / total * Math.PI * 2 * e;
            ctx.strokeStyle = rgba(mix(col, [255, 255, 255], i / (values.length + 1)), 1);
            ctx.lineWidth = r * .32; ctx.beginPath(); ctx.arc(w / 2, h / 2, r * .82, at, at + span); ctx.stroke();
            at += v / total * Math.PI * 2 * e;
          });
          ctx.fillStyle = "#191f28"; ctx.font = "700 20px " + getComputedStyle(doc.body).fontFamily;
          ctx.fillText(String(Math.round(total * e)), w / 2, h / 2 + 7);
          return;
        }
        var n = values.length, step = w / n, chartH = h - padB - 8;
        if (kind === "bar") {
          values.forEach(function (v, i) {
            var bh = v / max * chartH * e, x = i * step + step * .22, bw = step * .56, y = 8 + chartH - bh;
            var g = ctx.createLinearGradient(0, y, 0, y + bh);
            g.addColorStop(0, rgba(col, 1)); g.addColorStop(1, rgba(col, .45));
            ctx.fillStyle = g; ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(x, y, bw, bh, 6); else ctx.rect(x, y, bw, bh);
            ctx.fill();
            if (labels[i]) { ctx.fillStyle = "#8b95a1"; ctx.fillText(labels[i], x + bw / 2, h - 6); }
          });
          return;
        }
        var pts = values.map(function (v, i) { return [i * step + step / 2, 8 + chartH - v / max * chartH * e]; });
        var area = ctx.createLinearGradient(0, 8, 0, 8 + chartH);
        area.addColorStop(0, rgba(col, .28)); area.addColorStop(1, rgba(col, 0));
        ctx.beginPath(); ctx.moveTo(pts[0][0], 8 + chartH);
        pts.forEach(function (q) { ctx.lineTo(q[0], q[1]); });
        ctx.lineTo(pts[n - 1][0], 8 + chartH); ctx.closePath(); ctx.fillStyle = area; ctx.fill();
        ctx.beginPath(); pts.forEach(function (q, i) { if (i) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); });
        ctx.strokeStyle = rgba(col, 1); ctx.lineWidth = 2.5; ctx.lineJoin = "round"; ctx.stroke();
        pts.forEach(function (q, i) {
          ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(q[0], q[1], 3.5, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = rgba(col, 1); ctx.lineWidth = 2; ctx.stroke();
          if (labels[i]) { ctx.fillStyle = "#8b95a1"; ctx.fillText(labels[i], q[0], h - 6); }
        });
      },
      hidden: function () { wasShown = false; }
    };
  }

  // --- numbers that count up each time their screen opens: <span data-count>1,240</span> --------------
  function counter(el) {
    var text = el.textContent, m = text.match(/-?[\d,]+(\.\d+)?/);
    if (!m) return null;
    var target = parseFloat(m[0].replace(/,/g, "")), decimals = (m[1] || "").length - (m[1] ? 1 : 0);
    var start = null;
    function show(v) {
      var s = v.toLocaleString("ko-KR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      el.textContent = text.slice(0, m.index) + s + text.slice(m.index + m[0].length);
    }
    return {
      el: el,
      frame: function (t) {
        if (start === null) start = t;
        var p = reduce ? 1 : Math.min(1, (t - start) / 1000);
        show(target * (1 - Math.pow(1 - p, 3)));
      },
      hidden: function () { start = null; }
    };
  }

  // --- confetti on [data-confetti] ------------------------------------------------------------------
  function confetti(x, y) {
    if (reduce) return;
    var c = doc.createElement("canvas"), ctx = c.getContext("2d"), col = rgb(accent()), bits = [], t0 = null;
    c.className = "fx-confetti"; c.setAttribute("aria-hidden", "true"); doc.body.appendChild(c);
    fit2d(c, ctx, { width: window.innerWidth, height: window.innerHeight });
    var palette = [col, mix(col, [255, 255, 255], .5), [255, 196, 61], [72, 207, 173], [255, 122, 89]];
    for (var i = 0; i < 140; i++) {
      var a = Math.random() * Math.PI * 2, v = 4 + Math.random() * 7;
      bits.push({ x: x, y: y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 6, s: 5 + Math.random() * 6,
                  r: Math.random() * 6, vr: (Math.random() - .5) * .4, c: palette[i % palette.length] });
    }
    function tick(t) {
      if (t0 === null) t0 = t;
      var age = (t - t0) / 1600;
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
      bits.forEach(function (b) {
        b.vy += .28; b.vx *= .985; b.x += b.vx; b.y += b.vy; b.r += b.vr;
        ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.r); ctx.fillStyle = rgba(b.c, Math.max(0, 1 - age));
        ctx.fillRect(-b.s / 2, -b.s / 4, b.s, b.s / 2); ctx.restore();
      });
      if (age < 1) requestAnimationFrame(tick); else c.remove();
    }
    requestAnimationFrame(tick);
  }

  function init() {
    all("[data-fx3d]").forEach(function (el) {
      var fx = scene3d(el);
      if (fx) effects.push(fx);
      else if (!el.hasAttribute("data-fx")) el.setAttribute("data-fx", "particles");
    });
    all('[data-fx="particles"]').forEach(function (el) {
      if (!el.querySelector(":scope > canvas.fx-canvas")) effects.push(particles(el));
    });
    all("[data-chart]").forEach(function (el) { effects.push(chart(el)); });
    all("[data-count]").forEach(function (el) { var fx = counter(el); if (fx) effects.push(fx); });
    all(".stagger").forEach(function (box) {
      Array.prototype.forEach.call(box.children, function (child, i) { child.style.setProperty("--i", String(i)); });
    });
    if ("IntersectionObserver" in window) {
      var seen = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) en.target.classList.add("is-in"); });
      }, { threshold: .15 });
      all(".reveal").forEach(function (el) { seen.observe(el); });
    } else {
      all(".reveal").forEach(function (el) { el.classList.add("is-in"); });
    }
    doc.addEventListener("pointermove", function (e) {
      var card = e.target.closest && e.target.closest(".tilt");
      if (!card || reduce) return;
      var b = card.getBoundingClientRect();
      card.style.setProperty("--ry", ((e.clientX - b.left) / b.width - .5) * 8 + "deg");
      card.style.setProperty("--rx", (.5 - (e.clientY - b.top) / b.height) * 8 + "deg");
    });
    doc.addEventListener("pointerout", function (e) {
      var card = e.target.closest && e.target.closest(".tilt");
      if (card && !card.contains(e.relatedTarget)) { card.style.removeProperty("--rx"); card.style.removeProperty("--ry"); }
    });
    doc.addEventListener("click", function (e) {
      var btn = e.target.closest && e.target.closest("[data-confetti]");
      if (btn) { var b = btn.getBoundingClientRect(); confetti(b.left + b.width / 2, b.top + b.height / 2); }
    });
    var was = [];
    function loop(t) {
      effects.forEach(function (fx, i) {
        var on = shown(fx.el);
        if (on) fx.frame(t);
        else if (was[i] && fx.hidden) fx.hidden();
        was[i] = on;
      });
      requestAnimationFrame(loop);
    }
    if (effects.length) requestAnimationFrame(loop);
  }

  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", init); else init();
})();
