# Check the current Free Mobile plan — demo site

Use this skill when the user asks "Quel est mon forfait ?", "Combien je paie par mois ?", or whether a
plan change is scheduled. This task only reads. It never changes anything.

## Where
- http://localhost:8000/account/ → left menu "Mon forfait"
  (direct page: http://localhost:8000/account/forfait).
- The home page card "Mon forfait" shows the same plan and price.
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Mon forfait". Under "Forfait actuel", read: the plan name, its monthly price, and the list of
   what it includes (calls, SMS, internet).
3. If a blue box says "Changement programmé vers <plan> le <date>.", read it too.
4. Answer with the plan name, the monthly price, what it includes, and the scheduled change if there is one.

## Never (in this task)
- Never click "Changer de forfait", "Choisir ce forfait", "Annuler ce changement" or "Gérer mes options".
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".

## If something is not as described
- If the plan or the price is not shown, say it is not shown. Never guess.
