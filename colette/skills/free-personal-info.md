---
name: free-personal-info
description: Use when the person wants to change their contact email address or postal address (coordonnées, infos personnelles) in the Free Mobile customer area.
label: My details
ask: I'd like to see or change my contact details.
keywords: details | address | email | e-mail | contact | coordonnées
steps: Open your customer area | Log in | Open your personal details | Edit your details | Confirm with your approval
steps_view: Open your customer area | Log in | Open your personal details | Read your details
order: 3
---
# Change personal details (coordonnées) in the Free Mobile customer area

Only two details are covered: the contact email address and the postal address.
If the person only wants to SEE their current details (voir, consulter, récupérer…), open
"Mes infos personnelles", read the requested detail and give it in your answer. Change nothing,
click no "Modifier" button.
The person TYPES the new values herself in the form: never ask for them aloud, never type them from
what she said. Click the field, then call `ask_user` with exactly "Please type your new <address / email
address> yourself in the form, then say done." and read what she typed. Never invent or complete a value.

## Where
- https://mobile.free.fr/account/ → "Mon compte" → "Mes infos personnelles"
  (also written "Mes informations personnelles").
- If a login, a password or a text-message code is requested, call `ask_user` so the
  person types it herself, then wait. Never type an identifier, password or code yourself.
- If the page asks to choose a line ("Choisir une ligne"), choose the main line; if unsure, call `ask_user`.

## Change the contact email
1. Click "Modifier" next to "Mon adresse email".
2. Click the new-address field and call `ask_user`: "Please type your new email address yourself in the
   form, then say done." Then read the address she typed, letter by letter.
3. When the page asks to confirm the password: call `ask_user` so the person types it
   herself, then wait.
4. Call `confirm_change` with a short French summary such as:
   "remplacer l'adresse email <ancienne> par <nouvelle>".
5. Only if the reply says the user approved: click "Modifier mon adresse email".
   If the user refused: do not click it, and answer that the change was cancelled.
6. Answer with what the page shows after saving.

## Change the postal address
1. In "Mon adresse postale", click "Modifier".
2. Click the "Code postal" field and call `ask_user`: "Please type your new address yourself in the
   form, then say done." Help only if she asks. Then read every field she filled.
   Fill the form in its order: "Code postal" (type it), "Ville" (list), "Type de voie" (list: RUE,
   PLACE, AVENUE, BOULEVARD…), "Nom de voie" (long list written "NAME (TYPE)", e.g.
   "REPUBLIQUE (PLACE DE LA)"). Every list accepts typing: click it, type the first 3 letters
   (e.g. "REP" for République, "PLA" for PLACE) or the digits of a number, then click the match;
   scroll the list itself only if typing does nothing),
   then the street number. Check each field.
3. When the page asks to re-enter the password: call `ask_user` so the person types it
   herself, then wait.
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

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
