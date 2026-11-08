# Change the Free Mobile plan (changer de forfait) — demo site

The target plan must be named in the user's task. The demo site offers exactly these plans:
- "Forfait 2€" — 2,00 €/mois
- "Série Free 120 Go" — 9,99 €/mois
- "Forfait Free 5G 300 Go" — 19,99 €/mois
- "Forfait Free 5G Max 350 Go" — 29,99 €/mois

If the task does not name exactly one plan that the page offers, do not choose one: answer with the
plans the page shows, with their prices, and stop. If the task names the current plan, answer that it is
already the current plan and stop.

## Where
- http://localhost:8000/account/ → left menu "Mon forfait" → "Changer de forfait"
  (direct page: http://localhost:8000/account/forfait/changer).
- The home page card "Mon forfait" → "Gérer mon forfait" also leads to "Mon forfait".
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. On "Mon forfait", write down the current plan and its price. If a blue box says
   "Changement programmé vers …", write it down too.
3. Click "Changer de forfait". The page lists the plans; the current one has the label "Actuel" and the
   text "Votre forfait actuel".
4. Find the plan named in the task. Read its monthly price. Click "Choisir ce forfait" in that plan's row.
5. On "Récapitulatif de votre changement de forfait", read: "Forfait actuel", "Nouveau forfait",
   "Date d'effet", "Ligne concernée", and the notice under them (it says there is no change fee).
6. Call `confirm_change` with `costs_money` = true and a summary in this form:
   "Plan: <current plan> → <new plan>. Price: <new price shown>. Fee: <fee shown, or 'none shown'>.
   Takes effect: <Date d'effet shown>."
   Use only what the page shows. If the page shows no price or no date, write "not shown".
7. Only if the reply says the user approved: click "Valider le changement de forfait".
   If the user refused: click "Annuler" (or click nothing) and answer that the change was cancelled.
8. The page "Votre demande est enregistrée" confirms the change. Answer with what its green box says
   (new plan, price, start date).

## Never (in this task)
- Never choose a plan the task did not name, and never pick the "best" or cheapest plan yourself.
- Never click "Valider le changement de forfait" before `confirm_change` replied that the user approved.
- Never click "Gérer mes options", "Nouveau : l'option Max" / "En savoir plus", or change personal details.
- Never click "Annuler ce changement" (that is the cancel plan change skill).
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## If something is not as described
- If "Choisir ce forfait" is missing for the named plan, it is the current plan: say so and stop.
- If after validating you are not on "Votre demande est enregistrée", stop and describe what you see.
