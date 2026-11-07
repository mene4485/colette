/* Colette — bulle injectée à chaque page (CDP). Idempotente, top frame uniquement, Shadow DOM.
 * Rendu 100 % depuis l'état serveur ; les boutons envoient des messages.
 * Transport : binding CDP window.__coletteSend + window.__colette.onState (Chrome bloque
 * ws://localhost depuis un site public) ; sinon WebSocket ws://localhost:8765 (maquette locale). */
(function () {
  "use strict";
  if (window.top !== window) return;
  if (window.__colette) return;
  window.__colette = { version: 1 };

  var WS_URL = "ws://localhost:8765";
  var PANEL_W = 360; // largeur du panneau latéral ; la page est rétrécie d'autant (rien n'est caché)
  var HOLD_MS = 800;  // appui maintenu exigé sur Pause/Stop pendant que l'agent H agit
  var hold = null;    // {action, t0} — hors du DOM : render() reconstruit tout à chaque état
  var state = { open: false, status: "idle", steps: [], subtitle: "", confirm: null, guide: null };
  var PAGE_ID = Math.random().toString(36).slice(2, 10); // distingue les pages pour le guide manuel
  var nextCid = 1;
  var connected = false;
  var ws = null;
  var host, root;

  var CSS = [
    ":host{all:initial}",
    "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif}",
    ".wrap{position:fixed;right:24px;bottom:24px;z-index:2147483647;display:flex;flex-direction:column;align-items:flex-end;gap:12px}",
    ".bubble{display:flex;align-items:center;gap:12px;background:#6b2fd6;color:#fff;border:none;border-radius:999px;",
    "padding:14px 22px 14px 14px;font-size:20px;font-weight:600;cursor:pointer;box-shadow:0 8px 24px rgba(60,20,120,.35)}",
    ".bubble:hover{background:#5a22bf}",
    ".dot{width:44px;height:44px;border-radius:50%;background:#fff;color:#6b2fd6;display:flex;align-items:center;justify-content:center;font-size:26px}",
    ".working .dot,.speaking .dot,.listening .dot{animation:pulse 1.4s ease-in-out infinite}",
    "@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(255,255,255,.7)}50%{box-shadow:0 0 0 10px rgba(255,255,255,0)}}",
    ".panel{width:380px;max-height:78vh;overflow:auto;background:#fff;color:#1d1530;border-radius:20px;",
    "box-shadow:0 16px 48px rgba(40,10,90,.35);border:3px solid #6b2fd6;padding:18px 20px}",
    ".head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}",
    ".title{font-size:22px;font-weight:700;color:#6b2fd6}",
    ".status{font-size:15px;color:#5b5370;margin-top:2px}",
    ".x{background:none;border:none;font-size:28px;line-height:1;cursor:pointer;color:#5b5370;padding:4px 8px}",
    ".sub{font-size:24px;line-height:1.35;font-weight:600;min-height:32px;margin:6px 0 14px}",
    ".steps{list-style:none;margin:0 0 14px;padding:0}",
    ".steps li{display:flex;gap:10px;align-items:flex-start;font-size:18px;padding:6px 0;color:#8a8399}",
    ".steps li.doing{color:#1d1530;font-weight:700}.steps li.done{color:#2e7d32}",
    ".ico{width:24px;flex:none;text-align:center}",
    ".card{background:#fff6d6;border:3px solid #e0a800;border-radius:16px;padding:14px;margin-bottom:14px}",
    ".card p{font-size:21px;font-weight:700;margin:0 0 12px}",
    ".yn{display:flex;gap:12px}",
    ".yn button{flex:1;font-size:24px;font-weight:800;padding:14px 0;border-radius:14px;border:none;cursor:pointer;color:#fff}",
    ".yes{background:#2e7d32}.no{background:#c62828}",
    ".ctrl{display:flex;gap:10px}",
    ".ctrl button{flex:1;font-size:18px;font-weight:700;padding:12px 0;border-radius:12px;cursor:pointer;border:2px solid #6b2fd6;background:#fff;color:#6b2fd6}",
    ".ctrl .stop{border-color:#c62828;color:#c62828}",
    ".off{font-size:14px;color:#c62828;margin-top:10px}",
    ".hidden{display:none!important}",
    /* Panneau compact pendant que l'agent agit : ne masque pas les champs de la page. */
    ".panel.compact{width:300px;padding:12px 14px;border-radius:16px}",
    ".compact .head{margin-bottom:4px}.compact .title{font-size:17px}.compact .status{font-size:13px}",
    ".compact .x{font-size:22px;padding:2px 6px}",
    ".compact .sub{font-size:17px;line-height:1.3;min-height:0;margin:2px 0 8px}",
    ".compact .steps{margin:0 0 8px}.compact .steps li{font-size:14px;padding:2px 0;gap:6px}",
    ".compact .ico{width:18px}",
    ".compact .ctrl button{font-size:14px;padding:7px 0;border-radius:10px}",
    /* Pendant que H agit : le panneau laisse passer les clics vers la page (H ne peut ni le
       cliquer ni le fermer) ; seuls Pause/Stop restent actifs, en appui maintenu (H fait des clics brefs). */
    ".wrap{pointer-events:none}.wrap>*{pointer-events:auto}",
    ".panel.compact{pointer-events:none;opacity:.92}",
    ".compact .ctrl button{pointer-events:auto;position:relative;overflow:hidden}",
    ".compact .ctrl button .fill{position:absolute;left:0;top:0;bottom:0;width:0;background:rgba(107,47,214,.25)}",
    ".compact .ctrl .stop .fill{background:rgba(198,40,40,.25)}",
    ".compact .ctrl button.holding .fill{width:100%;transition:width " + HOLD_MS + "ms linear}",
    ".hint{font-size:12px;color:#5b5370;text-align:center;margin-top:4px}",
    /* Ouverte : panneau latéral pleine hauteur à droite ; la page est poussée à gauche (setPush). */
    ".wrap.side{top:0;right:0;bottom:0;width:" + PANEL_W + "px;gap:0;align-items:stretch}",
    ".side .panel,.side .panel.compact{width:100%;height:100%;max-height:none;border-radius:0;border:none;",
    "border-left:4px solid #6b2fd6;box-shadow:-6px 0 24px rgba(40,10,90,.18);padding:22px 20px;display:flex;flex-direction:column}",
    ".side .sub{font-size:24px}.side .compact .sub{font-size:22px;margin:6px 0 14px}",
    ".side .compact .title{font-size:22px}.side .compact .status{font-size:15px}.side .compact .head{margin-bottom:10px}",
    ".side .steps{flex:1;overflow:auto}.side .compact .steps li{font-size:16px;padding:4px 0}",
    ".side .ctrl{margin-top:auto}.side .compact .ctrl button{font-size:17px;padding:12px 0}",
    /* Guide manuel : anneau autour de l'élément à cliquer + petite fenêtre de consigne. */
    ".glayer{position:fixed;inset:0;z-index:2147483646;pointer-events:none}",
    ".ring{position:fixed;border:4px solid #6b2fd6;border-radius:12px;pointer-events:none;",
    "box-shadow:0 0 0 9999px rgba(20,10,40,.28);animation:ring 1.2s ease-in-out infinite}",
    ".ring.warn{border-color:#e65100}",
    "@keyframes ring{0%,100%{outline:0 solid rgba(107,47,214,.5)}50%{outline:8px solid rgba(107,47,214,0)}}",
    ".tip{position:fixed;width:320px;background:#fff;color:#1d1530;border:3px solid #6b2fd6;border-radius:16px;",
    "padding:12px 14px;box-shadow:0 12px 32px rgba(40,10,90,.35);pointer-events:auto}",
    ".tip.warn{border-color:#e65100;background:#fff3e0}",
    ".tip .n{font-size:14px;font-weight:700;color:#6b2fd6;margin-bottom:4px}.tip.warn .n{color:#e65100}",
    ".tip .t{font-size:19px;line-height:1.35;font-weight:600;margin-bottom:10px}",
    ".tip button{font-size:16px;font-weight:700;padding:8px 14px;border-radius:10px;border:2px solid #6b2fd6;",
    "background:#6b2fd6;color:#fff;cursor:pointer}"
  ].join("");

  var STATUS_TEXT = {
    idle: "Prête à vous aider", listening: "Je vous écoute…", speaking: "Colette parle…",
    working: "Je m'occupe de tout…", paused: "En pause — vous avez la main",
    awaiting_confirm: "J'attends votre accord", guiding: "Je vous guide pas à pas", done: "C'est terminé"
  };

  function hasBinding() { return typeof window.__coletteSend === "function"; }

  function send(msg) {
    if (hasBinding()) window.__coletteSend(JSON.stringify(msg));
    else if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg));
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function build() {
    host = document.createElement("colette-widget");
    host.setAttribute("aria-label", "Colette (assistant) — à ignorer");
    host.setAttribute("data-colette", "1");
    root = host.attachShadow({ mode: "open" });
    var style = el("style"); style.textContent = CSS; root.appendChild(style);
    var glayer = el("div", "glayer hidden"); glayer.id = "glayer"; root.appendChild(glayer);
    var wrap = el("div", "wrap"); wrap.id = "wrap"; root.appendChild(wrap);
    mount();
    render();
  }

  function mount() {
    if (host && !host.isConnected) (document.body || document.documentElement).appendChild(host);
  }

  function render() {
    if (!root) return;
    var wrap = root.getElementById("wrap");
    wrap.className = "wrap " + state.status + (state.open ? " side" : "");
    wrap.textContent = "";
    setPush(state.open);

    if (state.open) {
      var compact = state.status === "working" && !state.confirm;
      var panel = el("div", compact ? "panel compact" : "panel");
      panel.setAttribute("role", "dialog");
      var head = el("div", "head");
      var t = el("div");
      t.appendChild(el("div", "title", "🟣 Colette"));
      t.appendChild(el("div", "status", STATUS_TEXT[state.status] || state.status));
      head.appendChild(t);
      if (!compact) {  // pas de fermeture pendant que H agit (il l'a déjà fait)
        var x = el("button", "x", "×");
        x.setAttribute("aria-label", "Réduire");
        x.onclick = function () { state.open = false; render(); send({ type: "close" }); };
        head.appendChild(x);
      }
      panel.appendChild(head);

      panel.appendChild(el("div", "sub", state.subtitle || "Bonjour, que puis-je faire pour vous ?"));

      if (state.confirm) {
        var card = el("div", "card");
        card.appendChild(el("p", null, state.confirm.text));
        var yn = el("div", "yn");
        var yes = el("button", "yes", "OUI"); yes.onclick = function () { send({ type: "confirm", value: true }); };
        var no = el("button", "no", "NON"); no.onclick = function () { send({ type: "confirm", value: false }); };
        yn.appendChild(yes); yn.appendChild(no); card.appendChild(yn);
        panel.appendChild(card);
      }

      if (state.steps && state.steps.length) {
        var ul = el("ul", "steps");
        var steps = state.steps.slice(-8);
        steps.forEach(function (s) {
          var li = el("li", s.state);
          li.appendChild(el("span", "ico", s.state === "done" ? "✅" : s.state === "doing" ? "👉" : "○"));
          li.appendChild(el("span", null, s.label));
          ul.appendChild(li);
        });
        panel.appendChild(ul);
      }

      var ctrl = el("div", "ctrl");
      var paused = state.status === "paused";
      if (state.status === "guiding") {  // guide manuel : la personne clique elle-même, seul Stop reste
        var gstop = el("button", "stop", "⏹ Arrêter le guide");
        gstop.onclick = function () { send({ type: "stop" }); };
        ctrl.appendChild(gstop);
        panel.appendChild(ctrl);
        if (!connected) panel.appendChild(el("div", "off", "Connexion à Colette perdue… je réessaie."));
        wrap.appendChild(panel);
        renderGuide();
        return;
      }
      var pause = el("button", "pause", paused ? "▶️ Reprendre" : "✋ Pause");
      var stop = el("button", "stop", "⏹ Stop");
      if (compact) {
        holdable(pause, "pause");
        holdable(stop, "stop");
      } else {
        pause.onclick = function () { send({ type: paused ? "resume" : "pause" }); };
        stop.onclick = function () { send({ type: "stop" }); };
      }
      ctrl.appendChild(pause); ctrl.appendChild(stop);
      panel.appendChild(ctrl);
      if (compact) panel.appendChild(el("div", "hint", "Maintenez le bouton appuyé"));

      if (!connected) panel.appendChild(el("div", "off", "Connexion à Colette perdue… je réessaie."));
      wrap.appendChild(panel);
    } else {
      var b = el("button", "bubble");
      b.setAttribute("aria-label", "Parler à Colette");
      b.appendChild(el("span", "dot", "🟣"));
      b.appendChild(el("span", null, state.status === "idle" ? "Besoin d'aide ? Parlez à Colette" : "Colette"));
      b.onclick = function () { state.open = true; render(); send({ type: "open" }); };
      wrap.appendChild(b);
    }
    renderGuide();
  }

  // ---- Guide manuel : lecture de la page, anneau + fenêtre de consigne, détection du clic ----
  var SCAN_SEL = "a[href],button,input:not([type=hidden]),select,textarea,summary,[onclick]," +
    "[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[role=radio],[role=option],[role=switch]";
  var BUTTON_INPUTS = /^(button|submit|reset|checkbox|radio|image|file)$/;

  function visible(e) {
    var r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    var cs = getComputedStyle(e);
    return cs.visibility !== "hidden" && cs.display !== "none" && parseFloat(cs.opacity || "1") > 0.05;
  }

  function clean(t) { return ((t || "") + "").replace(/\s+/g, " ").trim().slice(0, 90); }

  // Libellé lisible — JAMAIS la valeur tapée dans un champ (mot de passe, identifiant…).
  function labelOf(e) {
    var tag = e.tagName, t = e.getAttribute("aria-label") || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      if (tag === "INPUT" && /^(button|submit|reset)$/.test(e.type)) t = t || e.value;
      if (!t && e.id) {
        var esc = window.CSS && window.CSS.escape ? window.CSS.escape(e.id) : e.id;
        var l = document.querySelector('label[for="' + esc + '"]');
        if (l) t = l.innerText;
      }
      if (!t && e.closest("label")) t = e.closest("label").innerText;
      t = t || e.placeholder || e.name || e.title || "";
      if (tag === "SELECT" && e.selectedIndex >= 0 && e.options[e.selectedIndex]) {
        t += " (choix : " + e.options[e.selectedIndex].text + ")";
      }
      return clean(t);
    }
    t = t || e.innerText || e.title || "";
    if (!clean(t)) { var img = e.querySelector("img[alt]"); if (img) t = img.alt; }
    return clean(t);
  }

  window.__colette.scan = function () {
    var nodes = document.querySelectorAll(SCAN_SEL), out = [];
    for (var i = 0; i < nodes.length && out.length < 200; i++) {
      var e = nodes[i];
      if (!visible(e) || e.closest("[aria-hidden=true]") || e.disabled) continue;
      var text = labelOf(e);
      var field = /^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName);
      if (!text && !field) continue;
      var cid = e.getAttribute("data-colette-id");
      if (!cid) { cid = "c" + (nextCid++); e.setAttribute("data-colette-id", cid); }
      var r = e.getBoundingClientRect();
      out.push({ id: cid, tag: e.tagName.toLowerCase(), type: e.getAttribute("role") || (field ? e.type || "" : ""),
                 text: text, inView: r.bottom > 0 && r.top < window.innerHeight });
    }
    var heads = [], hs = document.querySelectorAll("h1,h2,h3");
    for (var j = 0; j < hs.length && heads.length < 10; j++) {
      if (visible(hs[j]) && clean(hs[j].innerText)) heads.push(clean(hs[j].innerText));
    }
    return { pageId: PAGE_ID, url: location.href, title: document.title, headings: heads,
             text: ((document.body && document.body.innerText) || "").replace(/\s+/g, " ").slice(0, 2500),
             elements: out };
  };

  var guideRaf = null, shownStep = null;

  function guideHere() { var g = state.guide; return g && g.page === PAGE_ID ? g : null; }

  function guideTarget() {
    var g = guideHere();
    return g && g.target ? document.querySelector('[data-colette-id="' + g.target + '"]') : null;
  }

  function isTextField(e) {
    return !!e && ((e.tagName === "INPUT" && !BUTTON_INPUTS.test(e.type)) || e.tagName === "TEXTAREA" ||
                   e.tagName === "SELECT" || e.isContentEditable);
  }

  function renderGuide() {
    if (!root) return;
    var layer = root.getElementById("glayer"), g = guideHere();
    if (!g) {
      layer.className = "glayer hidden"; layer.textContent = "";
      if (guideRaf) { cancelAnimationFrame(guideRaf); guideRaf = null; }
      shownStep = null; layer.removeAttribute("data-key");
      return;
    }
    // L'état change souvent (sous-titres mot à mot) : on ne reconstruit que si l'étape change.
    var key = g.step + "|" + g.target + "|" + g.text;
    if (layer.getAttribute("data-key") === key) { if (!guideRaf) guideRaf = requestAnimationFrame(placeGuide); return; }
    layer.setAttribute("data-key", key);
    layer.className = "glayer"; layer.textContent = "";
    var warn = g.irreversible ? " warn" : "";
    var ring = el("div", "ring" + warn); ring.id = "gring"; layer.appendChild(ring);
    var tip = el("div", "tip" + warn); tip.id = "gtip";
    tip.appendChild(el("div", "n", (g.irreversible ? "⚠️ Étape " : "Étape ") + g.step));
    tip.appendChild(el("div", "t", g.text));
    var next = el("button", null, "C'est fait ➜");
    next.onclick = function () { send({ type: "guide_next", step: g.step }); };
    tip.appendChild(next);
    layer.appendChild(tip);
    var t = guideTarget();
    if (t && shownStep !== g.step) {
      shownStep = g.step;
      try { t.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (e) { t.scrollIntoView(); }
    }
    if (!guideRaf) guideRaf = requestAnimationFrame(placeGuide);
  }

  // Suit l'élément à chaque image (défilement, animations, page qui se décale).
  function placeGuide() {
    guideRaf = null;
    if (!root || !guideHere()) return;
    var ring = root.getElementById("gring"), tip = root.getElementById("gtip");
    if (!ring || !tip) return;
    var t = guideTarget();
    var areaW = window.innerWidth - (pushed ? PANEL_W : 0), tw = 320, th = tip.offsetHeight || 140;
    if (t && t.isConnected) {
      var r = t.getBoundingClientRect(), pad = 6;
      ring.style.display = "";
      ring.style.left = (r.left - pad) + "px"; ring.style.top = (r.top - pad) + "px";
      ring.style.width = (r.width + 2 * pad) + "px"; ring.style.height = (r.height + 2 * pad) + "px";
      var top = r.bottom + 16;
      if (top + th > window.innerHeight - 8) top = Math.max(8, r.top - th - 16);
      var left = Math.min(Math.max(8, r.left), Math.max(8, areaW - tw - 12));
      tip.style.left = left + "px"; tip.style.top = top + "px";
    } else {  // pas d'élément précis : consigne seule, en haut de la page
      ring.style.display = "none";
      tip.style.left = Math.max(8, (areaW - tw) / 2) + "px"; tip.style.top = "24px";
    }
    guideRaf = requestAnimationFrame(placeGuide);
  }

  // La personne a fait l'étape : clic sur l'élément, ou case remplie (change / Entrée).
  function onGuideAction(e, kind) {
    var g = guideHere(), t = guideTarget();
    if (!g || !t || !e.target || !t.contains(e.target)) return;
    var field = isTextField(t);
    if (kind === "pointer" && field) return;  // cliquer dans une case n'est pas encore l'avoir remplie
    if (kind === "key" && (!field || e.key !== "Enter")) return;
    send({ type: "guide_clicked", step: g.step, how: kind });
  }
  document.addEventListener("pointerdown", function (e) { onGuideAction(e, "pointer"); }, true);
  document.addEventListener("change", function (e) { onGuideAction(e, "change"); }, true);
  document.addEventListener("keydown", function (e) { onGuideAction(e, "key"); }, true);

  // ---- La page se pousse à gauche pour faire place au panneau (rien n'est caché dessous) ----
  var pushStyle = null, pushed = false, fixTimer = null;
  var FX = "data-colette-fx";

  function setPush(on) {
    if (on === pushed) return;
    pushed = on;
    if (on) {
      if (!pushStyle) {
        pushStyle = document.createElement("style");
        pushStyle.setAttribute("data-colette", "1");
        pushStyle.textContent = "html{margin-right:" + PANEL_W + "px!important;width:auto!important;" +
          "max-width:calc(100vw - " + PANEL_W + "px)!important;overflow-x:hidden!important}";
      }
      (document.head || document.documentElement).appendChild(pushStyle);
      fixFixed();
      fixTimer = setInterval(fixFixed, 1500);  // bannières / en-têtes ajoutés après coup
    } else {
      if (pushStyle && pushStyle.parentNode) pushStyle.parentNode.removeChild(pushStyle);
      clearInterval(fixTimer); fixTimer = null;
      restoreFixed();
    }
    window.dispatchEvent(new Event("resize"));  // les sites recalculent leur mise en page
  }

  // Les éléments position:fixed se placent par rapport à la fenêtre, pas à <html> :
  // on recale ceux qui débordent sous le panneau (bandeau cookies, en-tête, bouton de chat…).
  function fixFixed() {
    if (!pushed) return;
    var limit = window.innerWidth - PANEL_W;
    var all = document.body ? document.body.getElementsByTagName("*") : [];
    for (var i = 0; i < all.length && i < 5000; i++) {
      var e = all[i];
      if (e === host || e.hasAttribute(FX)) continue;
      var cs = getComputedStyle(e);
      if (cs.position !== "fixed" && cs.position !== "sticky") continue;
      var r = e.getBoundingClientRect();
      if (r.width === 0 || r.right <= limit + 1) continue;
      e.setAttribute(FX, JSON.stringify({ right: e.style.right, maxWidth: e.style.maxWidth, left: e.style.left }));
      if (r.left > limit - r.width / 2 && r.width < limit) {  // ancré à droite (ex. bouton de chat)
        var right = parseFloat(cs.right) || 0;
        e.style.setProperty("right", (right + PANEL_W) + "px", "important");
      } else {  // pleine largeur (bandeau, en-tête) : on le borne à la zone de la page
        e.style.setProperty("max-width", "calc(100vw - " + PANEL_W + "px)", "important");
      }
    }
  }

  function restoreFixed() {
    var fixed = document.querySelectorAll("[" + FX + "]");
    for (var i = 0; i < fixed.length; i++) {
      var e = fixed[i], o = {};
      try { o = JSON.parse(e.getAttribute(FX)) || {}; } catch (err) { /* ignore */ }
      e.style.right = o.right || ""; e.style.maxWidth = o.maxWidth || ""; e.style.left = o.left || "";
      e.removeAttribute(FX);
    }
  }

  // Bouton à appui maintenu : un clic bref (celui de l'agent H) ne fait rien.
  function holdable(btn, action) {
    btn.appendChild(el("span", "fill"));
    btn.setAttribute("aria-label", btn.textContent + " (maintenir appuyé)");
    if (hold && hold.action === action) btn.classList.add("holding");
    btn.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      hold = { action: action, t0: Date.now() };
      btn.classList.add("holding");
    });
  }
  window.addEventListener("pointerup", function () {
    if (!hold) return;
    var h = hold; hold = null;
    var held = Date.now() - h.t0;
    if (held >= HOLD_MS) {
      if (h.action === "stop") send({ type: "stop" });
      else send({ type: state.status === "paused" ? "resume" : "pause" });
    }
    render();
  }, true);
  window.addEventListener("pointercancel", function () { hold = null; render(); }, true);

  function connect() {
    try { ws = new WebSocket(WS_URL); } catch (e) { setTimeout(connect, 1000); return; }
    ws.onopen = function () { connected = true; render(); };
    ws.onmessage = function (ev) {
      try {
        var msg = JSON.parse(ev.data);
        if (msg.type === "state" && msg.state) { state = msg.state; render(); }
      } catch (e) { /* ignore */ }
    };
    ws.onclose = function () { connected = false; ws = null; render(); setTimeout(connect, 1000); };
    ws.onerror = function () { /* onclose suit */ };
  }

  window.__colette.getState = function () { return { state: state, connected: connected }; };
  window.__colette.root = function () { return root; };
  window.__colette.onState = function (s) { connected = true; state = s; render(); };

  // Quitter la page (autre onglet, fenêtre réduite) → on ferme la bulle, donc le micro.
  // Délai : une navigation masque aussi le document, mais ses timers ne tournent plus ensuite.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "hidden") return;
    setTimeout(function () {
      if (document.visibilityState === "hidden" && state.open) {
        state.open = false; render(); send({ type: "close", reason: "page_hidden" });
      }
    }, 1500);
  });

  // Diagnostic : où atterrissent vraiment les clics (ceux de H inclus) ?
  window.addEventListener("mousedown", function (e) {
    var t = e.target, d = "";
    // Jamais la valeur d'un champ (mot de passe, identifiant…) : seulement balise, id et texte visible.
    if (t && t.tagName) {
      var isField = /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable;
      d = t.tagName.toLowerCase() + (t.id ? "#" + t.id : "") + (t.type ? "[" + t.type + "]" : "") +
          (isField ? "" : " " + ((t.innerText || "") + "").trim().slice(0, 40));
    }
    send({ type: "debug_click", x: Math.round(e.clientX), y: Math.round(e.clientY),
           w: window.innerWidth, h: window.innerHeight, trusted: e.isTrusted, target: d });
  }, true);

  function start() {
    build();
    if (hasBinding()) send({ type: "hello" });
    else connect();
    setInterval(mount, 1000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
