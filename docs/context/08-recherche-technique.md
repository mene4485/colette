# 08 — Recherche technique (sam. 7 nov, matin)

## H Agents API
- Docs LLM : https://hub.hcompany.ai/llms.txt · SDK `pip install hai-agents` (v1.4.3) · clé : https://platform.hcompany.ai/settings/api-keys (`HAI_API_KEY`)
- Agent : `h/web-surfer-flash` (le plus rapide). `start_url` via `overrides={"agent.environments[kind=web].start_url": ...}`.
- `AsyncClient.start_session(...)` → handle ; `session.stream()` = long-poll des events (pas de SSE).
  - `policy_event` : `content` (message de l'agent → narration), `tool_reqs` (actions)
  - `observation_event` : `image.source` (screenshot, nécessite la clé → proxy backend), `metadata.url`
  - `LiveViewUrlEvent.data.live_view_url` (iframe ? non documenté) · `share_session()` = lien public
- **Human-in-the-loop = custom tool Python** (ex. `ask_user(question) -> str`) : l'agent attend le retour. https://hub.hcompany.ai/agents-api/custom-tools.md
- `send_message`, `pause/resume`, `cancel()` (→ `interrupted`).
- Même navigateur entre 2 phases : `idle_timeout_s=600`, puis `send_message("clique sur Confirmer")`.
- Profils persistants (`browser_profile_id` + `persist_browser_profile`). Vaults : mot de passe tapé hors contexte LLM (`fill_secret_at`).
- Plan Free : 60M tokens, 3 sessions concurrentes. Latence/step non documentée → à mesurer.
- Repos : https://github.com/hcompai/agents-api-demos

## Free
- **Résiliation pas faisable en ligne** (3244 + recommandé) → abandonnée.
- Démo retenue : **Free Mobile « Changer de forfait »** (~5 écrans), stop sur le récap avant validation.
- Login Free Mobile : identifiant 8 chiffres + mdp + **2FA SMS obligatoire** ; case « se souvenir de l'appareil ».
- Pas d'anti-bot détecté. Pas de compte de test → vraie ligne d'un membre.
- Idée : mdp via vault H, **code SMS dicté oralement** via le tool `ask_user` (cohérent avec le pitch).

## Voix (Pipecat 1.15.0)
- `pip install "pipecat-ai[gladia,daily,cartesia,openai,webrtc,runner]"` — 1.x : `PipelineWorker`, `settings=Service.Settings(...)`.
- Gladia : `GladiaSTTService(settings=...Settings(model="solaria-1", language_config=LanguageConfig(languages=["fr"])))`
- Tool long : async function call, `cancel_on_interruption=False`, `timeout_secs=600`, updates via
  `result_callback(..., properties=FunctionCallResultProperties(is_final=False))`.
  Exemple : https://github.com/pipecat-ai/pipecat/blob/main/examples/function-calling/function-calling-openai-async-stream.py
- Front : RTVI (`RTVIServerMessageFrame` → `RTVIEvent.ServerMessage` ; `sendClientMessage("stop")` → `on_client_message`).
- Client le plus rapide : SmallWebRTC + Voice UI Kit (`python bot.py -t webrtc`, localhost:7860).
- TTS FR : Cartesia `sonic-3.6` (`language=Language.FR`) ou ElevenLabs `eleven_flash_v2_5`.
- Téléphone : numéro FR impossible en 24h (Twilio = dossier réglementaire, Daily = US/CA only).
  → Bouton web = chemin principal ; numéro US Daily = bonus.

## ⭐ Agent H dans le navigateur de l'utilisateur (`host: user_device`)
Source : https://hub.hcompany.ai/agents-api/your-browser
- Agents API, environnement `{"kind": "web", "host": "user_device"}` → l'agent pilote le **Chrome local** (remote debugging :9222).
- `pip install "hai-agents[cli,browser]"`. Le SDK lance Chrome avec un profil dédié `~/.hai/chrome-profile`, **persistant** :
  on se connecte une fois soi-même, l'agent retrouve la session ensuite.
- Events / `send_message` / pause / cancel identiques au cloud. Stop global : `holo local stop`.
- Limites : 1 navigateur par process Python ; si le process meurt, la session est annulée (Chrome reste ouvert).
  Vaults / profils cloud / proxy non applicables (inutile : ce sont les logins du Chrome local).
- → Résout : identifiants (l'utilisateur tape lui-même, jamais via la voix ni le LLM), reprise en main (pause), stop.
