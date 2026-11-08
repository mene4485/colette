# Cancel a scheduled plan change — demo site

Use this skill when the user asks to cancel a plan change they asked for earlier ("annuler le changement
de forfait", "je veux garder mon forfait"). A change is only scheduled if "Mon forfait" shows it.

## Where
- http://localhost:8000/account/ → left menu "Mon forfait"
  (direct page: http://localhost:8000/account/forfait).
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Mon forfait". Find the blue box "Changement programmé vers <new plan> le <date>.".
   If there is no such box, stop and answer that no plan change is scheduled.
3. Write down the current plan (under "Forfait actuel") and the scheduled plan and date.
4. Call `confirm_change` with `costs_money` = false and a summary in this form:
   "Cancel scheduled plan change: keep <current plan>; do not switch to <new plan> on <date>."
5. Only if the reply says the user approved: click "Annuler ce changement" in the blue box.
   If the user refused: click nothing, and answer that the scheduled change is kept.
6. Check that a green box says "Le changement de forfait programmé a été annulé.", then answer with it.

## Never (in this task)
- Never click "Changer de forfait" or "Choisir ce forfait": this task only cancels.
- Never click "Annuler ce changement" before `confirm_change` replied that the user approved.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
