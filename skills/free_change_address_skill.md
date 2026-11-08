# Change the postal address — demo site

The new address comes from the user's task: street with number, postal code (5 digits) and city.
If the task does not give the complete new address, stop and answer which part is missing.
Never invent or complete a value yourself (no guessed postal code).

## Where
- http://localhost:8000/account/ → left menu "Mes informations" → "Modifier mes coordonnées"
  (direct page: http://localhost:8000/account/infos/modifier).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. On "Mes informations", write down the current "Adresse postale".
3. Click "Modifier mes coordonnées". The form is already filled with the current values.
4. Clear and type the new values in "Adresse (numéro et rue)", "Code postal" and "Ville". Check each
   field letter by letter. Leave "Adresse e-mail" and "Téléphone de contact" exactly as they are.
5. Call `confirm_change` with `costs_money` = false and a summary in this form:
   "Postal address: <old street>, <old postal code> <old city> → <new street>, <new postal code> <new city>."
6. Only if the reply says the user approved: click "Enregistrer les modifications".
   If the user refused: click "Annuler" and answer that the change was cancelled.
7. Check the result:
   - "Vos coordonnées ont bien été modifiées.": answer with the new address shown under "Adresse postale".
   - A red message ("Le code postal doit contenir 5 chiffres.", "Tous les champs sont obligatoires."):
     do not guess a fix. Stop and answer with the message and the value that was refused.

## Never (in this task)
- Never change the email, the contact phone, the holder ("Titulaire") or the password.
- Never click "Enregistrer les modifications" before `confirm_change` replied that the user approved.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## If something is not as described
- The demo site does not ask for the password and sends no verification letter. If a page asks for a
  password or a code, stop and describe what you see.
