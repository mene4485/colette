# Change the contact email address — demo site

The new email address comes from the user's task. If the task does not give a complete address
(name, "@", domain), stop and answer that the address is missing or incomplete.
Never invent or complete a value yourself.

## Where
- http://localhost:8000/account/ → left menu "Mes informations" → "Modifier mes coordonnées"
  (direct page: http://localhost:8000/account/infos/modifier).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. On "Mes informations", write down the current "Adresse e-mail".
3. Click "Modifier mes coordonnées". The form is already filled with the current values.
4. Clear "Adresse e-mail" and type the new address from the task. Check it letter by letter
   (dots, dashes, "@", domain). Leave every other field exactly as it is.
5. Call `confirm_change` with `costs_money` = false and a summary in this form:
   "Contact email: <old address> → <new address>."
6. Only if the reply says the user approved: click "Enregistrer les modifications".
   If the user refused: click "Annuler" and answer that the change was cancelled.
7. Check the result:
   - "Vos coordonnées ont bien été modifiées.": answer with the new address shown under "Adresse e-mail".
   - "L'adresse e-mail n'est pas valide.": do not guess a fix. Stop and answer with the message.

## Never (in this task)
- Never change the postal address, the contact phone, the holder ("Titulaire") or the password.
- Never click "Enregistrer les modifications" before `confirm_change` replied that the user approved.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## If something is not as described
- The demo site sends no confirmation email and does not ask for the password. If a page asks for a
  password or a code, stop and describe what you see.
