# 04 — Décisions de l'équipe (et ce qui a été écarté)

## Décidé
1. **Projet : Colette** — agent vocal qui réalise des démarches en ligne pour personnes âgées / malvoyantes.
   Nom de l'équipe et du produit : Colette.
2. **Démo : une seule démarche, courte mais pénible**, de bout en bout. Cas retenu : **Free, résiliation d'abonnement**
   (ou autre cas Free intéressant si la résiliation s'avère trop longue / irréversible à démontrer).
3. **Priorité à un MVP qui marche. L'UX s'améliore ensuite.**
4. **Point d'étape à midi samedi** : évaluer ce qui marche, décider de réduire les ambitions ou de pivoter.
5. Première tâche tech : coder un agent H qui prend en entrée (site, demande) et mène la démarche jusqu'au bout.
6. L'utilisateur garde le contrôle : narration vocale de chaque étape, affichage visuel de la progression par étapes,
   confirmation orale avant toute action importante/irréversible.
7. Les mots de passe ne sont jamais dictés à l'agent (solution à définir : session pré-authentifiée, profil navigateur…).
8. Cible principale : personnes âgées, **plutôt sur ordinateur que smartphone**.
9. Stripe : présenté comme intégré "pour le cas où l'utilisateur souscrit un abonnement" ; pas démontré.

## Encore ouvert
- **Canal vocal** : appel téléphonique (Daily dial-in / Twilio / Vapi) vs bouton vocal sur le site (WebRTC).
  Les deux sont acceptables pour le jury. Préférence Menelik : l'appel (plus impressionnant, matche le pitch).
  Fallback : bouton sur la page.
- **Forme du produit** : extension Chrome (proposée par Nour/Mialy : s'intègre aux routines rassurantes des seniors,
  "comme l'outil de traduction, toujours là") vs page web dédiée. Personne n'a déjà fait d'extension Chrome →
  risque. Pour la démo, une page web avec bouton + barre de progression suffit ; l'extension est une vision produit.
- Comment l'agent "connaît" l'utilisateur avant d'arriver sur le site (profil, infos à demander au fil de l'eau).
- Historique des démarches / rappel par l'agent : **idée pour plus tard, pas pour le hackathon.**

## Écarté (et pourquoi)
- Agent qui fait les courses en ligne pour malvoyants (Nour) : même population, mais l'impact administratif
  est jugé plus fort et plus universel.
- Billets de train / loisirs les moins chers avec plafond de paiement (Mialy) : bon use case Linkup + Stripe,
  mais exploré samedi matin puis abandonné : seniors en EHPAD/famille déjà accompagnés pour les loisirs,
  et la contrainte "4 partenaires" s'est révélée non stricte → retour à l'idée de base.
- Démarches impôts/CAF/retraite : trop longues ou impossibles à démontrer en live (impôts hors période,
  retraite = reconstitution de carrière).

## Répartition
- **Menelik** : construire l'agent H + intégration voix (lead tech).
- **Oleksander** : scripts, configuration de l'agent, tech.
- **Mialy** : UX / interface simple et intuitive, pitch, préparation des réponses au jury, marché.
- **Nour** : UX + pitch, connexions Twilio/Gladia/Daily, à cheval tech/produit.
- Tout le monde veut apprendre des deux côtés ; pas de silos stricts.

## Arguments / anecdotes retenus pour le pitch
- Xavier Niel dirige l'école 42 (co-organisatrice) **et** Free → clin d'œil : "il sera obligé d'intégrer Colette".
- Persona : "Géraldine n'arrivait pas à résilier son abonnement Free…" → avant / après.
- Marché secondaire : tous ceux qui n'ont pas le temps ou la patience pour un formulaire en ligne.
