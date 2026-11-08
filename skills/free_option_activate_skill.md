# Activate an option — demo site

The option to activate must be named in the user's task. If the task does not name exactly one option
that the page offers, do not choose one: answer with the options the page shows, with their prices, and stop.
If the named option is already "Activée", answer that it is already active and stop.

## Where
- http://localhost:8000/account/ → left menu "Mes options"
  (direct page: http://localhost:8000/account/options).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Mes options". Find the option named in the task. Read its price and its state.
3. Click "Activer" in that option's row.
4. On "Activation de l'option", read: "Option", "Prix", "Prise d'effet", "Ligne concernée" and the
   notice below (for a paid option: the price is added to the next bill, pro rata).
5. Call `confirm_change` with `costs_money` = true if the price is not "Gratuite" (false otherwise),
   and a summary in this form:
   "Activate option: <option name>. Price: <price shown>. Takes effect: <Prise d'effet shown>."
6. Only if the reply says the user approved: click "Confirmer l'activation".
   If the user refused: click "Annuler" and answer that the option was not activated.
7. Check that a green box says "L'option « <name> » est activée." and that the option now shows
   "Activée". Answer with it.

## Never (in this task)
- Never activate an option the task did not name, and never add a second option.
- Never click "Confirmer l'activation" before `confirm_change` replied that the user approved.
- Never deactivate an option, change the plan or change personal details.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
