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
  var HOLD_MS = 800;  // appui maintenu exigé sur Pause/Stop pendant que l'agent H agit
  var hold = null;    // {action, t0} — hors du DOM : render() reconstruit tout à chaque état
  var state = { open: false, status: "idle", steps: [], subtitle: "", confirm: null };
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
    ".hint{font-size:12px;color:#5b5370;text-align:center;margin-top:4px}"
  ].join("");

  var STATUS_TEXT = {
    idle: "Prête à vous aider", listening: "Je vous écoute…", speaking: "Colette parle…",
    working: "Je m'occupe de tout…", paused: "En pause — vous avez la main",
    awaiting_confirm: "J'attends votre accord", done: "C'est terminé"
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
    wrap.className = "wrap " + state.status;
    wrap.textContent = "";

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
        var steps = state.steps.slice(compact ? -3 : -6);
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

  function start() {
    build();
    if (hasBinding()) send({ type: "hello" });
    else connect();
    setInterval(mount, 1000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
