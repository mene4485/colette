# Colette — maquettes UI (Figma) et écarts décidés

Captures : `docs/design/*.png`. Le widget (`colette/static/widget.js`) doit y ressembler au maximum.
Style : carte blanche arrondie, ombre douce, bleu `#2155D3`-ish, gros texte, avatar « mamie à lunettes »,
en-tête « Colette · <statut coloré> » + bouton « ✕ Fermer ».

| # | Écran | Statut affiché | Contenu | Actions |
|---|---|---|---|---|
| 1 | Fermée | — | Pastille bas-droite : avatar + « Parler à Colette / Votre assistante » | Clic → ouvre (2) |
| 2 | Ouverte | ● vert « Disponible » | « Bonjour Marie, je suis Colette. Que voulez-vous faire ? » | **Un seul geste principal** : gros bouton « 🎤 Appuyer pour parler » (démarre l'appel). Dessous, en plus petit : raccourcis (Télécharger une facture · Changer d'abonnement · Modifier mes coordonnées). **Pas de champ texte.** |
| 3 | Écoute (appel en cours) | ● bleu « Je vous écoute » | Micro animé + onde, « Je vous écoute… », « Parlez normalement, prenez votre temps. », bloc « Vous dites : « … » » (transcription en direct) | **Conversation continue** (pas de « J'ai fini de parler ») : seulement « ⏸ Pause » et « Raccrocher » |
| 5 | Navigue | ● bleu « Je navigue pour vous » | Titre « Je <action> », « Étape 2 sur 4 » + barre, liste d'étapes Fait / En cours / À venir, « Vous n'avez rien à faire. Je vous préviens si j'ai besoin de vous. » Sur la page : bandeau bleu « 👁 Colette utilise cette page pour vous. Vous pouvez regarder. » | « Arrêter Colette » (+ Pause) |
| 6 | Accord | ● ambre « Attend votre accord » | Encadré « ⚠ J'ai besoin de votre accord », question en titre, 2–3 puces (prix / date / réversible), « Rien ne change sans votre accord. » | « Oui, <verbe> » / « Non, <garder…> » (+ oui/non à la voix) |
| 7 | Terminé | ● vert « Terminé » | ✓ vert, « C'est fait ! », phrase de résultat, encadré « Ce que j'ai fait pour vous » (liste numérotée) | « Écouter ce résumé » / « Faire autre chose » |
| 10 | Échec | ● ambre « Colette a besoin d'aide » | ⚠, « Je n'ai pas pu terminer », raison simple + « Ce n'est pas de votre faute. », pastille verte « Rien n'a été modifié sur votre compte » (seulement si aucune action confirmée n'a eu lieu) | « Montrez-moi où cliquer » · « Parler à un conseiller » · « Réessayer une fois » · « Laisser pour plus tard » |

## Écarts par rapport au Figma (décidés)
- Écran 2 : un seul geste principal (gros « Appuyer pour parler »), raccourcis plus petits dessous, champ texte supprimé.
- Écran 3 : discussion continue tout du long ; seulement Pause et Raccrocher.
- Raccourci « Résilier mon forfait » retiré : la résiliation Free Mobile n'est pas faisable en ligne (3244 + courrier).
  Raccourcis = les skills disponibles (`colette/skills/*.md`).
- Placement : la carte reste **ancrée à droite, page rétrécie** (comportement actuel) et **sans voile sombre** pendant
  que H agit — sinon H voit une page grisée / masquée. Voile léger acceptable seulement aux écrans 2, 3, 6, 7, 10.
- Les raccourcis envoient un message `{"type": "shortcut", "id": "<skill>"}` → même chemin qu'une demande orale.
