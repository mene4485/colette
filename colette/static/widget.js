/* Colette — panneau injecté à chaque page (CDP). Idempotent, top frame uniquement, Shadow DOM.
 * Rendu 100 % depuis l'état serveur (StateServer) ; les boutons envoient des messages.
 * Transport : binding CDP window.__coletteSend + window.__colette.onState (Chrome bloque
 * ws://localhost depuis un site public) ; sinon WebSocket ws://localhost:8765 (maquette locale).
 *
 * Écrans (maquettes v2) : panneau latéral droit pleine hauteur, la page est rétrécie (jamais grisée).
 *   02 ouverte (gros micro rond + raccourcis) · 03/04 conversation en continu (bulles Colette / Vous)
 *   05 navigue (cadre dégradé autour de la page, « Je clique ici », panneau non cliquable sauf
 *   Pause / Arrêter) · 06 votre accord · 07 c'est fait · 10 échec
 */
(function () {
  "use strict";
  if (window.top !== window) return;
  if (window.__colette) return;
  window.__colette = { version: 3 };

  var WS_URL = "ws://localhost:8765";
  // Mode en ligne (maquette sur Vercel) : la page définit window.COLETTE_BACKEND (https://… du backend).
  // Un seul WebSocket porte l'état, les boutons, le micro (PCM16 16 kHz) et la voix (PCM16 24 kHz).
  var BACKEND = (window.COLETTE_BACKEND || "").replace(/\/+$/, "");
  var HOSTED = !!BACKEND;
  if (HOSTED) WS_URL = BACKEND.replace(/^http/, "ws") + "/ws";
  var IN_RATE = 16000, OUT_RATE = 24000;
  var audioCtx = null, micStream = null, micNode = null, playAt = 0, playing = [];
  var shot = null, liveEl = null, busyServer = false;
  var PANEL_W = 440;  // largeur du panneau ; la page est rétrécie d'autant (rien n'est caché)
  var state = { open: false, status: "idle", steps: [], subtitle: "", confirm: null };
  var connected = false;
  var ws = null;
  var host, root, lastKey = "";

  var BLUE = "#2155D3", INK = "#0F172A", MUTED = "#475569", LINE = "#E2E6EE";
  var GREEN = "#2E6B4A", AMBER = "#8A5A12", SOFT = "#F3F5F9";

  var CSS = [
    ":host{all:initial}",
    "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;margin:0}",
    "button{font:inherit;cursor:pointer}",
    ".wrap{position:fixed;inset:0;z-index:2147483647;pointer-events:none}",
    ".wrap *{pointer-events:auto}",
    /* ---- pastille fermée ---- */
    ".pill{position:fixed;right:28px;bottom:28px;display:flex;align-items:center;gap:14px;background:" + BLUE + ";color:#fff;",
    "border:none;border-radius:999px;padding:10px 30px 10px 10px;box-shadow:0 10px 28px rgba(33,85,211,.35);text-align:left}",
    ".pill:hover{background:#1A47B8}",
    ".pill .av{width:58px;height:58px;border:none}",
    ".pill b{display:block;font-size:21px;font-weight:700;line-height:1.2}",
    ".pill small{display:block;font-size:15px;opacity:.95;margin-top:2px}",
    ".pill.live .av{animation:halo 1.6s ease-in-out infinite}",
    "@keyframes halo{0%,100%{box-shadow:0 0 0 0 rgba(255,255,255,.7)}50%{box-shadow:0 0 0 9px rgba(255,255,255,0)}}",
    ".av{flex:none;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center;border:1px solid " + LINE + "}",
    ".av svg{width:80%;height:80%}",
    /* ---- écran 05 : cadre dégradé autour de la page + « Je clique ici » ---- */
    ".frame{position:fixed;left:0;top:0;bottom:0;right:" + PANEL_W + "px;border:5px solid transparent;",
    "border-image:linear-gradient(90deg,#4F6BFF,#B66CE0 50%,#4F6BFF) 1;pointer-events:none!important}",
    ".mark{position:fixed;border:3px solid " + BLUE + ";border-radius:12px;pointer-events:none!important}",
    ".mark span{position:absolute;left:18px;bottom:calc(100% + 6px);background:" + BLUE + ";color:#fff;font-size:15px;font-weight:700;",
    "padding:6px 14px;border-radius:8px;white-space:nowrap;pointer-events:none!important}",
    /* ---- mode en ligne : écran de l'agent H (captures du navigateur cloud) à gauche du panneau ---- */
    ".live{position:fixed;left:0;top:0;bottom:0;right:" + PANEL_W + "px;background:#0F172A;display:none;flex-direction:column;",
    "padding:14px 18px 12px;gap:10px;pointer-events:auto}",
    ".livebar{display:flex;align-items:center;gap:10px;color:#fff;font-size:18px;font-weight:800}",
    ".livebar i{width:11px;height:11px;border-radius:50%;background:#EF4444;animation:halo 1.6s ease-in-out infinite}",
    ".livebox{position:relative;flex:1;min-height:0;display:flex;align-items:center;justify-content:center;",
    "border-radius:12px;overflow:hidden;border:4px solid transparent;border-image:linear-gradient(90deg,#4F6BFF,#B66CE0 50%,#4F6BFF) 1}",
    ".livebox img{max-width:100%;max-height:100%;object-fit:contain;background:#fff;display:block}",
    ".livecur{position:absolute;width:36px;height:36px;border:3px solid #fff;border-radius:50%;background:rgba(33,85,211,.55);",
    "box-shadow:0 0 0 4px rgba(33,85,211,.5);display:none;transition:left .4s,top .4s}",
    ".livecur span{position:absolute;left:-4px;bottom:calc(100% + 8px);background:" + BLUE + ";color:#fff;font-size:15px;font-weight:700;",
    "padding:6px 12px;border-radius:8px;white-space:nowrap}",
    ".typebox{display:flex;gap:8px}.typebox input{flex:1;min-width:0;font:inherit;font-size:17px;padding:12px 14px;border:1.5px solid #D3D8E2;border-radius:12px}",
    ".typebox button{font-size:16px;font-weight:800;padding:0 16px;border-radius:12px;border:2px solid " + BLUE + ";background:#fff;color:" + BLUE + "}",
    ".liveurl{color:#CBD5E1;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
    /* ---- panneau latéral ---- */
    ".side{position:fixed;top:0;right:0;bottom:0;width:" + PANEL_W + "px;background:#fff;color:" + INK + ";",
    "border-left:1px solid " + LINE + ";display:flex;flex-direction:column;overflow:hidden}",
    ".top{display:flex;align-items:center;justify-content:space-between;height:42px;padding:0 14px 0 16px;background:#F6F7FA;",
    "border-bottom:1px solid " + LINE + ";font-size:15px;font-weight:700;flex:none}",
    ".top button{background:none;border:none;color:" + MUTED + ";padding:4px;display:flex}.top svg{width:18px;height:18px}",
    ".head{display:flex;align-items:center;gap:16px;padding:18px 20px;border-bottom:1px solid " + LINE + ";flex:none}",
    ".head .av{width:62px;height:62px}",
    ".who{flex:1;min-width:0}",
    ".who b{display:block;font-size:25px;font-weight:800}",
    ".st{display:flex;align-items:center;gap:8px;font-size:17px;font-weight:700;margin-top:2px}",
    ".st i{width:11px;height:11px;border-radius:50%;background:currentColor;flex:none}",
    ".st.green{color:" + GREEN + "}.st.blue{color:" + BLUE + "}.st.amber{color:" + AMBER + "}",
    ".x{background:#fff;border:1.5px solid #D3D8E2;border-radius:14px;padding:9px 13px 7px;display:flex;flex-direction:column;",
    "align-items:center;gap:3px;color:" + INK + ";font-size:14px;font-weight:700}",
    ".x svg{width:22px;height:22px}",
    ".callbar{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:11px 20px;font-size:15px;font-weight:700;",
    "background:#E9F4EE;color:" + GREEN + ";flex:none}",
    ".callbar span{display:flex;align-items:center;gap:7px}.callbar i{width:9px;height:9px;border-radius:50%;background:currentColor}",
    ".callbar svg{width:15px;height:15px}",
    ".callbar.paused{background:#FBF3E4;color:" + AMBER + "}.callbar.ended{background:" + SOFT + ";color:" + MUTED + "}",
    ".body{flex:1;overflow-y:auto;padding:24px 22px;display:flex;flex-direction:column}",
    ".body>*{flex-shrink:0}",
    ".foot{border-top:1px solid " + LINE + ";padding:18px 22px 22px;display:flex;flex-direction:column;gap:12px;flex:none}",
    "h2{font-size:27px;line-height:1.25;font-weight:800;color:" + INK + "}",
    "h3{font-size:19px;font-weight:800;color:" + INK + "}",
    "p{font-size:18px;line-height:1.45;color:" + MUTED + "}",
    ".btn{width:100%;border-radius:16px;font-size:20px;font-weight:800;padding:18px 12px;border:2px solid " + BLUE + ";",
    "background:" + BLUE + ";color:#fff;display:flex;align-items:center;justify-content:center;gap:10px;white-space:nowrap}",
    ".btn:hover{background:#1A47B8}",
    ".btn.sec{background:#fff;color:" + INK + ";border-color:#D3D8E2}.btn.sec:hover{background:#F6F7FA}",
    ".btn.dark{background:#fff;color:" + INK + ";border-color:" + INK + "}.btn.dark:hover{background:#F6F7FA}",
    ".row2{display:flex;gap:12px}.row2 .btn{flex:1}",
    ".rows{display:flex;flex-direction:column;gap:12px;margin-top:14px}",
    ".rowb{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#fff;",
    "border:1.5px solid #D9DEE7;border-radius:14px;padding:18px 20px;font-size:19px;font-weight:800;color:" + INK + ";text-align:left}",
    ".rowb:hover{border-color:" + BLUE + ";background:#F7F9FE}",
    ".rowb svg{width:22px;height:22px;color:" + BLUE + ";flex:none}",
    /* 02 · ouverte */
    ".lead{margin-top:12px}",
    ".talk{display:flex;flex-direction:column;align-items:center;margin-top:26px;background:none;border:none;width:100%}",
    ".talk .halo{width:184px;height:184px;border-radius:50%;background:#EAF0FC;display:flex;align-items:center;justify-content:center}",
    ".talk .disc{width:146px;height:146px;border-radius:50%;background:" + BLUE + ";color:#fff;display:flex;align-items:center;justify-content:center}",
    ".talk:hover .disc{background:#1A47B8}",
    ".talk svg{width:50px;height:50px}",
    ".talk b{font-size:26px;font-weight:800;color:" + INK + ";margin-top:18px}",
    ".lock{display:flex;align-items:center;justify-content:center;gap:8px;font-size:16px;color:" + MUTED + ";margin-top:14px}",
    ".lock svg{width:17px;height:17px;color:" + GREEN + "}",
    ".sep{border-top:1px solid " + LINE + ";margin:22px 0 18px}",
    ".or{font-size:17px;color:" + MUTED + "}",
    ".grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}",
    ".chip{background:#fff;border:1.5px solid #D9DEE7;border-radius:14px;padding:15px 8px;font-size:18px;font-weight:800;color:" + INK + "}",
    ".chip:hover{border-color:" + BLUE + ";background:#F7F9FE}",
    /* 03/04 · conversation en continu */
    /* la bulle la plus récente reste toujours visible en bas ; les anciennes s'effacent par le haut */
    ".chat{display:flex;flex-direction:column;justify-content:flex-end;gap:6px;overflow:hidden;flex:1 1 auto!important;min-height:0;",
    "-webkit-mask-image:linear-gradient(to bottom,transparent 0,#000 40px)}",
    ".who2{font-size:14px;font-weight:700;color:" + MUTED + ";margin-top:12px}",
    ".who2.me{text-align:right}",
    ".msg{max-width:86%;border-radius:16px;padding:14px 18px;font-size:17px;line-height:1.45;color:" + INK + ";background:" + SOFT + ";align-self:flex-start}",
    ".msg.me{background:#EEF3FD;align-self:flex-end}",
    ".msg.now{font-size:23px;font-weight:800;line-height:1.35;max-width:100%}",
    ".caret{display:inline-block;width:2px;height:1.1em;background:" + BLUE + ";margin-left:6px;vertical-align:-3px;animation:blink 1s steps(1) infinite}",
    "@keyframes blink{50%{opacity:0}}",
    ".hintbox{display:flex;gap:12px;align-items:flex-start;border:2px solid " + BLUE + ";border-radius:14px;padding:16px 18px;",
    "font-size:18px;font-weight:800;color:" + INK + ";margin-top:16px}",
    ".hintbox svg{width:22px;height:22px;color:" + BLUE + ";flex:none;margin-top:2px}",
    ".listen{padding-top:16px;text-align:center;color:" + GREEN + ";font-size:18px;font-weight:800}",
    ".listen.blue{color:" + BLUE + "}.listen.grey{color:" + MUTED + "}",
    ".wave{display:flex;justify-content:center;align-items:center;gap:6px;height:52px;margin-bottom:10px}",
    ".wave i{width:6px;height:14px;border-radius:3px;background:currentColor;animation:wv 1s ease-in-out infinite}",
    ".wave.still i{animation:none;height:6px;opacity:.5}",
    "@keyframes wv{0%,100%{transform:scaleY(.5)}50%{transform:scaleY(2.6)}}",
    /* 05 · navigue */
    ".count{font-size:17px;font-weight:800;color:" + BLUE + ";margin-top:20px}",
    ".segs{display:flex;gap:6px;margin-top:12px}.segs i{flex:1;height:9px;border-radius:5px;background:#E5E8EF}.segs i.on{background:" + BLUE + "}",
    ".steps{list-style:none;padding:0;margin:20px 0 0;display:flex;flex-direction:column;gap:18px}",
    ".steps li{display:flex;align-items:center;gap:14px}",
    ".dot{width:34px;height:34px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;border:2px solid #D3D8E2;background:#fff}",
    ".dot svg{width:18px;height:18px}",
    ".done .dot{background:" + GREEN + ";border-color:" + GREEN + ";color:#fff}",
    ".doing .dot{background:" + BLUE + ";border-color:" + BLUE + "}.doing .dot:after{content:'';width:10px;height:10px;border-radius:50%;background:#fff}",
    ".steps .lbl{flex:1;font-size:18px;line-height:1.3;color:" + MUTED + "}",
    ".done .lbl{color:" + INK + "}.doing .lbl{color:" + BLUE + ";font-weight:800}",
    ".steps small{font-size:14px;font-weight:700;color:" + MUTED + ";white-space:nowrap}",
    ".done small{color:" + GREEN + "}.doing small{color:" + BLUE + "}",
    ".says{background:#EEF3FD;border-radius:14px;padding:16px 18px;margin-top:22px;font-size:17px;line-height:1.45;color:" + INK + ";",
    "display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}",
    ".says b{font-weight:800}",
    /* Pendant que H agit : le panneau laisse passer les clics (H ne peut ni le cliquer ni le fermer) ;
       seuls Pause / Arrêter restent actifs (simple clic). */
    ".guard .side,.guard .side *{pointer-events:none}",
    ".guard .side .hold{pointer-events:auto}",
    /* 06 · votre accord */
    ".tag{align-self:flex-start;background:#7A4A10;color:#fff;border-radius:8px;padding:6px 12px;font-size:16px;font-weight:800;margin-bottom:18px}",
    ".pts{list-style:none;padding:0;margin:18px 0 0;display:flex;flex-direction:column;gap:12px}",
    ".pts li{display:flex;gap:12px;font-size:18px;line-height:1.4;color:" + INK + "}",
    ".pts svg{width:20px;height:20px;flex:none;margin-top:3px;color:" + GREEN + "}",
    ".ambre{display:flex;gap:12px;background:#FBF3E4;color:" + AMBER + ";border-radius:14px;padding:16px 18px;",
    "font-size:18px;font-weight:800;line-height:1.4;margin-top:20px}",
    ".ambre svg{width:22px;height:22px;flex:none;margin-top:2px}",
    /* 07 · c'est fait / 10 · échec */
    ".badge{width:92px;height:92px;border-radius:50%;display:flex;align-items:center;justify-content:center;margin-bottom:22px}",
    ".badge svg{width:42px;height:42px}",
    ".badge.ok{background:" + GREEN + ";color:#fff}.badge.warn{background:#FBF3E4;color:" + AMBER + ";width:64px;height:64px}",
    ".badge.warn svg{width:30px;height:30px}.badge.info{background:#E8EEFB;color:" + BLUE + "}",
    ".big1{font-size:38px}",
    ".box{background:" + SOFT + ";border-radius:14px;padding:18px 20px;margin-top:22px}",
    ".box ol{margin:10px 0 0;padding-left:22px}",
    ".box li{font-size:17px;line-height:1.4;color:" + INK + ";margin-top:6px}",
    ".okpill{display:flex;align-items:center;gap:12px;background:#E9F4EE;color:" + GREEN + ";border-radius:14px;padding:16px 18px;",
    "font-size:18px;font-weight:800;margin-top:20px}",
    ".okpill svg{width:22px;height:22px;flex:none}",
    ".q{font-size:18px;font-weight:800;color:" + INK + ";margin-top:22px}",
    ".off{font-size:15px;color:#B42318;margin-top:14px;text-align:center}",
    /* petits écrans (portable 13") : tout tient sans défiler */
    "@media (max-height:820px){.head{padding:12px 20px}.head .av{width:52px;height:52px}.body{padding:18px 22px}",
    ".talk{margin-top:16px}.talk .halo{width:150px;height:150px}.talk .disc{width:118px;height:118px}.talk b{margin-top:12px;font-size:23px}",
    ".sep{margin:16px 0 12px}.grid{margin-top:12px}.chip{padding:13px 8px}.steps{gap:12px;margin-top:14px}.count{margin-top:14px}",
    ".badge.ok{width:76px;height:76px;margin-bottom:16px}.big1{font-size:32px}.foot{padding:14px 22px 16px}.btn{padding:15px 12px}}"
  ].join("");

  // ---- icônes (SVG en ligne) ----
  var ICON = {
    avatar: '<svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="9" r="5" fill="' + BLUE + '"/>' +
      '<path d="M10 24c0-8.5 6-14 14-14s14 5.5 14 14c-3.2-4.6-8-6.6-14-6.6S13.2 19.4 10 24z" fill="' + BLUE + '"/>' +
      '<circle cx="17.5" cy="26" r="5.4" fill="none" stroke="#111827" stroke-width="2.6"/>' +
      '<circle cx="30.5" cy="26" r="5.4" fill="none" stroke="#111827" stroke-width="2.6"/>' +
      '<path d="M22.9 25.5h2.2" stroke="#111827" stroke-width="2.6"/>' +
      '<path d="M19 35q5 4 10 0" fill="none" stroke="#111827" stroke-width="2.6" stroke-linecap="round"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21"/></svg>',
    chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    tick: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5L2.5 20h19L12 3.5z"/><path d="M12 10v4.5M12 17.3v.2"/></svg>',
    lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/></svg>',
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"/><path d="M8.5 12l2.5 2.5 4.5-5"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.2"/></svg>'
  };

  function hasBinding() { return typeof window.__coletteSend === "function"; }

  function send(msg) {
    if (HOSTED && /^(open|call|shortcut|resume)$/.test(msg.type)) startAudio();  // geste de la personne
    if (hasBinding()) window.__coletteSend(JSON.stringify(msg));
    else if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg));
  }

  // ---- audio (mode en ligne) ----
  function startAudio() {
    try {
      if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        playAt = 0;
      }
      if (audioCtx.state === "suspended") audioCtx.resume();
    } catch (e) { return; }
    if (micStream || !navigator.mediaDevices) return;
    micStream = "pending";
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      .then(function (stream) {
        micStream = stream;
        var src = audioCtx.createMediaStreamSource(stream);
        micNode = audioCtx.createScriptProcessor(4096, 1, 1);
        var ratio = audioCtx.sampleRate / IN_RATE;
        micNode.onaudioprocess = function (ev) {
          var input = ev.inputBuffer.getChannelData(0);
          ev.outputBuffer.getChannelData(0).fill(0);
          if (!ws || ws.readyState !== 1) return;
          var n = Math.floor(input.length / ratio), out = new Int16Array(n);
          for (var i = 0; i < n; i++) {
            var start = Math.floor(i * ratio), end = Math.min(input.length, Math.floor((i + 1) * ratio)), sum = 0;
            for (var j = start; j < end; j++) sum += input[j];
            var v = sum / Math.max(1, end - start);
            out[i] = v < 0 ? Math.max(-1, v) * 0x8000 : Math.min(1, v) * 0x7fff;
          }
          ws.send(out.buffer);
        };
        src.connect(micNode);
        micNode.connect(audioCtx.destination);  // nécessaire pour que onaudioprocess tourne (sortie muette)
      })
      .catch(function () {
        micStream = null;  // micro refusé : la zone de texte reste disponible
        console.warn("Colette : micro refusé — autorisez-le dans la barre d'adresse, ou écrivez dans la zone de texte.");
      });
  }

  function playPcm(buf) {
    if (!audioCtx) return;
    var pcm = new Int16Array(buf), n = pcm.length;
    if (!n) return;
    var b = audioCtx.createBuffer(1, n, OUT_RATE), ch = b.getChannelData(0);
    for (var i = 0; i < n; i++) ch[i] = pcm[i] / 0x8000;
    var src = audioCtx.createBufferSource();
    src.buffer = b;
    src.connect(audioCtx.destination);
    var now = audioCtx.currentTime;
    if (playAt < now + 0.03) playAt = now + 0.08;  // petit tampon anti-saccades
    src.start(playAt);
    playAt += b.duration;
    playing.push(src);
    src.onended = function () { var k = playing.indexOf(src); if (k >= 0) playing.splice(k, 1); };
  }

  function flushAudio() {
    for (var i = 0; i < playing.length; i++) { try { playing[i].stop(); } catch (e) { /* ignore */ } }
    playing = []; playAt = 0;
  }

  // ---- zone de texte (mode en ligne) : écrire à Colette au lieu de parler ----
  var typeForm = null;
  function typeBox() {
    if (!typeForm) {
      typeForm = el("form", "typebox");
      var inp = el("input"); inp.type = "text"; inp.placeholder = "Ou écrivez ici (ex. « oui »)…";
      inp.setAttribute("aria-label", "Écrire à Colette");
      var b = el("button", null, "Envoyer"); b.type = "submit";
      typeForm.appendChild(inp); typeForm.appendChild(b);
      typeForm.onsubmit = function (ev) {
        ev.preventDefault();
        var v = inp.value.trim();
        if (v) { send({ type: "text", text: v }); inp.value = ""; }
      };
    }
    return typeForm;
  }

  // ---- écran de l'agent (mode en ligne) : captures du navigateur cloud de H ----
  function renderLive() {
    if (!HOSTED || !root) return;
    var show = !!shot && state.open && (state.busy || !!state.confirm);
    if (!liveEl) {
      liveEl = el("div", "live");
      var bar = el("div", "livebar");
      bar.appendChild(el("i"));
      bar.appendChild(el("span", null, "Écran de Colette : elle fait la démarche pour vous, en direct"));
      liveEl.appendChild(bar);
      var box = el("div", "livebox");
      var img = el("img"); img.alt = "Ce que voit Colette";
      box.appendChild(img);
      var cur = el("div", "livecur"); cur.appendChild(el("span", null, "↓ Je clique ici"));
      box.appendChild(cur);
      liveEl.appendChild(box);
      liveEl.appendChild(el("div", "liveurl"));
      root.appendChild(liveEl);
    }
    liveEl.style.display = show ? "flex" : "none";
    if (!show) return;
    var im = liveEl.querySelector("img");
    if (im.getAttribute("src") !== shot.image) im.setAttribute("src", shot.image);
    liveEl.querySelector(".liveurl").textContent = shot.title || shot.url || "";
    placeCursor();
  }

  function placeCursor() {
    if (!liveEl || !shot) return;
    var im = liveEl.querySelector("img"), cur = liveEl.querySelector(".livecur");
    var c = shot.cursor, vp = shot.viewport;
    if (!c || !vp || !vp[0] || (c[0] === 0 && c[1] === 0) || !im.naturalWidth) { cur.style.display = "none"; return; }
    var box = im.parentNode.getBoundingClientRect(), r = im.getBoundingClientRect();
    var k = Math.min(r.width / vp[0], r.height / vp[1]);
    var w = vp[0] * k, h = vp[1] * k, ox = r.left + (r.width - w) / 2 - box.left, oy = r.top + (r.height - h) / 2 - box.top;
    cur.style.display = "block";
    cur.style.left = (ox + c[0] * k - 18) + "px";
    cur.style.top = (oy + c[1] * k - 18) + "px";
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function svg(name) {
    var s = el("span");
    s.style.display = "contents";
    s.innerHTML = ICON[name];
    return s;
  }

  function avatar() { var a = el("div", "av"); a.innerHTML = ICON.avatar; return a; }

  function button(cls, text, onclick) {
    var b = el("button", "btn " + (cls || ""), text);
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

  function wave(still) {
    var w = el("div", "wave" + (still ? " still" : ""));
    for (var i = 0; i < 11; i++) {
      var bar = el("i");
      bar.style.animationDelay = (-((Date.now() + i * 137) % 1000)) + "ms";  // même phase après chaque rendu
      bar.style.animationDuration = (0.8 + (i % 3) * 0.2) + "s";
      w.appendChild(bar);
    }
    return w;
  }

  function lastColette() {
    var t = state.transcript || [];
    for (var i = t.length - 1; i >= 0; i--) if (t[i].who !== "vous") return t[i].text;
    return "";
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

  function statusFor(scr) {
    if (state.status === "paused" && (scr === "call" || scr === "working")) return ["amber", "En pause"];
    if (scr === "call") return state.status === "speaking" ? ["blue", "Colette vous parle…"] : ["blue", "Je vous écoute…"];
    if (scr === "working") return state.status === "listening" ? ["blue", "Je vous écoute…"] : ["blue", "Je navigue pour vous"];
    if (scr === "confirm") return ["amber", "Attend votre accord"];
    if (scr === "failed") return ["amber", "Colette a besoin d'aide"];
    if (scr === "done") return state.outcome && state.outcome.kind !== "success" ? ["blue", "Démarche arrêtée"] : ["green", "Terminé"];
    return ["green", "Disponible"];
  }

  function render() {
    if (!root) return;
    var scr = screen();
    var shown = {}; for (var f in state) if (f !== "subtitle") shown[f] = state[f];  // sous-titres mot à mot : non affichés
    var key = JSON.stringify([shown, connected]);
    renderLive();
    if (key === lastKey) return;  // rien n'a changé : pas de reconstruction
    lastKey = key;
    var wrap = root.getElementById("wrap");
    var hadFocus = typeForm && root.activeElement === typeForm.firstChild;
    wrap.className = "wrap" + (scr === "working" ? " guard" : "");
    wrap.textContent = "";
    setPush(state.open);
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

    if (scr === "working") wrap.appendChild(el("div", "frame"));
    if (markBox) wrap.appendChild(markBox);

    var side = el("div", "side");
    side.setAttribute("role", "dialog");
    side.setAttribute("aria-label", "Colette");
    wrap.appendChild(side);
    var closeFn = function () { state.open = false; render(); send({ type: "close" }); };

    var top = el("div", "top");
    top.appendChild(el("span", null, "Colette"));
    if (scr !== "working") { var tx = el("button"); tx.setAttribute("aria-label", "Fermer"); tx.appendChild(svg("x")); tx.onclick = closeFn; top.appendChild(tx); }
    side.appendChild(top);

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
    if (scr !== "working") {  // pas de fermeture pendant que H agit
      var x = el("button", "x");
      x.setAttribute("aria-label", "Fermer");
      x.appendChild(svg("x"));
      x.appendChild(el("span", null, "Fermer"));
      x.onclick = closeFn;
      head.appendChild(x);
    }
    side.appendChild(head);

    // Barre d'appel : dit toujours la vérité sur le micro.
    if (scr !== "home") {
      var live = state.call || state.busy, paused = state.status === "paused";
      var cb = el("div", "callbar" + (!live ? " ended" : paused ? " paused" : ""));
      var l = el("span"); l.appendChild(el("i"));
      l.appendChild(document.createTextNode(!live ? "Appel terminé · micro coupé" : paused ? "En pause · micro coupé" : "Appel en cours · micro allumé"));
      var r = el("span"); r.appendChild(svg("lock")); r.appendChild(document.createTextNode("Je ne garde rien"));
      cb.appendChild(l); cb.appendChild(r);
      side.appendChild(cb);
    }

    var body = el("div", "body");
    var foot = el("div", "foot");
    side.appendChild(body);
    ({ home: home, call: call, working: working, confirm: confirm, done: done, failed: failed })[scr](body, foot);
    if (HOSTED && (scr === "call" || scr === "working" || scr === "confirm")) {
      foot.insertBefore(typeBox(), foot.firstChild);  // sans micro : on peut aussi écrire à Colette
      if (hadFocus) typeForm.firstChild.focus();
    }
    if (!connected) body.appendChild(el("div", "off", busyServer
      ? "Colette aide déjà d'autres personnes en ce moment. Réessayez dans quelques minutes."
      : "Connexion à Colette perdue… je réessaie."));
    if (foot.childNodes.length) side.appendChild(foot);
  }

  // ---- 02 · ouverte ----
  function home(body) {
    body.appendChild(el("h2", null, "Bonjour, je suis Colette."));
    body.appendChild(el("p", "lead", "Dites-moi simplement ce que vous voulez faire."));
    var talk = el("button", "talk");
    var halo = el("span", "halo"), disc = el("span", "disc");
    disc.appendChild(svg("mic")); halo.appendChild(disc); talk.appendChild(halo);
    talk.appendChild(el("b", null, "Appuyer pour parler"));
    talk.onclick = function () { state.call = true; render(); send({ type: "call" }); };
    body.appendChild(talk);
    var lock = el("div", "lock"); lock.appendChild(svg("lock"));
    lock.appendChild(el("span", null, "Je ne garde rien de ce que vous dites."));
    body.appendChild(lock);
    var shortcuts = state.shortcuts || [];
    if (shortcuts.length) {
      body.appendChild(el("div", "sep"));
      body.appendChild(el("div", "or", "Ou choisissez directement :"));
      var grid = el("div", "grid");
      shortcuts.forEach(function (s) {
        var c = el("button", "chip", s.label);
        c.onclick = function () { state.call = true; render(); send({ type: "shortcut", id: s.id }); };
        grid.appendChild(c);
      });
      body.appendChild(grid);
    }
  }

  // ---- 03 / 04 · conversation en continu ----
  function call(body, foot) {
    var paused = state.status === "paused", speaking = state.status === "speaking";
    var msgs = (state.transcript || []).slice(-3).map(function (m) { return { who: m.who, text: m.text }; });
    if (state.heard && !paused) msgs.push({ who: "vous", text: state.heard, live: true });
    msgs = msgs.slice(-3);
    var chat = el("div", "chat");
    var prev = null;
    msgs.forEach(function (m, i) {
      var me = m.who === "vous";
      if (m.who !== prev) chat.appendChild(el("div", "who2" + (me ? " me" : ""), me ? "Vous" : "Colette"));
      prev = m.who;
      var b = el("div", "msg" + (me ? " me" : "") + (i === msgs.length - 1 ? " now" : ""), m.text);
      if (m.live) b.appendChild(el("span", "caret"));
      chat.appendChild(b);
    });
    body.appendChild(chat);
    var last = msgs[msgs.length - 1];
    if (last && last.who !== "vous" && /\?\s*$/.test(last.text) && !paused) {
      var h = el("div", "hintbox"); h.appendChild(svg("mic"));
      h.appendChild(el("span", null, "Répondez simplement « oui » ou « non » à voix haute."));
      body.appendChild(h);
    }
    var lis = el("div", "listen" + (paused ? " grey" : speaking ? " blue" : ""));
    lis.appendChild(wave(paused));
    lis.appendChild(el("div", null, paused ? "En pause — je n'écoute plus." : speaking ? "Colette vous parle…" : "Je vous écoute… prenez votre temps."));
    body.appendChild(lis);
    var row = el("div", "row2");
    row.appendChild(button("sec", paused ? "Reprendre" : "Pause", function () { send({ type: paused ? "resume" : "pause" }); }));
    row.appendChild(button("dark", "Arrêter l'appel", function () { state.call = false; render(); send({ type: "hangup" }); }));
    foot.appendChild(row);
  }

  // ---- 05 · navigue (H agit) ----
  function working(body, foot) {
    var steps = state.steps || [];
    body.appendChild(el("h2", null, state.title || "Je m'occupe de votre demande"));
    if (steps.length) {
      var cur = 0;
      steps.forEach(function (s, i) { if (s.state === "doing") cur = i + 1; });
      var doneN = steps.filter(function (s) { return s.state === "done"; }).length;
      if (!cur) cur = Math.min(doneN + 1, steps.length);
      body.appendChild(el("div", "count", "Étape " + cur + " sur " + steps.length));
      var segs = el("div", "segs");
      steps.forEach(function (s, i) { segs.appendChild(el("i", i < cur ? "on" : null)); });
      body.appendChild(segs);
      var ul = el("ul", "steps");
      var start = Math.max(0, Math.min(cur - 3, steps.length - 6));
      steps.slice(start, start + 6).forEach(function (s) {
        var li = el("li", s.state);
        var d = el("span", "dot");
        if (s.state === "done") d.appendChild(svg("check"));
        li.appendChild(d);
        li.appendChild(el("span", "lbl", s.label));
        li.appendChild(el("small", null, s.state === "done" ? "Fait" : s.state === "doing" ? "En cours" : "À venir"));
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }
    var said = lastColette();
    var says = el("div", "says");
    says.appendChild(el("b", null, "Colette dit : "));
    says.appendChild(document.createTextNode(state.status === "paused" ? "Je suis en pause. Vous avez la main."
      : said || "Vous n'avez rien à faire. Je vous préviens si j'ai besoin de vous."));
    body.appendChild(says);
    var paused = state.status === "paused";
    var row = el("div", "row2");
    // .hold : seuls boutons cliquables pendant que H agit (simple clic).
    row.appendChild(button("sec hold", paused ? "Reprendre" : "Pause", function () { send({ type: paused ? "resume" : "pause" }); }));
    row.appendChild(button("dark hold", "Arrêter", function () { send({ type: "stop" }); }));
    foot.appendChild(row);
  }

  // ---- 06 · votre accord ----
  function confirm(body, foot) {
    var c = state.confirm || {};
    body.appendChild(el("div", "tag", "À vous"));
    body.appendChild(el("h2", null, c.title || c.text || "Je valide ?"));
    var pts = c.bullets || [];
    if (pts.length) {
      var ul = el("ul", "pts");
      pts.forEach(function (p) { var li = el("li"); li.appendChild(svg("tick")); li.appendChild(el("span", null, p)); ul.appendChild(li); });
      body.appendChild(ul);
    }
    var a = el("div", "ambre"); a.appendChild(svg("mic"));
    a.appendChild(el("span", null, "Dites « oui » ou touchez le bouton. Rien ne change sans votre accord."));
    body.appendChild(a);
    foot.appendChild(button("", c.yes || "Oui, je suis d'accord", function () { send({ type: "confirm", value: true }); }));
    foot.appendChild(button("sec", c.no || "Non, ne rien changer", function () { send({ type: "confirm", value: false }); }));
  }

  // ---- 07 · c'est fait (ou arrêté / refusé) ----
  function done(body, foot) {
    var o = state.outcome || {};
    var ok = o.kind === "success";
    var b = el("div", "badge " + (ok ? "ok" : "info"));
    b.appendChild(svg(ok ? "tick" : "info"));
    body.appendChild(b);
    body.appendChild(el("h2", "big1", o.title || (ok ? "C'est fait !" : "Rien n'a été changé")));
    if (o.text) { var p = el("p", null, o.text); p.style.marginTop = "14px"; body.appendChild(p); }
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
    var row = el("div", "row2");
    row.appendChild(button("sec", "Écouter ce résumé", function () { send({ type: "replay" }); }));
    row.appendChild(button("dark", "Terminer l'appel", function () { state.open = false; render(); send({ type: "later" }); }));
    foot.appendChild(row);
  }

  function okPill() {
    var g = el("div", "okpill");
    g.appendChild(svg("shield"));
    g.appendChild(el("span", null, "Rien n'a été modifié sur votre compte."));
    return g;
  }

  // ---- 10 · échec ----
  function failed(body, foot) {
    var o = state.outcome || {};
    var b = el("div", "badge warn"); b.appendChild(svg("warn")); body.appendChild(b);
    body.appendChild(el("h2", null, o.title || "Je n'ai pas pu terminer"));
    var p = el("p", null, (o.text || "Le site ne répond pas comme prévu.") + " Ce n'est pas de votre faute.");
    p.style.marginTop = "12px";
    body.appendChild(p);
    if (o.nothing_changed) body.appendChild(okPill());
    body.appendChild(el("div", "q", "Que voulez-vous faire ?"));
    var rows = el("div", "rows");
    rows.appendChild(rowButton("Parler à un conseiller", function () { send({ type: "advisor" }); }));
    rows.appendChild(rowButton("Réessayer une fois", function () { send({ type: "retry" }); }));
    body.appendChild(rows);
    foot.appendChild(button("sec", "Laisser pour plus tard", function () { state.open = false; render(); send({ type: "later" }); }));
  }

  // ---- La page se pousse à gauche pour faire place au panneau : rien n'est caché dessous ----
  var pushStyle = null, pushed = false, fixTimer = null;
  var FX = "data-colette-fx";

  function setPush(open) {
    if (open === pushed) return;
    pushed = open;
    if (!open) {
      if (pushStyle && pushStyle.parentNode) pushStyle.parentNode.removeChild(pushStyle);
      clearInterval(fixTimer); fixTimer = null;
      restoreFixed();
    } else {
      if (!pushStyle) {
        pushStyle = document.createElement("style");
        pushStyle.setAttribute("data-colette", "1");
        pushStyle.textContent = "html{margin-right:" + PANEL_W + "px!important;width:auto!important;" +
          "max-width:calc(100vw - " + PANEL_W + "px)!important;overflow-x:hidden!important}";
      }
      (document.head || document.documentElement).appendChild(pushStyle);
      fixFixed();
      fixTimer = setInterval(fixFixed, 1500);  // bannières / en-têtes ajoutés après coup
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
      e.setAttribute(FX, JSON.stringify({ right: e.style.right, maxWidth: e.style.maxWidth }));
      if (r.left > limit - r.width / 2 && r.width < limit) {  // ancré à droite (ex. bouton de chat)
        e.style.setProperty("right", ((parseFloat(cs.right) || 0) + PANEL_W) + "px", "important");
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
      for (var p in o) e.style[p] = o[p] || "";
      e.removeAttribute(FX);
    }
  }

  // ---- « Je clique ici » : cadre sur l'élément que l'agent H vient de cliquer ----
  var markTarget = null, markBox = null, markTimer = null;

  function setMark(t) {
    var target = (t.closest && t.closest("a,button,label,li,tr,[role=button],[role=link],input,select,textarea")) || t;
    if (target === document.body || target === document.documentElement) return;
    markTarget = target;
    if (!markBox) {
      markBox = el("div", "mark");
      markBox.appendChild(el("span", null, "↓ Je clique ici"));
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
    var pad = 6;
    markBox.style.left = (r.left - pad) + "px"; markBox.style.top = (r.top - pad) + "px";
    markBox.style.width = (r.width + 2 * pad) + "px"; markBox.style.height = (r.height + 2 * pad) + "px";
  }

  function connect() {
    try { ws = new WebSocket(WS_URL); } catch (e) { setTimeout(connect, 1000); return; }
    ws.binaryType = "arraybuffer";
    ws.onopen = function () { connected = true; busyServer = false; render(); };
    ws.onmessage = function (ev) {
      if (typeof ev.data !== "string") { playPcm(ev.data); return; }
      try {
        var msg = JSON.parse(ev.data);
        if (msg.type === "state" && msg.state) {
          state = msg.state;
          render();
        } else if (msg.type === "screen") { shot = msg; renderLive(); }
        else if (msg.type === "busy") { busyServer = true; }
      } catch (e) { /* ignore */ }
    };
    ws.onclose = function () {
      connected = false; ws = null; render();
      setTimeout(connect, busyServer ? 15000 : (HOSTED ? 2000 : 1000));
    };
    ws.onerror = function () { /* onclose suit */ };
  }

  window.__colette.getState = function () { return { state: state, connected: connected, screen: screen() }; };
  window.__colette.root = function () { return root; };
  window.__colette.onState = function (s) { connected = true; state = s; render(); };

  // Changer de page ou d'onglet ne ferme JAMAIS la bulle : l'état vit côté serveur et la bulle
  // réinjectée dans la nouvelle page reprend là où elle en était (appel et démarche continuent).

  // Diagnostic : où atterrissent vraiment les clics (ceux de H inclus) ? + cadre « Je clique ici ».
  window.addEventListener("resize", function () { placeCursor(); });
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
