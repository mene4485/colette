# Change the account password — demo site

Passwords never go through you: you never see, type, say or write any password, old or new.
The current password is filled by the tool `fill_free_password`; the new password is typed by the user
themselves, in the browser.

## Where
- http://localhost:8000/account/ → left menu "Mes informations" → "Modifier mon mot de passe"
  (direct page: http://localhost:8000/account/infos/motdepasse).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Modifier mon mot de passe". The form has three fields: "Mot de passe actuel",
   "Nouveau mot de passe", "Confirmer le nouveau mot de passe".
   Read the rule above them: at least 8 characters, including at least one digit.
3. Click "Mot de passe actuel" and call `fill_free_password` (no arguments).
4. Call `ask_user` with this question: "Tapez vous-même votre nouveau mot de passe dans les cases
   « Nouveau mot de passe » et « Confirmer le nouveau mot de passe ». Au moins 8 caractères, dont un
   chiffre. Ne me le dites pas. Dites « c'est fait » quand c'est fait." Wait for the answer.
   If the user says they do not want to continue, click "Annuler" and answer that nothing was changed.
5. Call `confirm_change` with `costs_money` = false and the summary:
   "Change the account password (new password typed by the user)."
6. Only if the reply says the user approved: click "Valider le nouveau mot de passe".
   If the user refused: click "Annuler" and answer that the password was not changed.
7. Check the result:
   - "Votre mot de passe a bien été modifié." on "Mes informations": answer that the password is changed,
     and remind the user to use the new one at the next login.
   - A red message ("Le mot de passe actuel est incorrect.", "…au moins 8 caractères, dont au moins un
     chiffre.", "Les deux nouveaux mots de passe ne sont pas identiques.", "Le nouveau mot de passe doit
     être différent de l'actuel."): the fields are now empty. Answer with the message and stop. Do not retry
     on your own.

## Never (in this task)
- Never type a password yourself, never ask the user to say it aloud, never repeat it in your answer.
- Never click "Valider le nouveau mot de passe" before `confirm_change` replied that the user approved.
- Never change personal details, the plan or the options.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
