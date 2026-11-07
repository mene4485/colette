---
name: demo-personal-info
description: Use when the person wants to see or change their postal address, contact email or contact phone (coordonnées, informations personnelles) on the Free Mobile demo customer area.
label: Mes coordonnées
ask: Je voudrais voir ou modifier mes coordonnées.
keywords: coordonnées | coordonnees | adresse | e-mail | email | mail | téléphone | informations personnelles
steps: Ouvrir votre espace abonné | Vous connecter | Ouvrir vos informations | Modifier vos coordonnées | Valider avec votre accord
steps_view: Ouvrir votre espace abonné | Vous connecter | Ouvrir vos informations | Lire vos coordonnées
order: 3
---
# See or change personal details (coordonnées) — demo customer area

If the person only wants to SEE a detail, open "Mes informations", read it and answer. Change nothing.
New values come from the task. If a piece is missing, ask only for it with `ask_user`, one short
question at a time (number and street, then postal code, then city), keeping what was already said.
Never invent a value.

## Where
- Left menu "Mes informations" → section "Mes coordonnées" → button "Modifier mes coordonnées".
- The form has plain text fields: "Adresse (numéro et rue)", "Code postal", "Ville",
  "Adresse e-mail", "Téléphone de contact". Only change the fields the person asked for.

## Steps
1. Open "Mes informations" and write down the current value of the detail to change.
2. Click "Modifier mes coordonnées".
3. For each field to change: click it, select all its text and replace it with the new value. Check it.
4. Call `confirm_change` with a short French summary, e.g.
   "remplacer l'adresse 12 rue des Lilas, 75020 Paris par 3 place de la République, 75003 Paris".
5. Only if the reply starts with "Approved": click "Enregistrer les modifications".
   If refused: click "Annuler" and answer that nothing was changed.
6. If the page shows a red error, fix that field (ask the person if needed) and try again.
7. Answer with what the page shows ("Vos coordonnées ont bien été modifiées.").

## Never
- Never change the holder name, the password, the plan or the options.
- Never click "Enregistrer les modifications" before `confirm_change` replied "Approved".
