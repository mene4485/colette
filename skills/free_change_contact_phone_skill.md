# Change the contact phone number — demo site

The contact phone is the number Free uses to reach the user. It is not the mobile line itself
(the line number "06 12 34 56 78" cannot be changed here).
The new number comes from the user's task: 10 digits starting with 0, or +33 followed by 9 digits.
If the task does not give a complete number, stop and answer that it is missing or incomplete.
Never invent or complete a value yourself.

## Where
- http://localhost:8000/account/ → left menu "Mes informations" → "Modifier mes coordonnées"
  (direct page: http://localhost:8000/account/infos/modifier).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. On "Mes informations", write down the current "Téléphone de contact".
3. Click "Modifier mes coordonnées". The form is already filled with the current values.
4. Clear "Téléphone de contact" and type the new number from the task. Check it digit by digit.
   Leave every other field exactly as it is.
5. Call `confirm_change` with `costs_money` = false and a summary in this form:
   "Contact phone: <old number> → <new number>."
6. Only if the reply says the user approved: click "Enregistrer les modifications".
   If the user refused: click "Annuler" and answer that the change was cancelled.
7. Check the result:
   - "Vos coordonnées ont bien été modifiées.": answer with the new number shown under "Téléphone de contact".
   - "Le numéro de téléphone n'est pas valide.": do not guess a fix. Stop and answer with the message.

## Never (in this task)
- Never change the postal address, the email, the holder ("Titulaire") or the password.
- Never click "Enregistrer les modifications" before `confirm_change` replied that the user approved.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
