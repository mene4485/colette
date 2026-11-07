# 03 — Partenaires, règles, logistique

## Règles officielles
- Équipes de 1 à 4. ~800 candidatures, participants sélectionnés.
- Slide du kickoff : "utiliser au moins 4 des 5 technologies partenaires" (H Company, Gladia, Linkup, Stripe, Devin).
- **Clarification obtenue oralement auprès de l'organisateur (samedi matin)** : ce n'est pas strict.
  - H Company + Gladia : sûrs.
  - Au moins Linkup **ou** Stripe en plus. Stripe peut simplement figurer dans le code et la doc
    (ex. paywall / business model), sans démo. Devin compte s'il sert au développement.
  - "Développez votre truc, ne stressez pas."
- **Soumission : dimanche 8 nov, 14h00.** Schedule et critères sur Luma et Builder Base.
- Sponsor prizes : Best Use of Gladia (1 000 €), Best Use of Devin (1 000 €), Best LinkedIn post (500 €), Best X post (500 €).
- Prix principaux : 5 000 / 3 000 / 2 000 € par équipe.

## H Company (cœur du projet)
- Agents computer-use : voient l'écran, cliquent, remplissent des formulaires. Marche même sans API côté site.
- Setup : redeem credits via Builder Base → docs (LLM-optimized, à donner directement à Claude Code) → API key
  → créer un agent via la plateforme (UI) ou le SDK (Python + TypeScript).
- Plateforme : replay des sessions (pause, étape par étape), gestion des agents, environnements, dossiers.
- Repo GitHub de démos à forker (point de départ possible).
- Mentors H sur place (t-shirts) + Discord H Company (channels par partenaire).
- Test déjà fait par Menelik avec l'extension HoloTab sur free.fr : l'agent a navigué seul et trouvé les 3 offres 5G.
  Il n'a pas pu entrer le mot de passe (volontairement). → Free ne semble pas bloquer le computer use.

## Gladia (sponsor track)
- Plateforme voix, connue pour le speech-to-text (STT) temps réel.
- Nouvelle plateforme end-to-end (STT + TTS temps réel + diarization + NER + fine-tuning) sort le **1er décembre** :
  **on doit utiliser le stack actuel**.
- Pipecat a un service Gladia STT natif → chemin le plus rapide.

## Linkup
- API de recherche web pour agents, retourne du JSON structuré. Compte gratuit + codes promo.
- Fort pour "va chercher une info sur le web", pas pour naviguer un site.
- Usage possible chez nous : comparer les forfaits (Free vs Orange…) ou trouver la bonne page/procédure
  de résiliation avant de lancer l'agent H. Suffit de l'intégrer dans le code.

## Stripe
- Pas de représentant sur place. Crédits de participation après le hackathon + prix pour les gagnants.
- Idée notée : cartes virtuelles à usage unique avec plafond (Issuing) pour souscrire sans exposer sa vraie carte.
- Pour nous : à mentionner dans le code/README comme brique "souscription" / business model. Pas de démo.

## Cognition / Devin
- Agent de code autonome, VM dédiée (macOS/Windows/Linux), model-agnostic, parallélisable. Plan max 200 $ offert 1 mois.
- Accès via le Discord H Company, channel "Cognition Help". Team plan multiplayer sur demande.
- Pour nous : optionnel, utilisable pour paralléliser du dev (ex. front de la barre de progression).

## Morning
- 1 mois gratuit de coworking pour les 3 équipes du podium ; 50 % sur 2 mois pour tous. Pas une techno.

## Logistique
- Lieu : La Maison by Motier Ventures, Paris. Samedi : hack dès 10h30, repas 12h30 / 19h, fermeture 21h.
  Dimanche : réouverture 8h, soumission 14h, judging 14h30, pitches finaux 15h45, résultats 17h45.
- Équipe créée sur Builder Base sous le nom **Colette**.
