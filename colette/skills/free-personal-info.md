---
name: free-personal-info
description: Use when the person wants to change their contact email address or postal address (coordonnées, infos personnelles) in the Free Mobile customer area.
label: Modifier mes coordonnées
keywords: coordonnées | coordonnees | adresse | e-mail | email | mail | informations personnelles
steps: Ouvrir votre espace abonné | Vous connecter | Ouvrir vos informations personnelles | Modifier vos coordonnées | Valider avec votre accord
steps_view: Ouvrir votre espace abonné | Vous connecter | Ouvrir vos informations personnelles | Lire vos coordonnées
order: 3
---
# Change personal details (coordonnées) in the Free Mobile customer area

Only two details are covered: the contact email address and the postal address.
If the person only wants to SEE their current details (voir, consulter, récupérer…), open
"Mes infos personnelles", read the requested detail and give it in your answer. Change nothing,
click no "Modifier" button.
The new values come from the user's task. If the task does not give the complete new value, call
`ask_user` to get it. Never invent or complete a value yourself.

## Where
- https://mobile.free.fr/account/ → "Mon compte" → "Mes infos personnelles"
  (also written "Mes informations personnelles").
- Si une connexion, un mot de passe ou un code SMS est demandé, appelle `ask_user` pour que la
  personne le tape elle-même, puis attends. Never type an identifier, password or code yourself.
- If the page asks to choose a line ("Choisir une ligne"), choose the main line; if unsure, call `ask_user`.

## Change the contact email
1. Click "Modifier" next to "Mon adresse email".
2. Type the new email address into the new-address field. Check it letter by letter.
3. When the page asks to confirm the password: appelle `ask_user` pour que la personne le tape
   elle-même, puis attends.
4. Call `confirm_change` with a short French summary such as:
   "remplacer l'adresse email <ancienne> par <nouvelle>".
5. Only if the reply says the user approved: click "Modifier mon adresse email".
   If the user refused: do not click it, and answer that the change was cancelled.
6. Answer with what the page shows after saving.

## Change the postal address
1. In "Mon adresse postale", click "Modifier".
2. Type the new address into the matching fields (street, postal code, city...). Check each field.
3. When the page asks to re-enter the password: appelle `ask_user` pour que la personne le tape
   elle-même, puis attends.
4. Call `confirm_change` with a summary such as: "remplacer l'adresse postale <ancienne> par <nouvelle>".
5. Only if the user approved: click "Enregistrer". If refused: do not click it, answer that the change was cancelled.
6. Free then sends a letter with a verification code ("code de vérification") to the new address.
   The change is not finished until that code is entered. Answer with what the page shows, and say that
   the code from the letter is still needed.

## Finish a postal address change (code from Free's letter)
- Only when the person gives the verification code: open "Mes infos personnelles", find the field
  for the verification code, type the code, call `confirm_change`
  ("saisir le code de vérification reçu par courrier"), and validate only if approved.

## Never (in this task)
- Never change anything other than the contact email or the postal address: not the password, not the
  bank details (RIB), not the plan, not the options, not the phone line.
- Never click buttons to pay, cancel, change plan, subscribe, order or delete.
- Never click a save, "Modifier …" or "Enregistrer" button before `confirm_change` replied that the user approved.
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
