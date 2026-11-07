# 05 — Architecture cible (proposition, à valider par la recherche)

## Principe
Réutiliser le pipeline voix **Pipecat + Daily.co** que Menelik a déjà. L'agent H n'est qu'un **tool**
que le bot vocal appelle. Deux boucles distinctes :
- boucle conversationnelle (temps réel, voix) → Pipecat ;
- boucle d'exécution (lente, navigateur) → H Agents API, en tâche de fond.

```
Téléphone (Daily dial-in)      ┐
   ou bouton WebRTC sur le site ┘──► Daily room ──► Pipecat bot
                                                     ├─ STT : Gladia (service Pipecat natif)  ← sponsor track
                                                     ├─ LLM : function calling (ex. run_demarche, confirm, stop)
                                                     ├─ TTS : ElevenLabs / Cartesia (voix FR naturelle)
                                                     └─ tool run_demarche(site, tâche, infos)
                                                            └─► H Agents API (session navigateur)
                                                                  ├─ events de progression ──► TTS (narration)
                                                                  └─ events de progression ──► page web (barre d'étapes)
                                                                       via Daily app messages / RTVI
```

## Points clés
1. **H en background, jamais en appel bloquant.** Lancer la session H dans une `asyncio.Task`, pousser des
   `TextFrame` dans le pipeline à chaque étape ("Je suis sur votre espace client, je cherche la rubrique abonnement…").
   Sinon le bot se tait 30 s et le jury décroche.
2. **Confirmation orale avant action irréversible.** À vérifier dans les docs H :
   - Option A : l'API supporte une pause / "ask user" / human-in-the-loop → l'utiliser.
   - Option B : découper en deux runs : "va jusqu'à la page de confirmation et arrête-toi" → question au téléphone →
     "clique sur confirmer". Vérifier si la session navigateur persiste entre deux runs ; sinon le 2e run refait
     le chemin (acceptable en démo, mais plus lent).
3. **Barre de progression à l'écran** : `transport.send_app_message()` (ou RTVI) du bot vers la page.
   Donne le critère "UX & user control" presque gratuitement. Ajouter un bouton **Stop** qui annule la task H
   + un mot vocal "stop".
4. **Identifiants** : jamais dictés. Session Free pré-authentifiée (profil navigateur / cookies côté H)
   ou compte de test. À vérifier : comment H gère les environnements / profils persistants.
5. **Téléphonie** : Daily fait du dial-in PSTN (numéro + config). Si trop long → bouton WebRTC sur la page
   (Pipecat client JS ou Daily prebuilt). Raconter le téléphone comme étape suivante.
6. **Latence** : mesurer dès samedi matin la durée d'un run H complet sur Free. Adapter le script vocal pour meubler.

## Questions à résoudre par la recherche (docs H en priorité)
- Modèle d'exécution de l'API H : run synchrone vs session streamée ? Webhooks / SSE pour les étapes ?
- Peut-on injecter une instruction en cours de run (ex. "voici le numéro de ligne") ?
- Pause / reprise / human-in-the-loop natif ?
- Persistance du navigateur / des cookies entre runs ? Environnements ?
- Accès à l'écran live (screenshots / replay) pour l'afficher au jury pendant la démo ?
- Pipecat : version actuelle du service Gladia STT, config FR, VAD recommandé.
- Daily : dial-in PSTN FR — délai d'obtention d'un numéro, coût, config Pipecat.
- TTS FR de qualité avec faible latence (ElevenLabs Flash vs Cartesia) — lequel est déjà dans le pipeline existant ?

## Intégration des autres partenaires (minimal, pour la doc/code)
- **Linkup** : étape optionnelle "trouver la procédure officielle de résiliation Free" ou "comparer les forfaits"
  avant de lancer H. Une fonction, un appel API, un log.
- **Stripe** : module `billing/` ou mention README : souscription Colette (B2B2C, l'opérateur paie) et/ou
  cartes virtuelles à usage unique pour les souscriptions. Pas de démo.
- **Devin** : utilisé pour paralléliser (ex. page front barre d'étapes). Mentionner dans README si utilisé.
