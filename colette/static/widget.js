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
  var audioCtx = null, micStream = null, micNode = null, playAt = 0, playing = [], micWanted = false;
  var outNode = null, outEl = null;
  var shot = null, liveEl = null, busyServer = false;
  var PANEL_W = 440;  // largeur du panneau ; la page est rétrécie d'autant (rien n'est caché)
  var state = { open: false, status: "idle", steps: [], subtitle: "", confirm: null };
  var connected = false;
  var ws = null;
  var host, root, lastKey = "";

  var BLUE = "#2155D3", INK = "#0F172A", MUTED = "#475569", LINE = "#E2E6EE";
  var GREEN = "#2E6B4A", AMBER = "#8A5A12", SOFT = "#F3F5F9";
  var CALL = "#1E8E3E", RED = "#C62828";

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
    ".live{position:fixed;z-index:2147483646;left:0;top:0;bottom:0;right:" + PANEL_W + "px;background:#0F172A;display:none;flex-direction:column;",
    "padding:14px 18px 12px;gap:10px;pointer-events:auto}",
    ".livebar{display:flex;align-items:center;gap:10px;color:#fff;font-size:18px;font-weight:800}",
    ".livebar i{width:11px;height:11px;border-radius:50%;background:#EF4444;animation:halo 1.6s ease-in-out infinite}",
    ".livebox{position:relative;flex:1;min-height:0;display:flex;align-items:center;justify-content:center;",
    "border-radius:12px;overflow:hidden;border:4px solid transparent;border-image:linear-gradient(90deg,#4F6BFF,#B66CE0 50%,#4F6BFF) 1}",
    ".livebox img{max-width:100%;max-height:100%;object-fit:contain;background:#fff;display:block}",
    ".livecur{position:absolute;width:36px;height:36px;border:3px solid #fff;border-radius:50%;background:rgba(33,85,211,.55);",
    "box-shadow:0 0 0 4px rgba(33,85,211,.5);display:none}",
    ".livecur span{position:absolute;left:-4px;bottom:calc(100% + 8px);background:" + BLUE + ";color:#fff;font-size:15px;font-weight:700;",
    "padding:6px 12px;border-radius:8px;white-space:nowrap}",
    ".typebox{display:flex;gap:8px}.typebox input{flex:1;min-width:0;font:inherit;font-size:17px;padding:12px 14px;border:1.5px solid #D3D8E2;border-radius:12px}",
    ".typebox button{font-size:16px;font-weight:800;padding:0 16px;border-radius:12px;border:2px solid " + BLUE + ";background:#fff;color:" + BLUE + "}",
    ".hl{position:fixed;z-index:2147483646;pointer-events:none!important;animation:halo 1.6s ease-in-out infinite}",
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
    ".talk{display:flex;flex-direction:column;align-items:center;margin-top:16px;background:none;border:none;width:100%}",
    ".talk .halo{width:150px;height:150px;border-radius:50%;background:#EAF0FC;display:flex;align-items:center;justify-content:center}",
    ".talk .disc{width:118px;height:118px;border-radius:50%;background:" + BLUE + ";color:#fff;display:flex;align-items:center;justify-content:center}",
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
    ".guard .side .typebox,.guard .side .typebox *{pointer-events:auto}",
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
    /* appel : bouton vert, raccrocher rouge, minuteur, exemples, garanties */
    ".talk .halo.callh{background:#E6F4EA}.talk .disc.calld{background:" + CALL + "}.talk:hover .disc.calld{background:#17752F}",
    ".talk small{font-size:16px;color:" + MUTED + ";margin-top:6px}",
    ".pill .ph{position:absolute;left:48px;top:46px;width:24px;height:24px;border-radius:50%;background:" + CALL + ";border:2px solid #fff;",
    "display:flex;align-items:center;justify-content:center}.pill .ph svg{width:13px;height:13px;color:#fff}.pill{position:fixed}",
    ".ex{display:flex;flex-direction:column;gap:10px;margin-top:12px}",
    ".exb{width:100%;text-align:left;background:" + SOFT + ";border:1.5px solid transparent;border-radius:14px;padding:10px 16px;",
    "font-size:17px;line-height:1.3;font-style:italic;color:" + INK + "}.exb:hover{border-color:" + BLUE + ";background:#F7F9FE}",
    ".guar{list-style:none;padding:0;margin:20px 0 0;display:flex;flex-direction:column;gap:10px;border-top:1px solid " + LINE + ";padding-top:16px}",
    ".guar li{display:flex;gap:10px;align-items:flex-start;font-size:15.5px;line-height:1.35;color:" + INK + "}",
    ".guar svg{width:19px;height:19px;flex:none;color:" + GREEN + ";margin-top:1px}",
    ".mini{font-size:14px;color:" + MUTED + ";text-align:center;line-height:1.35}",
    ".btn.red{background:" + RED + ";border-color:" + RED + ";color:#fff}.btn.red:hover{background:#A51F1F}",
    ".btn svg{width:22px;height:22px}",
    ".tm{font-variant-numeric:tabular-nums;font-weight:800}",
    /* petits écrans (portable 13") : tout tient sans défiler */
    "@media (max-height:820px){.head{padding:12px 20px}.head .av{width:52px;height:52px}.body{padding:18px 22px}",
    ".talk{margin-top:16px}.talk .halo{width:150px;height:150px}.talk .disc{width:118px;height:118px}.talk b{margin-top:12px;font-size:23px}",
    ".sep{margin:16px 0 12px}.grid{margin-top:12px}.chip{padding:13px 8px}.steps{gap:12px;margin-top:14px}.count{margin-top:14px}",
    ".badge.ok{width:76px;height:76px;margin-bottom:16px}.big1{font-size:32px}.foot{padding:14px 22px 16px}.btn{padding:15px 12px}}",
    /* guide pas à pas : anneau autour de l'élément à cliquer + petite fenêtre de consigne */
    ".glayer{position:fixed;inset:0;z-index:2147483645;pointer-events:none}.glayer.hidden{display:none}",
    ".ring{position:fixed;border:4px solid " + BLUE + ";border-radius:12px;pointer-events:none;",
    "box-shadow:0 0 0 9999px rgba(15,23,42,.25);animation:gring 1.2s ease-in-out infinite}",
    ".ring.warn{border-color:#E65100}",
    "@keyframes gring{0%,100%{outline:0 solid rgba(33,85,211,.5)}50%{outline:8px solid rgba(33,85,211,0)}}",
    ".tip{position:fixed;width:320px;background:#fff;color:" + INK + ";border:3px solid " + BLUE + ";border-radius:16px;",
    "padding:12px 14px;box-shadow:0 12px 32px rgba(15,23,42,.3);pointer-events:auto;font:16px/1.4 system-ui,sans-serif}",
    ".tip.warn{border-color:#E65100;background:#FFF3E0}",
    ".tip .n{font-size:14px;font-weight:700;color:" + BLUE + ";margin-bottom:4px}.tip.warn .n{color:#E65100}",
    ".tip .t{font-size:19px;line-height:1.35;font-weight:600;margin-bottom:10px}",
    ".tip button{font-size:16px;font-weight:700;padding:8px 14px;border-radius:10px;border:2px solid " + BLUE + ";",
    "background:" + BLUE + ";color:#fff;cursor:pointer}"
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
    phone: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6.6 10.8a15.1 15.1 0 006.6 6.6l2.2-2.2a1 1 0 011-.25c1.1.37 2.3.57 3.6.57a1 1 0 011 1V20a1 1 0 01-1 1A17 17 0 013 4a1 1 0 011-1h3.5a1 1 0 011 1c0 1.3.2 2.5.57 3.6a1 1 0 01-.25 1L6.6 10.8z"/></svg>',
    hangup: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .4-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85a1 1 0 01-1.41-.02L.29 13.08a1 1 0 010-1.41C3.34 8.77 7.46 7 12 7s8.66 1.77 11.71 4.67a1 1 0 010 1.41l-2.48 2.48a1 1 0 01-1.41.02 11.3 11.3 0 00-2.67-1.85 1 1 0 01-.56-.9v-3.1A15 15 0 0012 9z"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.2"/></svg>'
  };

  function hasBinding() { return typeof window.__coletteSend === "function"; }

  // Mode en ligne : la bulle ne se connecte au backend qu'au premier geste (ouvrir, appeler, écrire).
  // Un onglet ouvert sans appel ne prend donc plus de place parmi les sessions du serveur.
  var pendingMsgs = [], idleTimer = null, wantConn = !HOSTED;
  function ensureConn(msg) {
    wantConn = true;
    if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; }
    if (ws && ws.readyState === 1) return false;
    if (/^(open|call|shortcut|text|resume|retry)$/.test(msg.type)) pendingMsgs.push(msg);
    if (!ws) connect();
    return true;  // message envoyé à la connexion
  }
  function scheduleIdleClose() {
    // raccroché et rien en cours : on rend la session au serveur au bout d'une minute
    if (!HOSTED) return;
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(function () {
      idleTimer = null;
      if (state.busy || state.call) return;
      wantConn = false;
      if (ws) { try { ws.close(); } catch (e) { /* ignore */ } }
    }, 60000);
  }

  function send(msg) {
    if (HOSTED && !hasBinding() && /^(open|call|shortcut|text|resume|retry)$/.test(msg.type) && ensureConn(msg)) {
      if (/^(open|call|shortcut|resume)$/.test(msg.type)) startAudio();
      return;
    }
    if (HOSTED && /^(hangup|later)$/.test(msg.type)) { stopAudio(); scheduleIdleClose(); }  // raccrocher : micro rendu, son coupé
    if (HOSTED && /^(open|call|shortcut|resume)$/.test(msg.type)) startAudio();  // geste de la personne
    if (HOSTED && /^(open|call|shortcut|text)$/.test(msg.type)) setTimeout(shareSession, 0);
    if (hasBinding()) window.__coletteSend(JSON.stringify(msg));
    else if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg));
  }

  // ---- audio (mode en ligne) ----
  function startAudio() {
    micWanted = true;
    try {
      if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        playAt = 0;
        makeOutput();
      }
      if (audioCtx.state === "suspended") audioCtx.resume();
    } catch (e) { return; }
    if (micStream || !navigator.mediaDevices) return;
    micStream = "pending";
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      .then(function (stream) {
        if (!micWanted) { stream.getTracks().forEach(function (t) { t.stop(); }); micStream = null; return; }
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
        console.warn("Colette: microphone blocked. Allow it in the address bar, or type in the text box.");
      });
  }

  // Sortie audio : AudioContext → WebRTC en boucle locale → <audio>. L'anti-écho de Chrome ne prend
  // comme référence que le son joué par WebRTC : sans ça, le micro capte la voix de Colette et elle
  // « se répond » (vu le 7 nov). Repli sur la sortie directe si la boucle ne se connecte pas.
  function makeOutput() {
    outNode = audioCtx.destination;
    try {
      var dest = audioCtx.createMediaStreamDestination();
      var pc1 = new RTCPeerConnection(), pc2 = new RTCPeerConnection();
      pc1.onicecandidate = function (e) { if (e.candidate) pc2.addIceCandidate(e.candidate); };
      pc2.onicecandidate = function (e) { if (e.candidate) pc1.addIceCandidate(e.candidate); };
      outEl = document.createElement("audio");
      outEl.autoplay = true;
      pc2.ontrack = function (e) { outEl.srcObject = e.streams[0]; outEl.play().catch(function () {}); };
      dest.stream.getTracks().forEach(function (t) { pc1.addTrack(t, dest.stream); });
      pc1.createOffer()
        .then(function (o) { return pc1.setLocalDescription(o); })
        .then(function () { return pc2.setRemoteDescription(pc1.localDescription); })
        .then(function () { return pc2.createAnswer(); })
        .then(function (a) { return pc2.setLocalDescription(a); })
        .then(function () { return pc1.setRemoteDescription(pc2.localDescription); })
        .catch(function () { /* repli : sortie directe */ });
      var t0 = Date.now();
      var check = setInterval(function () {
        if (pc2.connectionState === "connected" || pc2.iceConnectionState === "connected" || pc2.iceConnectionState === "completed") {
          clearInterval(check); outNode = dest; window.__colette.aec = "webrtc";
        } else if (Date.now() - t0 > 3000) {
          clearInterval(check); window.__colette.aec = "direct";
        }
      }, 100);
      window.__colette.aec = "pending";
      window.__colette.out = function () { return { paused: outEl.paused, t: outEl.currentTime, ice: pc2.iceConnectionState }; };
    } catch (e) { outNode = audioCtx.destination; window.__colette.aec = "direct"; }
  }

  function playPcm(buf) {
    if (!audioCtx) return;
    var pcm = new Int16Array(buf), n = pcm.length;
    if (!n) return;
    var b = audioCtx.createBuffer(1, n, OUT_RATE), ch = b.getChannelData(0);
    for (var i = 0; i < n; i++) ch[i] = pcm[i] / 0x8000;
    var src = audioCtx.createBufferSource();
    src.buffer = b;
    src.connect(outNode || audioCtx.destination);
    var now = audioCtx.currentTime;
    if (playAt < now + 0.03) playAt = now + 0.08;  // petit tampon anti-saccades
    src.start(playAt);
    playAt += b.duration;
    playing.push(src);
    src.onended = function () { var k = playing.indexOf(src); if (k >= 0) playing.splice(k, 1); };
  }

  function stopAudio() {
    micWanted = false;
    flushAudio();
    if (micStream && micStream !== "pending") {
      try { micStream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) { /* ignore */ }
    }
    if (micNode) { try { micNode.disconnect(); } catch (e) { /* ignore */ } micNode.onaudioprocess = null; }
    micStream = null; micNode = null;
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
      var inp = el("input"); inp.type = "text"; inp.placeholder = "Or type here (e.g. \"yes\")…";
      inp.setAttribute("aria-label", "Write to Colette");
      var b = el("button", null, "Send"); b.type = "submit";
      typeForm.appendChild(inp); typeForm.appendChild(b);
      typeForm.onsubmit = function (ev) {
        ev.preventDefault();
        var v = inp.value.trim();
        if (v) { send({ type: "text", text: v }); inp.value = ""; }
      };
    }
    return typeForm;
  }

  // ---- connexion partagée (mode en ligne) ----
  // La personne tape elle-même identifiant et mot de passe sur SA page. Le formulaire part en fetch
  // (pas de rechargement : l'appel continue), puis la bulle demande au site un jeton de session à usage
  // court et l'envoie au backend : l'agent ouvre /colette/claim?t=… et se retrouve connecté.
  // Colette (et l'agent H) ne voient jamais le mot de passe.
  function swapPage(html, url, push) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var kids = Array.prototype.slice.call(document.body.childNodes);
    for (var i = 0; i < kids.length; i++) if (kids[i] !== host) document.body.removeChild(kids[i]);
    var nk = Array.prototype.slice.call(doc.body.childNodes);
    for (var j = 0; j < nk.length; j++) {
      if (nk[j].tagName === "SCRIPT") {
        // scripts en ligne de la page (bannière cookies…) rejoués ; jamais widget.js (src) une 2e fois
        if (!nk[j].src && !/COLETTE_BACKEND/.test(nk[j].textContent || "")) {
          var sc = document.createElement("script"); sc.textContent = nk[j].textContent;
          document.body.insertBefore(sc, host);
        }
        continue;
      }
      document.body.insertBefore(document.importNode(nk[j], true), host);
    }
    if (doc.title) document.title = doc.title;
    try {
      if (push && url !== location.href) history.pushState(null, "", url);
      else history.replaceState(null, "", url);
    } catch (e) { /* ignore */ }
  }

  // ---- navigation sans rechargement (mode en ligne) ----
  // Recharger la page = nouvelle bulle = nouvelle session : l'appel s'arrêtait à chaque clic sur un
  // onglet du site (« My plan », « Usage & bills »…). Les liens et formulaires du même site passent
  // donc en fetch + remplacement du contenu ; la bulle, l'appel et la démarche ne bougent pas.
  function softNavigable(u) {
    return u.origin === location.origin &&
      !/^\/(colette|reset|favicon)|^\/account\/logout|\.pdf$/.test(u.pathname);
  }
  function softGo(req, url, push) {
    return req.then(function (r) {
      var ct = r.headers.get("content-type") || "";
      if (!/text\/html/.test(ct)) { location.href = url; return; }  // fichier, autre : vrai chargement
      return r.text().then(function (t) {
        swapPage(t, r.url, push);
        if (state.guide) send({ type: "page_loaded" });  // guide pas à pas : nouvelle page à relire
        if (push) window.scrollTo(0, 0);
      });
    }).catch(function () { location.href = url; });
  }
  if (HOSTED) {
    document.addEventListener("click", function (ev) {
      if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      var a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
      if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download")) return;
      var u; try { u = new URL(a.getAttribute("href"), location.href); } catch (e) { return; }
      if (!softNavigable(u)) return;
      if (u.pathname === location.pathname && u.search === location.search && u.hash) return;  // ancre
      ev.preventDefault();
      softGo(fetch(u.href, { credentials: "same-origin", cache: "no-store" }), u.href, true);
    });
    window.addEventListener("popstate", function () {
      softGo(fetch(location.href, { credentials: "same-origin", cache: "no-store" }), location.href, false);
    });
  }

  // Partage proactif : à chaque demande, le backend reçoit un lien de reprise de la session de la
  // personne, sur sa page actuelle → l'agent démarre déjà connecté, là où elle est.
  var lastShare = 0;
  function shareSession() {
    if (!HOSTED || !connected || Date.now() - lastShare < 3000) return;
    lastShare = Date.now();
    fetch("/colette/handoff", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.token) return;
        var here = location.pathname + location.search;
        send({ type: "session", url: location.origin + "/colette/claim?t=" + encodeURIComponent(d.token) +
                                      "&next=" + encodeURIComponent(here) });
      })
      .catch(function () { /* pas connectée : l'agent demandera la connexion */ });
  }

  function tryHandoff(loud) {
    fetch("/colette/handoff", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && d.token) send({ type: "handoff", url: location.origin + "/colette/claim?t=" + encodeURIComponent(d.token) });
        else if (loud) send({ type: "handoff_missing" });
      })
      .catch(function () { if (loud) send({ type: "handoff_missing" }); });
  }

  // ---- formulaire rempli par la personne (mode en ligne) ----
  // L'agent travaille dans le navigateur cloud de H : la personne tape ses nouvelles informations dans le
  // formulaire de SA page ; « Done » → la bulle envoie ce qu'elle a tapé (jamais un mot de passe) et l'agent
  // le recopie. Après son « oui » et l'enregistrement par l'agent, on rejoue l'enregistrement sur sa page.
  var pendingForm = null;
  function pageForm() {
    var forms = document.querySelectorAll("form");
    for (var i = 0; i < forms.length; i++) {
      if (/\/account\/login/.test(forms[i].action || "")) continue;
      if (forms[i].querySelector("input:not([type=hidden]):not([type=submit]),select,textarea")) return forms[i];
    }
    return null;
  }
  function focusForm() {
    var f = pageForm(); if (!f) return;
    var first = f.querySelector("input:not([type=hidden]):not([type=submit]):not([type=password]),select,textarea");
    try { f.scrollIntoView({ block: "center", behavior: "smooth" }); if (first) first.focus(); } catch (e) { /* ignore */ }
  }
  function collectForm() {
    var f = pageForm(), vals = [];
    if (f) {
      var fields = f.querySelectorAll("input,select,textarea");
      for (var i = 0; i < fields.length; i++) {
        var e = fields[i];
        if (/^(hidden|submit|button|reset|password|checkbox|radio|file|image)$/.test(e.type || "")) continue;
        var changed = e.tagName === "SELECT" ? !e.options[e.selectedIndex] || !e.options[e.selectedIndex].defaultSelected
                                             : e.value !== e.defaultValue;
        vals.push({ label: labelOf(e).replace(/\s*\(selected:.*\)$/, ""), value: e.value, changed: changed });
      }
      var only = vals.filter(function (v) { return v.changed; });
      if (only.length) vals = only;  // seulement ce qu'elle a changé (sinon tout, l'agent comparera)
      pendingForm = { action: f.action, body: new URLSearchParams(new FormData(f)).toString() };
    }
    send({ type: "form_values", values: vals });
  }
  function replayForm() {
    if (!pendingForm) return;
    var pf = pendingForm; pendingForm = null;
    if (!state.outcome || state.outcome.kind !== "success") return;  // refusé / arrêté : rien n'est enregistré
    fetch(pf.action, { method: "POST", body: new URLSearchParams(pf.body), credentials: "same-origin" })
      .then(function (r) { return r.text().then(function (t) { swapPage(t, r.url, false); }); })
      .catch(function () { /* ignore */ });
  }

  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    // pendant la saisie : « Save » sur sa page = « Done » (l'enregistrement se fait après son accord)
    if (HOSTED && state.form_handoff && f && !/\/account\/login/.test(f.action || "")) {
      ev.preventDefault(); ev.stopImmediatePropagation(); collectForm(); return;
    }
    if (!HOSTED || !connected || !(state.busy || state.call) || !f || !f.action) return;
    if (!/\/account\/login/.test(f.action)) return;
    ev.preventDefault();
    var body = new URLSearchParams(new FormData(f));
    fetch(f.action, { method: "POST", body: body, credentials: "same-origin" })
      .then(function (r) { return r.text().then(function (t) { return [r, t]; }); })
      .then(function (rt) {
        var r = rt[0];
        swapPage(rt[1], r.url);
        if (!/\/account\/login/.test(r.url)) tryHandoff(true);  // connectée : on partage la session
      })
      .catch(function () { f.submit(); });
  }, true);

  // Autres formulaires du site (modifier ses coordonnées, valider un forfait…) : même chose, sans
  // rechargement. Le login garde son propre traitement ci-dessus (partage de session).
  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (!HOSTED || ev.defaultPrevented || !f || !f.action || /\/account\/login/.test(f.action)) return;
    var u; try { u = new URL(f.action, location.href); } catch (e) { return; }
    if (!softNavigable(u)) return;
    ev.preventDefault();
    var method = (f.method || "get").toUpperCase(), data = new URLSearchParams(new FormData(f));
    if (method === "GET") {
      u.search = data.toString();
      softGo(fetch(u.href, { credentials: "same-origin", cache: "no-store" }), u.href, true);
    } else {
      softGo(fetch(u.href, { method: "POST", body: data, credentials: "same-origin" }), u.href, true);
    }
  });

  // ---- la page de la personne suit celle de l'agent (mode en ligne) ----
  // L'agent travaille dans son navigateur cloud ; à chaque nouvelle page, la page de la personne passe
  // au même chemin (fetch + remplacement, sans rechargement : l'appel continue). Quand l'écran de
  // l'agent se referme, la personne est donc au même endroit (ex. « Conso et factures »).
  var syncedPath = "";
  function syncPage(url) {
    if (!HOSTED || !url) return;
    var u;
    try { u = new URL(url); } catch (e) { return; }
    if (/^\/(colette|reset|favicon)|^\/account\/(login|logout)|\.pdf$/.test(u.pathname)) return;
    var q = new URLSearchParams(u.search); q.delete("agent"); q.delete("__path");
    var target = u.pathname + (q.toString() ? "?" + q.toString() : "");
    if (target === syncedPath) return;
    var prev = syncedPath;
    syncedPath = target;
    if (target === location.pathname + location.search) return;
    // Changement de forfait validé par l'agent (dans SON navigateur) : la personne a déjà dit oui,
    // on rejoue la même validation sur sa page pour qu'elle voie le nouveau forfait.
    var offre = (/\/account\/forfait\/recap\?(?:.*&)?offre=(\w+)/.exec(prev) || [])[1];
    var req = (offre && /^\/account\/forfait\/confirmation/.test(target))
      ? fetch("/account/forfait/valider", { method: "POST", credentials: "same-origin",
                                            body: new URLSearchParams({ offre: offre }) })
      : fetch(target, { credentials: "same-origin", cache: "no-store" });
    req
      .then(function (r) { return r.text().then(function (t) { return [r, t]; }); })
      .then(function (rt) {
        if (/\/account\/login/.test(rt[0].url)) return;  // pas connectée sur sa page : on ne touche à rien
        swapPage(rt[1], rt[0].url);
        highlightDownload();
      })
      .catch(function () { /* ignore */ });
  }

  // Facture : l'agent ne télécharge pas (le fichier arriverait dans son navigateur cloud) ;
  // on montre le bouton « Télécharger » sur la page de la personne, elle clique elle-même.
  var hlBox = null, hlTarget = null, hlTimer = null;
  function highlightDownload() {
    var said = ((state.outcome && state.outcome.text) || "") + " " + lastColette();
    if (state.busy || (!/^\/account\/factures/.test(location.pathname) && !/download|t[ée]l[ée]charg/i.test(said))) return;
    var links = document.querySelectorAll("a,button");
    hlTarget = null;
    for (var i = 0; i < links.length; i++) {
      if (/download|t[ée]l[ée]charger/i.test(links[i].textContent || "")) { hlTarget = links[i]; break; }
    }
    if (!hlTarget || !root) return;
    if (!hlBox) {
      hlBox = el("div", "mark hl");
      hlBox.appendChild(el("span", null, "↓ Click here to download"));
      root.appendChild(hlBox);
    }
    try { hlTarget.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (e) { /* ignore */ }
    hlTarget.addEventListener("click", function () { if (hlBox) hlBox.style.display = "none"; }, { once: true });
    if (!hlTimer) hlTimer = setInterval(placeHighlight, 250);
    placeHighlight();
  }
  function placeHighlight() {
    if (!hlBox || !hlTarget || !hlTarget.isConnected) { if (hlBox) hlBox.style.display = "none"; return; }
    var r = hlTarget.getBoundingClientRect(), pad = 6;
    hlBox.style.left = (r.left - pad) + "px"; hlBox.style.top = (r.top - pad) + "px";
    hlBox.style.width = (r.width + 2 * pad) + "px"; hlBox.style.height = (r.height + 2 * pad) + "px";
  }

  // ---- écran de l'agent (mode en ligne) : captures du navigateur cloud de H ----
  function renderLive() {
    if (!HOSTED || !root) return;
    var show = !!shot && state.open && (state.busy || !!state.confirm) && !state.login_handoff && !state.form_handoff &&
      state.status !== "guiding" && !state.guide;
    if (!liveEl) {
      liveEl = el("div", "live");
      var bar = el("div", "livebar");
      bar.appendChild(el("i"));
      bar.appendChild(el("span", null, "Colette's screen: she's doing it for you, live"));
      liveEl.appendChild(bar);
      var box = el("div", "livebox");
      var img = el("img"); img.alt = "What Colette sees";
      img.onload = placeCursor;  // curseur posé quand la capture est affichée, pas avant
      box.appendChild(img);
      var cur = el("div", "livecur"); cur.appendChild(el("span", null, "↓ I'm clicking here"));
      box.appendChild(cur);
      liveEl.appendChild(box);
      liveEl.appendChild(el("div", "liveurl"));
      root.appendChild(liveEl);
    }
    liveEl.style.display = show ? "flex" : "none";
    if (!show) return;
    var im = liveEl.querySelector("img");
    liveEl.querySelector(".liveurl").textContent = shot.title || shot.url || "";
    if (im.getAttribute("src") !== shot.image) {
      // nouvelle capture : on cache le curseur jusqu'à ce qu'elle soit affichée (onload), sinon il
      // saute sur la nouvelle position par-dessus l'ancienne image
      liveEl.querySelector(".livecur").style.display = "none";
      im.setAttribute("src", shot.image);
    } else {
      placeCursor();
    }
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

  // ---- guide pas à pas : lecture de la page, anneau + consigne, détection du clic ----
  var PAGE_ID = Math.random().toString(36).slice(2, 10), nextCid = 1;
  var SCAN_SEL = "a[href],button,input:not([type=hidden]),select,textarea,summary,[onclick]," +
    "[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[role=radio],[role=option],[role=switch]";
  var BUTTON_INPUTS = /^(button|submit|reset|checkbox|radio|image|file)$/;

  function gVisible(e) {
    var r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    var cs = getComputedStyle(e);
    return cs.visibility !== "hidden" && cs.display !== "none" && parseFloat(cs.opacity || "1") > 0.05;
  }
  function gClean(t) { return ((t || "") + "").replace(/\s+/g, " ").trim().slice(0, 90); }
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
        t += " (selected: " + e.options[e.selectedIndex].text + ")";
      }
      return gClean(t);
    }
    t = t || e.innerText || e.title || "";
    if (!gClean(t)) { var img = e.querySelector("img[alt]"); if (img) t = img.alt; }
    return gClean(t);
  }
  window.__colette.scan = function () {
    var nodes = document.querySelectorAll(SCAN_SEL), out = [];
    for (var i = 0; i < nodes.length && out.length < 200; i++) {
      var e = nodes[i];
      if (!gVisible(e) || e.closest("[aria-hidden=true]") || e.disabled) continue;
      var text = labelOf(e), field = /^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName);
      if (!text && !field) continue;
      var cid = e.getAttribute("data-colette-id");
      if (!cid) { cid = "c" + (nextCid++); e.setAttribute("data-colette-id", cid); }
      var r = e.getBoundingClientRect();
      out.push({ id: cid, tag: e.tagName.toLowerCase(), type: e.getAttribute("role") || (field ? e.type || "" : ""),
                 text: text, inView: r.bottom > 0 && r.top < window.innerHeight });
    }
    var heads = [], hs = document.querySelectorAll("h1,h2,h3");
    for (var j = 0; j < hs.length && heads.length < 10; j++) {
      if (gVisible(hs[j]) && gClean(hs[j].innerText)) heads.push(gClean(hs[j].innerText));
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
    if (!layer) return;
    if (!g) {
      layer.className = "glayer hidden"; layer.textContent = "";
      if (guideRaf) { cancelAnimationFrame(guideRaf); guideRaf = null; }
      shownStep = null; layer.removeAttribute("data-key");
      return;
    }
    var key = g.step + "|" + g.target + "|" + g.text;  // reconstruit seulement si l'étape change
    if (layer.getAttribute("data-key") === key) { if (!guideRaf) guideRaf = requestAnimationFrame(placeGuide); return; }
    layer.setAttribute("data-key", key);
    layer.className = "glayer"; layer.textContent = "";
    var warn = g.irreversible ? " warn" : "";
    var ring = el("div", "ring" + warn); ring.id = "gring"; layer.appendChild(ring);
    var tip = el("div", "tip" + warn); tip.id = "gtip";
    tip.appendChild(el("div", "n", (g.irreversible ? "⚠️ Step " : "Step ") + g.step));
    tip.appendChild(el("div", "t", g.text));
    var next = el("button", null, "Done ➜");
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
  function placeGuide() {  // suit l'élément à chaque image (défilement, page qui se décale)
    guideRaf = null;
    if (!root || !guideHere()) return;
    var ring = root.getElementById("gring"), tip = root.getElementById("gtip");
    if (!ring || !tip) return;
    var t = guideTarget();
    var areaW = window.innerWidth - (state.open ? PANEL_W : 0), tw = 320, th = tip.offsetHeight || 140;
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

  function build() {
    host = document.createElement("colette-widget");
    host.setAttribute("aria-label", "Colette (assistant) — ignore");
    host.setAttribute("data-colette", "1");
    root = host.attachShadow({ mode: "open" });
    var style = el("style"); style.textContent = CSS; root.appendChild(style);
    var wrap = el("div", "wrap"); wrap.id = "wrap"; root.appendChild(wrap);
    var glayer = el("div", "glayer hidden"); glayer.id = "glayer"; root.appendChild(glayer);
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
    if (state.status === "paused" && (scr === "call" || scr === "working")) return ["amber", "Paused"];
    if (scr === "call") return state.status === "speaking" ? ["blue", "Colette is speaking…"] : ["blue", "I'm listening…"];
    if (scr === "working" && state.status === "guiding") return ["blue", "I'm guiding you step by step"];
    if (scr === "working") return state.status === "listening" ? ["blue", "I'm listening…"] : ["blue", "I'm browsing for you"];
    if (scr === "confirm") return ["amber", "Waiting for your approval"];
    if (scr === "failed") return ["amber", "Colette needs help"];
    if (scr === "done") return state.outcome && state.outcome.kind !== "success" ? ["blue", "Task stopped"] : ["green", "Done"];
    return ["green", "Available"];
  }

  function render() {
    if (!root) return;
    var scr = screen();
    var shown = {}; for (var f in state) if (f !== "subtitle") shown[f] = state[f];  // sous-titres mot à mot : non affichés
    var key = JSON.stringify([shown, connected]);
    renderLive();
    renderGuide();
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
      pill.setAttribute("aria-label", "Call Colette");
      pill.appendChild(avatar());
      var ph = el("span", "ph"); ph.appendChild(svg("phone")); pill.appendChild(ph);
      var t = el("span");
      t.appendChild(el("b", null, state.call || state.busy ? "Back to the call" : "Need help? Call Colette"));
      t.appendChild(el("small", null, state.busy ? "Colette is working for you" : "She does it with you, by voice"));
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
      x.setAttribute("aria-label", "Close");
      x.appendChild(svg("x"));
      x.appendChild(el("span", null, "Close"));
      x.onclick = closeFn;
      head.appendChild(x);
    }
    side.appendChild(head);

    // Barre d'appel : dit toujours la vérité sur le micro.
    if (scr !== "home") {
      var live = state.call || state.busy, paused = state.status === "paused";
      var cb = el("div", "callbar" + (!live ? " ended" : paused ? " paused" : ""));
      var l = el("span"); l.appendChild(el("i"));
      l.appendChild(document.createTextNode(!live ? "Call ended" : paused ? "On hold · mic off" : "Call in progress"));
      cb.appendChild(l);
      if (live) cb.appendChild(el("span", "tm", callClock()));
      side.appendChild(cb);
    }

    var body = el("div", "body");
    var foot = el("div", "foot");
    side.appendChild(body);
    ({ home: home, call: call, working: working, confirm: confirm, done: done, failed: failed })[scr](body, foot);
    if (HOSTED && state.login_handoff && body.firstChild) {
      var hb = el("div", "hintbox");
      hb.appendChild(svg("lock"));
      hb.appendChild(el("span", null, "Log in yourself on the page, on the left. Colette can't see what you type."));
      body.insertBefore(hb, body.firstChild);
    }
    if (HOSTED && state.form_handoff && body.firstChild) {
      var fb = el("div", "hintbox");
      fb.appendChild(svg("lock"));
      fb.appendChild(el("span", null, "Type your new details in the form on the page, on the left. Then click Done."));
      body.insertBefore(fb, body.firstChild);
      foot.insertBefore(button("", "Done ✓", collectForm), foot.firstChild);
    }
    if (HOSTED && (scr === "call" || scr === "working" || scr === "confirm")) {
      foot.insertBefore(typeBox(), foot.firstChild);  // sans micro : on peut aussi écrire à Colette
      if (hadFocus) typeForm.firstChild.focus();
    }
    if (!connected && (wantConn || busyServer)) body.appendChild(el("div", "off", busyServer
      ? "Colette is already helping other people right now. Please try again in a few minutes."
      : ws ? "Connecting to Colette…" : "Lost connection to Colette… trying again."));
    if (foot.childNodes.length) side.appendChild(foot);
  }

  // ---- 02 · ouverte ----
  function home(body) {
    body.appendChild(el("h2", null, "Hello!"));
    body.appendChild(el("p", "lead", "I do it for you, while we talk."));
    var talk = el("button", "talk");
    var halo = el("span", "halo callh"), disc = el("span", "disc calld");
    disc.appendChild(svg("phone")); halo.appendChild(disc); talk.appendChild(halo);
    talk.appendChild(el("b", null, "Call Colette"));
    talk.onclick = function () { state.call = true; render(); send({ type: "call" }); };
    body.appendChild(talk);
    var shortcuts = state.shortcuts || [];
    if (shortcuts.length) {
      body.appendChild(el("div", "sep"));
      body.appendChild(el("div", "or", "For example:"));
      var ex = el("div", "ex");
      shortcuts.forEach(function (s) {
        var c = el("button", "exb", "\u201C" + (s.ask || s.label) + "\u201D");
        c.onclick = function () { state.call = true; render(); send({ type: "shortcut", id: s.id }); };
        ex.appendChild(c);
      });
      body.appendChild(ex);
    }
    body.appendChild(guarantees());
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
      if (m.who !== prev) chat.appendChild(el("div", "who2" + (me ? " me" : ""), me ? "You" : "Colette"));
      prev = m.who;
      var b = el("div", "msg" + (me ? " me" : "") + (i === msgs.length - 1 ? " now" : ""), m.text);
      if (m.live) b.appendChild(el("span", "caret"));
      chat.appendChild(b);
    });
    body.appendChild(chat);
    var last = msgs[msgs.length - 1];
    var lis = el("div", "listen" + (paused ? " grey" : speaking ? " blue" : ""));
    lis.appendChild(wave(paused));
    lis.appendChild(el("div", null, paused ? "Paused — I'm not listening." : speaking ? "Colette is speaking…" : "I'm listening… take your time."));
    body.appendChild(lis);
    var row = el("div", "row2");
    row.appendChild(button("sec", paused ? "Resume" : "Pause", function () { send({ type: paused ? "resume" : "pause" }); }));
    row.appendChild(hangButton("Hang up", function () { state.call = false; render(); send({ type: "hangup" }); }));
    foot.appendChild(row);
    foot.appendChild(el("div", "mini", "Nothing changes without your \u201Cyes\u201D \u00B7 Say \u201Cstop\u201D at any time"));
  }

  function hangButton(label, fn) {
    var b = button("red", label, fn);
    b.insertBefore(svg("hangup"), b.firstChild);
    return b;
  }

  function guarantees() {
    var ul = el("ul", "guar");
    [["lock", "Never sees your password"],
     ["shield", "Nothing changes without your \u201Cyes\u201D"],
     ["mic", "Say \u201Cstop\u201D anytime"]].forEach(function (g) {
      var li = el("li"); li.appendChild(svg(g[0])); li.appendChild(el("span", null, g[1])); ul.appendChild(li);
    });
    return ul;
  }

  // Minuteur d'appel (local) : démarre au début de l'appel, mis à jour chaque seconde sans reconstruire.
  var callStart = 0;
  function callClock() {
    var live = state.open && (state.call || state.busy);
    if (!live) { callStart = 0; return ""; }
    if (!callStart) callStart = Date.now();
    var sec = Math.floor((Date.now() - callStart) / 1000);
    return Math.floor(sec / 60) + ":" + ("0" + (sec % 60)).slice(-2);
  }
  setInterval(function () {
    if (!root) return;
    var t = root.querySelector(".tm");
    if (t) t.textContent = callClock();
    else if (!(state.call || state.busy)) callStart = 0;
  }, 1000);

  // ---- 05 · navigue (H agit) ----
  function working(body, foot) {
    var steps = state.steps || [];
    body.appendChild(el("h2", null, state.title || "I'm taking care of your request"));
    if (steps.length) {
      var cur = 0;
      steps.forEach(function (s, i) { if (s.state === "doing") cur = i + 1; });
      var doneN = steps.filter(function (s) { return s.state === "done"; }).length;
      if (!cur) cur = Math.min(doneN + 1, steps.length);
      body.appendChild(el("div", "count", "Step " + cur + " of " + steps.length));
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
        li.appendChild(el("small", null, s.state === "done" ? "Done" : s.state === "doing" ? "In progress" : "Up next"));
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }
    var said = lastColette();
    var says = el("div", "says");
    says.appendChild(el("b", null, "Colette says: "));
    says.appendChild(document.createTextNode(state.status === "paused" ? "I'm paused. You're in control."
      : said || "You don't need to do anything. I'll let you know if I need you."));
    body.appendChild(says);
    var paused = state.status === "paused";
    var row = el("div", "row2");
    // .hold : seuls boutons cliquables pendant que H agit (simple clic).
    row.appendChild(button("sec hold", paused ? "Resume" : "Pause", function () { send({ type: paused ? "resume" : "pause" }); }));
    row.appendChild(button("red hold", "Stop", function () { send({ type: "stop" }); }));
    foot.appendChild(row);
    foot.appendChild(el("div", "mini", "Nothing changes without your \u201Cyes\u201D"));
  }

  // ---- 06 · votre accord ----
  function confirm(body, foot) {
    var c = state.confirm || {};
    body.appendChild(el("div", "tag", "Your turn"));
    body.appendChild(el("h2", null, c.title || c.text || "Shall I go ahead?"));
    var pts = c.bullets || [];
    if (pts.length) {
      var ul = el("ul", "pts");
      pts.forEach(function (p) { var li = el("li"); li.appendChild(svg("tick")); li.appendChild(el("span", null, p)); ul.appendChild(li); });
      body.appendChild(ul);
    }
    var a = el("div", "ambre"); a.appendChild(svg("mic"));
    a.appendChild(el("span", null, "Say \"yes\" or tap the button. Nothing changes without your approval."));
    body.appendChild(a);
    foot.appendChild(button("", c.yes || "Yes, I agree", function () { send({ type: "confirm", value: true }); }));
    foot.appendChild(button("sec", c.no || "No, don't change anything", function () { send({ type: "confirm", value: false }); }));
  }

  // ---- 07 · c'est fait (ou arrêté / refusé) ----
  function done(body, foot) {
    var o = state.outcome || {};
    var ok = o.kind === "success";
    var b = el("div", "badge " + (ok ? "ok" : "info"));
    b.appendChild(svg(ok ? "tick" : "info"));
    body.appendChild(b);
    body.appendChild(el("h2", "big1", o.title || (ok ? "All done!" : "Nothing was changed")));
    if (o.text) { var p = el("p", null, o.text); p.style.marginTop = "14px"; body.appendChild(p); }
    if (!ok && o.nothing_changed) body.appendChild(okPill());
    var items = o.summary || [];
    if (items.length) {
      var box = el("div", "box");
      box.appendChild(el("h3", null, "What I did for you"));
      var ol = el("ol");
      items.forEach(function (s) { ol.appendChild(el("li", null, s)); });
      box.appendChild(ol);
      body.appendChild(box);
    }
    var row = el("div", "row2");
    row.appendChild(button("sec", "New request", newSession));
    row.appendChild(hangButton("Hang up", function () { state.open = false; render(); send({ type: "later" }); }));
    foot.appendChild(row);
  }

  function okPill() {
    var g = el("div", "okpill");
    g.appendChild(svg("shield"));
    g.appendChild(el("span", null, "Nothing was changed on your account."));
    return g;
  }

  // ---- 10 · échec ----
  function failed(body, foot) {
    var o = state.outcome || {};
    var b = el("div", "badge warn"); b.appendChild(svg("warn")); body.appendChild(b);
    body.appendChild(el("h2", null, o.title || "I couldn't finish"));
    var p = el("p", null, (o.text || "The website isn't responding as expected.") + " It's not your fault.");
    p.style.marginTop = "12px";
    body.appendChild(p);
    if (o.nothing_changed) body.appendChild(okPill());
    body.appendChild(el("div", "q", "What would you like to do?"));
    var rows = el("div", "rows");
    rows.appendChild(rowButton("Talk to an advisor", function () { send({ type: "advisor" }); }));
    rows.appendChild(rowButton("Try once more", function () { send({ type: "retry" }); }));
    body.appendChild(rows);
    foot.appendChild(button("sec", "Leave it for later", function () { state.open = false; render(); send({ type: "later" }); }));
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
      markBox.appendChild(el("span", null, "↓ I'm clicking here"));
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

  // « Nouvelle demande » : on ferme la session (le serveur arrête tout, agent compris) et on en ouvre
  // une neuve, puis l'appel reprend tout seul. Plus d'état résiduel d'une démarche à l'autre.
  var restartCall = false;
  function newSession() {
    restartCall = true;
    shot = null; syncedPath = ""; lastShare = 0;
    if (hlBox) hlBox.style.display = "none";
    state = { open: true, status: "idle", steps: [], subtitle: "", confirm: null, call: true, transcript: [] };
    render();
    if (hasBinding()) {  // local (CDP) : pas de WebSocket, le serveur remet tout à zéro et l'appel reprend
      restartCall = false;
      send({ type: "new_session" }); send({ type: "open" }); send({ type: "call" });
      return;
    }
    if (ws) { try { ws.close(); } catch (e) { /* ignore */ } } else connect();
  }

  function connect() {
    if (hasBinding()) {  // canal local CDP disponible : jamais de WebSocket (bloqué depuis free.fr)
      if (ws) { try { ws.onclose = null; ws.close(); } catch (e) { /* ignore */ } ws = null; }
      send({ type: "hello" });
      return;
    }
    try { ws = new WebSocket(WS_URL); } catch (e) { setTimeout(connect, 1000); return; }
    ws.binaryType = "arraybuffer";
    ws.onopen = function () {
      connected = true; busyServer = false; render();
      var queued = pendingMsgs; pendingMsgs = [];
      for (var qi = 0; qi < queued.length; qi++) send(queued[qi]);
      if (restartCall) {
        restartCall = false;
        send({ type: "open" }); send({ type: "call" });
      }
    };
    ws.onmessage = function (ev) {
      if (typeof ev.data !== "string") { playPcm(ev.data); return; }
      try {
        var msg = JSON.parse(ev.data);
        if (msg.type === "state" && msg.state) {
          var prev = state;
          state = msg.state;
          if (HOSTED && state.login_handoff && !prev.login_handoff) tryHandoff(false);  // déjà connectée ?
          if (HOSTED && state.login_check && state.login_check !== prev.login_check) tryHandoff(true);
          if (HOSTED && state.form_check && state.form_check !== prev.form_check) collectForm();
          if (HOSTED && state.form_handoff && !prev.form_handoff) focusForm();
          if (HOSTED && prev.busy && !state.busy) replayForm();
          if (HOSTED && prev.busy && !state.busy) setTimeout(highlightDownload, 300);  // fin de démarche
          render();
        } else if (msg.type === "scan") {  // guide pas à pas : le backend lit la page de la personne
          var page = null;
          try { page = window.__colette.scan(); } catch (e) { /* ignore */ }
          send({ type: "scan_result", id: msg.id, page: page });
        } else if (msg.type === "screen") { shot = msg; renderLive(); syncPage(msg.url); }
        else if (msg.type === "busy") { busyServer = true; }
      } catch (e) { /* ignore */ }
    };
    ws.onclose = function () {
      ws = null;
      if (hasBinding()) { send({ type: "hello" }); return; }  // le canal local a pris le relais
      connected = false; render();
      if (!wantConn && !restartCall) return;  // session rendue volontairement : on se reconnectera au prochain geste
      setTimeout(function () { if (!ws) connect(); }, busyServer ? 15000 : restartCall ? 300 : (HOSTED ? 2000 : 1000));
    };
    ws.onerror = function () { /* onclose suit */ };
  }

  window.__colette.newSession = function () { newSession(); };
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
    else if (!HOSTED) {
      // le canal CDP peut arriver un peu après le script : on l'attend avant de tenter le WebSocket
      var tries = 0, wait = setInterval(function () {
        if (hasBinding()) { clearInterval(wait); send({ type: "hello" }); }
        else if (++tries >= 15) { clearInterval(wait); connect(); }
      }, 100);
    }
    setInterval(mount, 1000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
