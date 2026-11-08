# Deactivate an option — demo site

The option to deactivate must be named in the user's task. If the task does not name exactly one option
that is "Activée" on the page, do not choose one: answer with the active options and stop.
If the named option is "Non activée", answer that it is not active and stop.

## Where
- http://localhost:8000/account/ → left menu "Mes options"
  (direct page: http://localhost:8000/account/options).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Mes options". Find the option named in the task; check it shows "Activée".
3. Click "Désactiver" in that option's row.
4. On "Désactivation de l'option", read: "Option", "Prix", "Prise d'effet", "Ligne concernée".
5. Call `confirm_change` with `costs_money` = false and a summary in this form:
   "Deactivate option: <option name> (<price shown>). Takes effect: <Prise d'effet shown>."
6. Only if the reply says the user approved: click "Confirmer la désactivation".
   If the user refused: click "Annuler" and answer that the option is still active.
7. Check that a green box says "L'option « <name> » est désactivée." and that the option now shows
   "Non activée". Answer with it.

## Never (in this task)
- Never deactivate an option the task did not name.
- Never click "Confirmer la désactivation" before `confirm_change` replied that the user approved.
- Never activate an option, change the plan or change personal details.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
