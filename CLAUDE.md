# Colette — contexte projet (hackathon H Company × 42AI, Paris, 7–8 nov 2026)

Tu travailles avec Menelik sur **Colette**, un agent vocal qui réalise des démarches en ligne
à la place de personnes âgées / malvoyantes, en dialoguant avec elles au téléphone.
Lis `docs/context/*.md` avant toute proposition. Ils sont la source de vérité.

## Contrainte absolue
- **Deadline de soumission : dimanche 8 nov, 14h00 (Paris).** Nous sommes samedi matin.
- Pitch + démo live devant jury à 15h45 dimanche, puis Q&A.
- Un MVP qui marche en démo > une archi propre. Toute décision se juge à l'aune de
  "est-ce que ça augmente la probabilité d'une démo réussie dimanche 14h ?".

## Ce qu'on construit (résumé)
Scénario démo : une personne âgée n'arrive pas à gérer son abonnement Free en ligne.
Elle appelle un numéro (ou clique un bouton vocal sur le site). L'agent :
1. comprend la demande à l'oral,
2. ouvre le site et navigue (agent computer-use H Company),
3. décrit à voix haute chaque étape,
4. demande les infos manquantes à l'oral,
5. **s'arrête et demande une confirmation orale explicite avant toute action irréversible**,
6. résume ce qui a été fait.
Le jury voit en même temps : l'appel, l'écran de l'agent, une barre de progression par étapes.

## Stack imposée / choisie
- **H Company Agents API** (computer use) — obligatoire, cœur du projet. Docs LLM-optimized dispo.
- **Gladia** (speech-to-text) — sponsor track "Best Use of Gladia" (1 000 €). Ancien stack uniquement
  (la nouvelle plateforme sort le 1er déc).
- **Pipecat + Daily.co** — Menelik a déjà un pipeline voix fonctionnel avec une room Daily. À réutiliser
  **si tu juges que c'est pertinent** : compare avec les alternatives (ex. Gladia direct, Vapi, Twilio, LiveKit)
  et recommande, en tenant compte du temps restant et du code déjà existant.
- Linkup (web search API) et/ou Stripe : au moins un des deux doit apparaître dans le code/doc.
  Pas besoin de le démontrer. Voir `docs/context/03-partenaires-et-regles.md`.
- Devin (Cognition) : compte si utilisé pour coder. Optionnel.

## Critères de jugement (pondérés) — optimiser dans cet ordre
1. Use of Computer Use — 25 %
2. Technical execution & reliability (end to end, sans hand-holding) — 25 %
3. Usefulness & impact — 20 %
4. Originality — 15 %
5. UX & user control (l'utilisateur peut superviser / stopper) — 10 %
6. Demo clarity & Q&A — 5 %

## Comment travailler avec moi
- **Avant tout plan : pose-moi tes questions** (AskUserQuestion). Ne devine pas.
- Fais des recherches **précises et récentes** (docs H, Pipecat, Gladia, Daily) avant de proposer
  une architecture. Cite les URLs. Lance des subagents en parallèle si plusieurs sujets.
- Compare 2–3 options max, avec un verdict clair en fonction du contexte ci-dessus (temps, critères, stack existant).
- Plan par étapes ordonnées (pas d'horaires), de la plus risquée à la moins risquée :
  faisabilité H sur Free → voix ↔ H connectés → confirmation + stop → affichage progression → README + vidéo de secours.
- Réponses courtes et scannables. Menelik préfère moins de texte.
- Code : Python (Pipecat), TypeScript si nécessaire pour le front. Commit souvent.
- Toujours prévoir un **fallback démo** (vidéo enregistrée, ou site de test maquette) si Free bloque les bots.

## Équipe
- Menelik (toi) : agent H + intégration voix. Lead tech.
- Oleksander : scripts, config agent, tech.
- Mialy : UX, interface, pitch, réponses aux questions du jury.
- Nour : UX + pitch, aide sur connexions Twilio/Gladia/Daily.

## Fichiers de contexte
- `docs/context/01-projet-colette.md` — vision, problème, chiffres, scénario démo
- `docs/context/02-criteres-jugement.md` — grille du jury
- `docs/context/03-partenaires-et-regles.md` — règles, sponsors, ce qui compte vraiment
- `docs/context/04-decisions-equipe.md` — tout ce qui a été décidé / écarté et pourquoi
- `docs/context/05-architecture-cible.md` — archi proposée Pipecat + Daily + H, points à vérifier
- `docs/context/06-planning-et-risques.md` — timeline du week-end, risques, fallbacks
- `docs/context/07-pitch-notes.md` — arguments pour le pitch et les Q&A
