/* Colette — bulle injectée à chaque page (CDP). Idempotente, top frame uniquement, Shadow DOM.
 * Rendu 100 % depuis l'état serveur (StateServer) ; les boutons envoient des messages.
 * Transport : binding CDP window.__coletteSend + window.__colette.onState (Chrome bloque
 * ws://localhost depuis un site public) ; sinon WebSocket ws://localhost:8765 (maquette locale).
 *
 * Écrans (maquettes docs/design/*.png) :
 *   1 fermée · 2 ouverte (Disponible) · 3 appel en cours (écoute / parle / pause)
 *   5 navigue (H agit : pas de voile, bandeau bleu, panneau non cliquable sauf Pause/Arrêter en appui maintenu)
 *   6 accord · 7 terminé (ou arrêté / refusé) · 10 échec
 */
(function () {
  "use strict";
  if (window.top !== window) return;
  if (window.__colette) return;
  window.__colette = { version: 2 };

  var WS_URL = "ws://localhost:8765";
  var PANEL_W = 440;  // largeur de la zone latérale ; la page est rétrécie d'autant (rien n'est caché)
  var BANNER_H = 52;  // bandeau « Colette utilise cette page » : la page est poussée vers le bas d'autant
  var HOLD_MS = 800;  // appui maintenu exigé sur Pause/Arrêter pendant que l'agent H agit
  var hold = null;    // {action, t0} — hors du DOM : render() reconstruit tout à chaque état
  var state = { open: false, status: "idle", steps: [], subtitle: "", confirm: null };
  var connected = false;
  var ws = null;
  var host, root, lastKey = "";

  var BLUE = "#2155D3", INK = "#0F172A", MUTED = "#475569", LINE = "#E2E6EE";
  var GREEN = "#2E6B4A", AMBER = "#8A5A12";

  var CSS = [
    ":host{all:initial}",
    "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;margin:0}",
    "button{font:inherit;cursor:pointer}",
    ".wrap{position:fixed;inset:0;z-index:2147483647;pointer-events:none}",
    ".wrap *{pointer-events:auto}",
    ".hidden{display:none!important}",
    /* ---- 1 · pastille fermée ---- */
    ".pill{position:fixed;right:28px;bottom:28px;display:flex;align-items:center;gap:14px;background:" + BLUE + ";color:#fff;",
    "border:none;border-radius:999px;padding:10px 30px 10px 10px;box-shadow:0 10px 28px rgba(33,85,211,.35);text-align:left}",
    ".pill:hover{background:#1A47B8}",
    ".pill .av{width:58px;height:58px}",
    ".pill b{display:block;font-size:21px;font-weight:700;line-height:1.2}",
    ".pill small{display:block;font-size:15px;opacity:.95;margin-top:2px}",
    ".pill.live .av{animation:halo 1.6s ease-in-out infinite}",
    "@keyframes halo{0%,100%{box-shadow:0 0 0 0 rgba(255,255,255,.7)}50%{box-shadow:0 0 0 9px rgba(255,255,255,0)}}",
    ".av{flex:none;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center}",
    ".av svg{width:78%;height:78%}",
    /* ---- voile léger (écrans 2, 3, 6, 7, 10) et bandeau (écran 5) : sur la zone de la page ---- */
    ".veil{position:fixed;left:0;top:0;bottom:0;right:" + PANEL_W + "px;background:rgba(15,23,42,.16);pointer-events:none!important}",
    ".banner{position:fixed;left:0;top:0;right:" + PANEL_W + "px;height:" + BANNER_H + "px;background:" + BLUE + ";color:#fff;",
    "display:flex;align-items:center;gap:12px;padding:0 28px;font-size:18px;font-weight:700;pointer-events:none!important}",
    ".banner svg{width:24px;height:24px;flex:none}",
    /* « Colette est ici » : cadre sur le dernier élément cliqué par l'agent */
    ".mark{position:fixed;border:3px solid " + BLUE + ";border-radius:10px;background:rgba(33,85,211,.07);pointer-events:none!important}",
    ".mark span{position:absolute;right:-3px;top:-34px;background:" + BLUE + ";color:#fff;font-size:14px;font-weight:700;",
    "padding:6px 12px;border-radius:999px;white-space:nowrap;pointer-events:none!important}",
    /* ---- zone latérale + carte ---- */
    ".side{position:fixed;top:0;right:0;bottom:0;width:" + PANEL_W + "px;background:#E9ECF2;padding:16px}",
    ".card{height:100%;background:#fff;color:" + INK + ";border-radius:24px;box-shadow:0 18px 50px rgba(15,23,42,.18);",
    "display:flex;flex-direction:column;overflow:hidden;border:1px solid #DDE1EA}",
    ".head{display:flex;align-items:center;gap:14px;padding:18px 18px 16px 22px;border-bottom:1px solid " + LINE + "}",
    ".head .av{width:50px;height:50px;border:1px solid " + LINE + "}",
    ".who{flex:1;min-width:0}",
    ".who b{display:block;font-size:22px;font-weight:700}",
    ".st{display:flex;align-items:center;gap:7px;font-size:15px;font-weight:700;margin-top:2px}",
    ".st i{width:9px;height:9px;border-radius:50%;background:currentColor;flex:none}",
    ".st.green{color:" + GREEN + "}.st.blue{color:" + BLUE + "}.st.amber{color:" + AMBER + "}",
    ".x{background:#F1F3F7;border:none;border-radius:14px;padding:9px 14px 7px;display:flex;flex-direction:column;align-items:center;",
    "gap:2px;color:" + INK + ";font-size:13px;font-weight:700}",
    ".x svg{width:20px;height:20px}",
    ".body{flex:1;overflow:auto;padding:24px 22px}",
    ".foot{border-top:1px solid " + LINE + ";padding:18px 22px 20px;display:flex;flex-direction:column;gap:12px}",
    "h2{font-size:25px;line-height:1.3;font-weight:800;color:" + INK + "}",
    "h3{font-size:19px;font-weight:800;color:" + INK + "}",
    "p{font-size:18px;line-height:1.45;color:" + MUTED + "}",
    ".btn{width:100%;border-radius:16px;font-size:20px;font-weight:800;padding:17px 16px;border:2px solid " + BLUE + ";",
    "background:" + BLUE + ";color:#fff;display:flex;align-items:center;justify-content:center;gap:10px;position:relative;overflow:hidden}",
    ".btn:hover{background:#1A47B8}",
    ".btn.sec{background:#fff;color:" + INK + ";border-color:#D3D8E2}.btn.sec:hover{background:#F6F7FA}",
    ".btn.red{color:#B42318}",
    ".btn svg{width:24px;height:24px;flex:none}",
    ".btn.big{font-size:23px;padding:24px 16px;border-radius:20px}",
    ".btn.big svg{width:30px;height:30px}",
    ".row2{display:flex;gap:12px}.row2 .btn{flex:1;white-space:nowrap;font-size:18px;padding:17px 10px}",
    ".row2 .btn.red{flex:1.35}",
    ".rows{display:flex;flex-direction:column;gap:12px;margin-top:14px}",
    ".rowb{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#fff;",
    "border:1.5px solid #D9DEE7;border-radius:14px;padding:15px 18px;font-size:18px;font-weight:700;color:" + INK + ";text-align:left}",
    ".rowb:hover{border-color:" + BLUE + ";background:#F7F9FE}",
    ".rowb svg{width:20px;height:20px;color:" + BLUE + ";flex:none}",
    ".lead{margin-top:10px}",
    ".or{margin-top:26px;font-size:16px;font-weight:700;color:" + MUTED + "}",
    /* écran 3 */
    ".mic{width:120px;height:120px;border-radius:50%;background:#E8EEFB;margin:6px auto 0;display:flex;align-items:center;justify-content:center}",
    ".mic div{width:84px;height:84px;border-radius:50%;background:" + BLUE + ";color:#fff;display:flex;align-items:center;justify-content:center}",
    ".mic svg{width:34px;height:34px}",
    ".mic.on{animation:micpulse 1.8s ease-in-out infinite}",
    ".mic.off div{background:#94A3B8}",
    "@keyframes micpulse{0%,100%{box-shadow:0 0 0 0 rgba(33,85,211,.25)}50%{box-shadow:0 0 0 14px rgba(33,85,211,0)}}",
    ".wave{display:flex;justify-content:center;align-items:center;gap:6px;height:40px;margin:14px 0 6px}",
    ".wave i{width:6px;height:12px;border-radius:3px;background:" + BLUE + ";animation:wv 1s ease-in-out infinite}",
    ".wave.still i{animation:none;height:6px;background:#CBD5E1}",
    "@keyframes wv{0%,100%{transform:scaleY(.5)}50%{transform:scaleY(2.4)}}",
    ".center{text-align:center}",
    ".center p{margin-top:8px}",
    ".said{background:#F4F6FA;border-radius:14px;padding:14px 18px;margin-top:20px;text-align:left}",
    ".said small{display:block;font-size:15px;font-weight:700;color:" + MUTED + ";margin-bottom:6px}",
    ".said div{font-size:19px;line-height:1.45;color:" + INK + "}",
    ".said.col{background:#EEF3FD}",
    /* écran 5 */
    ".count{font-size:16px;font-weight:700;color:" + MUTED + ";margin-top:20px}",
    ".bar{height:12px;border-radius:6px;background:#EEF1F6;margin-top:10px;overflow:hidden}",
    ".bar i{display:block;height:100%;background:" + BLUE + ";border-radius:6px;transition:width .4s}",
    ".steps{list-style:none;padding:0;margin:20px 0 0;display:flex;flex-direction:column;gap:16px}",
    ".steps li{display:flex;gap:14px;align-items:flex-start}",
    ".num{width:38px;height:38px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;",
    "font-size:17px;font-weight:800;border:2px solid #D3D8E2;color:" + MUTED + ";background:#fff}",
    ".num svg{width:20px;height:20px}",
    ".done .num{background:" + GREEN + ";border-color:" + GREEN + ";color:#fff}",
    ".doing .num{background:" + BLUE + ";border-color:" + BLUE + ";color:#fff}",
    ".steps .lbl{font-size:18px;line-height:1.3;color:" + MUTED + ";padding-top:1px}",
    ".doing .lbl{color:" + INK + ";font-weight:800}",
    ".done .lbl{color:" + INK + "}",
    ".steps small{display:block;font-size:14px;font-weight:700;margin-top:3px;color:" + MUTED + "}",
    ".done small{color:" + GREEN + "}.doing small{color:" + BLUE + "}",
    ".calm{margin-top:22px}",
    ".hint{font-size:14px;color:" + MUTED + ";text-align:center;margin-top:-4px}",
    ".fill{position:absolute;left:0;top:0;bottom:0;width:0;background:rgba(33,85,211,.18);pointer-events:none!important}",
    ".btn.red .fill{background:rgba(180,35,24,.16)}",
    ".holding .fill{width:100%;transition:width " + HOLD_MS + "ms linear}",
    /* Pendant que H agit : le panneau laisse passer les clics (H ne peut ni le cliquer ni le fermer) ;
       seuls Pause/Arrêter restent actifs, en appui maintenu (H fait des clics brefs). */
    ".guard .card,.guard .card *{pointer-events:none}",
    ".guard .card .hold{pointer-events:auto}",
    /* écran 6 */
    ".need{display:flex;align-items:center;gap:10px;background:#FBF3E4;color:" + AMBER + ";border-radius:12px;",
    "padding:13px 16px;font-size:18px;font-weight:800;margin-bottom:20px}",
    ".need svg{width:22px;height:22px;flex:none}",
    ".pts{list-style:none;padding:0;margin:16px 0 0}",
    ".pts li{display:flex;gap:10px;font-size:18px;line-height:1.4;color:" + INK + ";padding:12px 0;border-bottom:1px solid " + LINE + "}",
    ".pts svg{width:18px;height:18px;flex:none;margin-top:4px;color:" + MUTED + "}",
    ".safe{font-size:16px;font-weight:700;color:" + MUTED + ";margin-top:16px}",
    /* écrans 7 et 10 */
    ".badge{width:76px;height:76px;border-radius:50%;display:flex;align-items:center;justify-content:center;margin-bottom:20px}",
    ".badge svg{width:36px;height:36px}",
    ".badge.ok{background:" + GREEN + ";color:#fff}.badge.warn{background:#FBF3E4;color:" + AMBER + "}",
    ".badge.info{background:#E8EEFB;color:" + BLUE + "}",
    ".big1{font-size:31px}",
    ".box{background:#F4F6FA;border-radius:14px;padding:16px 18px;margin-top:20px}",
    ".box ol{margin:10px 0 0;padding-left:22px}",
    ".box li{font-size:17px;line-height:1.4;color:" + INK + ";margin-top:6px}",
    ".okpill{display:flex;align-items:center;gap:10px;background:#E9F4EE;color:" + GREEN + ";border-radius:12px;padding:12px 16px;",
    "font-size:17px;font-weight:800;margin-top:18px}",
    ".okpill svg{width:20px;height:20px;flex:none}",
    ".q{font-size:18px;font-weight:800;color:" + INK + ";margin-top:22px}",
    ".off{font-size:15px;color:#B42318;margin-top:14px;text-align:center}"
  ].join("");

  // ---- icônes (SVG en ligne) ----
  var ICON = {
    avatar: '<svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="10" r="5.5" fill="' + BLUE + '"/>' +
      '<path d="M11 24c0-8 6-13.5 13-13.5S37 16 37 24c-3-4.5-7.5-6.5-13-6.5S14 19.5 11 24z" fill="' + BLUE + '"/>' +
      '<circle cx="18" cy="26" r="5" fill="none" stroke="#111827" stroke-width="2.4"/>' +
      '<circle cx="30" cy="26" r="5" fill="none" stroke="#111827" stroke-width="2.4"/>' +
      '<path d="M23 25.5h2" stroke="#111827" stroke-width="2.4"/>' +
      '<path d="M19.5 34.5q4.5 3.5 9 0" fill="none" stroke="#111827" stroke-width="2.4" stroke-linecap="round"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21"/></svg>',
    chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5L2.5 20h19L12 3.5z"/><path d="M12 10v4.5M12 17.3v.2"/></svg>',
    eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1.2"/><rect x="14" y="5" width="4" height="14" rx="1.2"/></svg>',
    play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15l12.5-7.5z"/></svg>',
    hang: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 9c-3.4 0-6.6.9-9.2 2.6-.6.4-.9 1.2-.6 1.9l1 2.3c.3.7 1.1 1 1.8.8l3.2-1.1c.6-.2 1-.8 1-1.4v-2c1.8-.5 3.8-.5 5.6 0v2c0 .6.4 1.2 1 1.4l3.2 1.1c.7.2 1.5-.1 1.8-.8l1-2.3c.3-.7 0-1.5-.6-1.9C18.6 9.9 15.4 9 12 9z"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.2"/></svg>'
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

  function svg(name, cls) {
    var s = el("span", cls || null);
    s.style.display = "contents";
    s.innerHTML = ICON[name];
    return s;
  }

  function avatar() { var a = el("div", "av"); a.innerHTML = ICON.avatar; return a; }

  function button(cls, text, icon, onclick) {
    var b = el("button", "btn " + (cls || ""));
    if (icon) b.appendChild(svg(icon));
    b.appendChild(el("span", null, text));
    if (onclick) b.onclick = onclick;
    return b;
  }

  function rowButton(text, onclick) {
    var b = el("button", "rowb");
    b.appendChild(el("span", null, text));
    b.appendChild(svg("chev"));
    b.onclick = onclick;
    return b;
  }

  // Les animations reprennent à la même phase après chaque reconstruction du DOM (pas de saccade).
  function phase(e, periodMs) { e.style.animationDelay = (-(Date.now() % periodMs)) + "ms"; return e; }

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

  // ---- quel écran ? ----
  function screen() {
    if (!state.open) return "closed";
    var o = state.outcome;
    if (state.confirm) return "confirm";
    if (o && o.kind === "failed") return "failed";
    if (o) return "done";
    if (state.busy) return "working";
    if (state.call) return "call";
    return "home";
  }

  var STATUS = {
    home: ["green", "Disponible"],
    confirm: ["amber", "Attend votre accord"],
    failed: ["amber", "Colette a besoin d'aide"],
    done: ["green", "Terminé"]
  };

  function statusFor(scr) {
    if (state.status === "paused" && (scr === "call" || scr === "working")) return ["amber", "En pause"];
    if (scr === "call") return state.status === "speaking" ? ["blue", "Colette vous parle"] : ["blue", "Je vous écoute"];
    if (scr === "working") return state.status === "listening" ? ["blue", "Je vous écoute"] : ["blue", "Je navigue pour vous"];
    if (scr === "done" && state.outcome && state.outcome.kind !== "success") return ["blue", "Démarche arrêtée"];
    return STATUS[scr] || ["blue", ""];
  }

  function render() {
    if (!root) return;
    var scr = screen();
    var key = JSON.stringify([state, connected, hold && hold.action]);
    if (key === lastKey) return;  // rien n'a changé : pas de reconstruction
    lastKey = key;
    var wrap = root.getElementById("wrap");
    wrap.className = "wrap" + (scr === "working" ? " guard" : "");
    wrap.textContent = "";
    setPush(state.open, scr === "working");
    updateMark();

    if (scr === "closed") {
      var pill = el("button", "pill" + (state.call || state.busy ? " live" : ""));
      pill.setAttribute("aria-label", "Parler à Colette");
      pill.appendChild(avatar());
      var t = el("span");
      t.appendChild(el("b", null, "Parler à Colette"));
      t.appendChild(el("small", null, state.busy ? "Je travaille pour vous" : "Votre assistante"));
      pill.appendChild(t);
      pill.onclick = function () { state.open = true; render(); send({ type: "open" }); };
      wrap.appendChild(pill);
      return;
    }

    if (scr === "working") {
      var banner = el("div", "banner");
      banner.appendChild(svg("eye"));
      banner.appendChild(el("span", null, "Colette utilise cette page pour vous. Vous pouvez regarder."));
      wrap.appendChild(banner);
    } else {
      wrap.appendChild(el("div", "veil"));
    }
    if (markBox) wrap.appendChild(markBox);

    var side = el("div", "side");
    var card = el("div", "card");
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", "Colette");
    side.appendChild(card);
    wrap.appendChild(side);

    // en-tête
    var head = el("div", "head");
    head.appendChild(avatar());
    var who = el("div", "who");
    who.appendChild(el("b", null, "Colette"));
    var st = statusFor(scr);
    var stl = el("div", "st " + st[0]);
    stl.appendChild(el("i"));
    stl.appendChild(el("span", null, st[1]));
    who.appendChild(stl);
    head.appendChild(who);
    if (scr !== "working") {  // pas de fermeture pendant que H agit (il l'a déjà fait)
      var x = el("button", "x");
      x.setAttribute("aria-label", "Fermer");
      x.appendChild(svg("x"));
      x.appendChild(el("span", null, "Fermer"));
      x.onclick = function () { state.open = false; render(); send({ type: "close" }); };
      head.appendChild(x);
    }
    card.appendChild(head);

    var body = el("div", "body");
    var foot = el("div", "foot");
    card.appendChild(body);
    ({ home: home, call: call, working: working, confirm: confirm, done: done, failed: failed })[scr](body, foot);
    if (!connected) body.appendChild(el("div", "off", "Connexion à Colette perdue… je réessaie."));
    if (foot.childNodes.length) card.appendChild(foot);
  }

  // ---- 2 · ouverte ----
  function home(body) {
    body.appendChild(el("h2", null, "Bonjour, je suis Colette."));
    body.appendChild(el("p", "lead", "Que voulez-vous faire ? Appuyez sur le bouton et parlez-moi."));
    var talk = button("big", "Appuyer pour parler", "mic", function () {
      state.call = true; render(); send({ type: "call" });
    });
    talk.style.marginTop = "22px";
    body.appendChild(talk);
    var shortcuts = state.shortcuts || [];
    if (shortcuts.length) {
      body.appendChild(el("div", "or", "Ou touchez une ligne :"));
      var rows = el("div", "rows");
      shortcuts.forEach(function (s) {
        rows.appendChild(rowButton(s.label, function () {
          state.call = true; render(); send({ type: "shortcut", id: s.id });
        }));
      });
      body.appendChild(rows);
    }
  }

  // ---- 3 · appel en cours (conversation continue) ----
  function call(body, foot) {
    var paused = state.status === "paused";
    var speaking = state.status === "speaking";
    var c = el("div", "center");
    var mic = phase(el("div", "mic" + (paused ? " off" : speaking ? "" : " on")), 1800);
    var inner = el("div"); inner.appendChild(svg(paused ? "pause" : "mic")); mic.appendChild(inner);
    c.appendChild(mic);
    var wave = el("div", "wave" + (paused ? " still" : ""));
    for (var i = 0; i < 9; i++) {
      var bar = el("i");
      bar.style.animationDelay = (-((Date.now() + i * 130) % 1000)) + "ms";
      bar.style.animationDuration = (0.8 + (i % 3) * 0.2) + "s";
      wave.appendChild(bar);
    }
    c.appendChild(wave);
    c.appendChild(el("h2", null, paused ? "En pause" : speaking ? "Colette vous répond…" : "Je vous écoute…"));
    c.appendChild(el("p", null, paused ? "Je n'écoute plus. Appuyez sur « Reprendre » quand vous voulez."
      : "Parlez normalement, prenez votre temps."));
    body.appendChild(c);
    if (speaking && state.subtitle) {
      var col = el("div", "said col");
      col.appendChild(el("small", null, "Colette dit :"));
      col.appendChild(el("div", null, state.subtitle));
      body.appendChild(col);
    }
    if (state.heard) {
      var said = el("div", "said");
      said.appendChild(el("small", null, speaking ? "Vous avez dit :" : "Vous dites :"));
      said.appendChild(el("div", null, "« " + state.heard + " »"));
      body.appendChild(said);
    }
    var row = el("div", "row2");
    row.appendChild(button("sec", paused ? "Reprendre" : "Pause", paused ? "play" : "pause", function () {
      send({ type: paused ? "resume" : "pause" });
    }));
    row.appendChild(button("sec red", "Raccrocher", "hang", function () {
      state.call = false; render(); send({ type: "hangup" });
    }));
    foot.appendChild(row);
  }

  // ---- 5 · navigue (H agit) ----
  function working(body, foot) {
    var steps = state.steps || [];
    body.appendChild(el("h2", null, state.title || "Je m'occupe de votre demande"));
    if (state.status === "listening" && state.subtitle) {  // question de l'agent H
      var q = el("div", "said col");
      q.appendChild(el("small", null, "Colette vous demande :"));
      q.appendChild(el("div", null, state.subtitle));
      body.appendChild(q);
      var said = el("div", "said");
      said.style.marginTop = "10px";
      said.appendChild(el("small", null, "Vous dites :"));
      said.appendChild(el("div", null, state.heard ? "« " + state.heard + " »" : "…"));
      body.appendChild(said);
    }
    if (steps.length) {
      var cur = 0;
      steps.forEach(function (s, i) { if (s.state === "doing") cur = i + 1; });
      var doneN = steps.filter(function (s) { return s.state === "done"; }).length;
      if (!cur) cur = Math.min(doneN + 1, steps.length);
      body.appendChild(el("div", "count", "Étape " + cur + " sur " + steps.length));
      var bar = el("div", "bar"), fill = el("i");
      fill.style.width = Math.max(6, Math.round(100 * (doneN + 0.5) / steps.length)) + "%";
      bar.appendChild(fill); body.appendChild(bar);
      var ul = el("ul", "steps");
      var start = Math.max(0, Math.min(cur - 3, steps.length - 6));
      steps.slice(start, start + 6).forEach(function (s, k) {
        var li = el("li", s.state);
        var n = el("span", "num");
        if (s.state === "done") n.appendChild(svg("check")); else n.textContent = String(start + k + 1);
        li.appendChild(n);
        var l = el("div", "lbl", s.label);
        l.appendChild(el("small", null, s.state === "done" ? "Fait" : s.state === "doing" ? "En cours" : "À venir"));
        li.appendChild(l);
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }
    var asking = state.status === "listening" && state.subtitle;
    if (asking) {
      // question de l'agent H : en haut, toujours visible (la liste des étapes passe dessous)
    } else if (state.status === "paused") {
      body.appendChild(el("p", "calm", "Je suis en pause. Vous avez la main. Dites « continuez » ou maintenez « Reprendre »."));
    } else {
      body.appendChild(el("p", "calm", "Vous n'avez rien à faire. Je vous préviens si j'ai besoin de vous."));
    }
    var paused = state.status === "paused";
    var row = el("div", "row2");
    row.appendChild(holdable(button("sec", paused ? "Reprendre" : "Pause", paused ? "play" : "pause"), "pause"));
    row.appendChild(holdable(button("sec red", "Arrêter Colette"), "stop"));
    foot.appendChild(row);
    foot.appendChild(el("div", "hint", "Maintenez le bouton appuyé"));
  }

  // ---- 6 · accord ----
  function confirm(body, foot) {
    var c = state.confirm || {};
    var need = el("div", "need");
    need.appendChild(svg("warn"));
    need.appendChild(el("span", null, "J'ai besoin de votre accord"));
    body.appendChild(need);
    body.appendChild(el("h2", null, c.title || c.text || "Je valide ?"));
    var pts = c.bullets || [];
    if (pts.length) {
      var ul = el("ul", "pts");
      pts.forEach(function (p) { var li = el("li"); li.appendChild(svg("chev")); li.appendChild(el("span", null, p)); ul.appendChild(li); });
      body.appendChild(ul);
    }
    body.appendChild(el("div", "safe", "Rien ne change sans votre accord. Vous pouvez aussi répondre « oui » ou « non » à voix haute."));
    foot.appendChild(button("", c.yes || "Oui, je suis d'accord", null, function () { send({ type: "confirm", value: true }); }));
    foot.appendChild(button("sec", c.no || "Non, ne rien changer", null, function () { send({ type: "confirm", value: false }); }));
  }

  // ---- 7 · terminé (ou arrêté / refusé) ----
  function done(body, foot) {
    var o = state.outcome || {};
    var ok = o.kind === "success";
    var b = el("div", "badge " + (ok ? "ok" : "info"));
    b.appendChild(svg(ok ? "check" : "info"));
    body.appendChild(b);
    body.appendChild(el("h2", "big1", o.title || (ok ? "C'est fait !" : "Rien n'a été changé")));
    if (o.text) { var p = el("p", null, o.text); p.style.marginTop = "12px"; body.appendChild(p); }
    if (!ok && o.nothing_changed) body.appendChild(okPill());
    var items = o.summary || [];
    if (items.length) {
      var box = el("div", "box");
      box.appendChild(el("h3", null, "Ce que j'ai fait pour vous"));
      var ol = el("ol");
      items.forEach(function (s) { ol.appendChild(el("li", null, s)); });
      box.appendChild(ol);
      body.appendChild(box);
    }
    foot.appendChild(button("sec", "Écouter ce résumé", null, function () { send({ type: "replay" }); }));
    foot.appendChild(button("", "Faire autre chose", null, function () {
      state.outcome = null; render(); send({ type: "reset" });
    }));
  }

  function okPill() {
    var g = el("div", "okpill");
    g.appendChild(svg("check"));
    g.appendChild(el("span", null, "Rien n'a été modifié sur votre compte."));
    return g;
  }

  // ---- 10 · échec ----
  function failed(body, foot) {
    var o = state.outcome || {};
    var b = el("div", "badge warn"); b.appendChild(svg("warn")); body.appendChild(b);
    body.appendChild(el("h2", null, o.title || "Je n'ai pas pu terminer"));
    var p = el("p", null, (o.text || "Le site ne répond pas comme prévu.") + " Ce n'est pas de votre faute.");
    p.style.marginTop = "10px";
    body.appendChild(p);
    if (o.nothing_changed) body.appendChild(okPill());
    body.appendChild(el("div", "q", "Que voulez-vous faire ?"));
    var rows = el("div", "rows");
    rows.appendChild(rowButton("Réessayer une fois", function () { send({ type: "retry" }); }));
    rows.appendChild(rowButton("Parler à un conseiller", function () { send({ type: "advisor" }); }));
    body.appendChild(rows);
    foot.appendChild(button("sec", "Laisser pour plus tard", null, function () {
      state.open = false; render(); send({ type: "later" });
    }));
  }

  // ---- La page se pousse à gauche (panneau) et vers le bas (bandeau) : rien n'est caché dessous ----
  var pushStyle = null, pushKey = "", fixTimer = null;
  var FX = "data-colette-fx", FXT = "data-colette-fxt";

  function setPush(open, banner) {
    var k = (open ? "o" : "") + (banner ? "b" : "");
    if (k === pushKey) return;
    var bannerWas = pushKey.indexOf("b") >= 0;
    pushKey = k;
    if (!open) {
      if (pushStyle && pushStyle.parentNode) pushStyle.parentNode.removeChild(pushStyle);
      clearInterval(fixTimer); fixTimer = null;
      restoreFixed(FX); restoreFixed(FXT);
    } else {
      if (!pushStyle) { pushStyle = document.createElement("style"); pushStyle.setAttribute("data-colette", "1"); }
      pushStyle.textContent = "html{margin-right:" + PANEL_W + "px!important;width:auto!important;" +
        "max-width:calc(100vw - " + PANEL_W + "px)!important;overflow-x:hidden!important;" +
        (banner ? "margin-top:" + BANNER_H + "px!important;" : "") + "}";
      (document.head || document.documentElement).appendChild(pushStyle);
      if (bannerWas && !banner) restoreFixed(FXT);
      fixFixed();
      if (!fixTimer) fixTimer = setInterval(fixFixed, 1500);  // bannières / en-têtes ajoutés après coup
    }
    window.dispatchEvent(new Event("resize"));  // les sites recalculent leur mise en page
  }

  // Les éléments position:fixed se placent par rapport à la fenêtre, pas à <html> : on recale ceux
  // qui débordent sous le panneau (bandeau cookies, bouton de chat…) ou sous le bandeau bleu.
  function fixFixed() {
    if (!pushKey) return;
    var banner = pushKey.indexOf("b") >= 0;
    var limit = window.innerWidth - PANEL_W;
    var all = document.body ? document.body.getElementsByTagName("*") : [];
    for (var i = 0; i < all.length && i < 5000; i++) {
      var e = all[i];
      if (e === host) continue;
      var cs = getComputedStyle(e);
      if (cs.position !== "fixed" && cs.position !== "sticky") continue;
      var r = e.getBoundingClientRect();
      if (r.width === 0) continue;
      if (!e.hasAttribute(FX) && r.right > limit + 1) {
        e.setAttribute(FX, JSON.stringify({ right: e.style.right, maxWidth: e.style.maxWidth }));
        if (r.left > limit - r.width / 2 && r.width < limit) {  // ancré à droite (ex. bouton de chat)
          e.style.setProperty("right", ((parseFloat(cs.right) || 0) + PANEL_W) + "px", "important");
        } else {  // pleine largeur (bandeau, en-tête) : on le borne à la zone de la page
          e.style.setProperty("max-width", "calc(100vw - " + PANEL_W + "px)", "important");
        }
      }
      if (banner && !e.hasAttribute(FXT) && cs.top !== "auto" && r.top < BANNER_H && r.bottom > 0 &&
          (cs.position === "fixed" || parseFloat(cs.top) < BANNER_H)) {
        e.setAttribute(FXT, JSON.stringify({ top: e.style.top }));
        e.style.setProperty("top", ((parseFloat(cs.top) || 0) + BANNER_H) + "px", "important");
      }
    }
  }

  function restoreFixed(attr) {
    var fixed = document.querySelectorAll("[" + attr + "]");
    for (var i = 0; i < fixed.length; i++) {
      var e = fixed[i], o = {};
      try { o = JSON.parse(e.getAttribute(attr)) || {}; } catch (err) { /* ignore */ }
      for (var p in o) e.style[p] = o[p] || "";
      e.removeAttribute(attr);
    }
  }

  // ---- « Colette est ici » : cadre sur l'élément que l'agent H vient de cliquer ----
  var markTarget = null, markBox = null, markTimer = null;

  function setMark(t) {
    var target = (t.closest && t.closest("a,button,label,li,tr,[role=button],[role=link],input,select,textarea")) || t;
    if (target === document.body || target === document.documentElement) return;
    markTarget = target;
    if (!markBox) {
      markBox = el("div", "mark");
      markBox.appendChild(el("span", null, "Colette est ici"));
    }
    if (!markTimer) markTimer = setInterval(updateMark, 300);
    updateMark();
    if (!markBox.isConnected && root) { var w = root.getElementById("wrap"); if (w) w.appendChild(markBox); }
  }

  function updateMark() {
    if (!markBox) return;
    if (!state.busy || !markTarget || !markTarget.isConnected) {
      clearInterval(markTimer); markTimer = null;
      if (markBox.parentNode) markBox.parentNode.removeChild(markBox);
      markBox = null; markTarget = null;
      return;
    }
    var r = markTarget.getBoundingClientRect();
    var pad = 4;
    markBox.style.left = (r.left - pad) + "px"; markBox.style.top = (r.top - pad) + "px";
    markBox.style.width = (r.width + 2 * pad) + "px"; markBox.style.height = (r.height + 2 * pad) + "px";
  }

  // Bouton à appui maintenu : un clic bref (celui de l'agent H) ne fait rien.
  function holdable(btn, action) {
    btn.classList.add("hold");
    btn.appendChild(el("span", "fill"));
    btn.setAttribute("aria-label", btn.textContent + " (maintenir appuyé)");
    if (hold && hold.action === action) btn.classList.add("holding");
    btn.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      hold = { action: action, t0: Date.now() };
      btn.classList.add("holding");
    });
    return btn;
  }
  window.addEventListener("pointerup", function () {
    if (!hold) return;
    var h = hold; hold = null;
    if (Date.now() - h.t0 >= HOLD_MS) {
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

  window.__colette.getState = function () { return { state: state, connected: connected, screen: screen() }; };
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

  // Diagnostic : où atterrissent vraiment les clics (ceux de H inclus) ? + cadre « Colette est ici ».
  window.addEventListener("mousedown", function (e) {
    var t = e.target, d = "";
    if (t === host) return;  // clic sur la bulle elle-même
    // Jamais la valeur d'un champ (mot de passe, identifiant…) : seulement balise, id et texte visible.
    if (t && t.tagName) {
      var isField = /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable;
      d = t.tagName.toLowerCase() + (t.id ? "#" + t.id : "") + (t.type ? "[" + t.type + "]" : "") +
          (isField ? "" : " " + ((t.innerText || "") + "").trim().slice(0, 40));
      if (state.busy) setMark(t);
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
