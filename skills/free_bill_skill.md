# Download a Free Mobile bill (most recent by default) — demo site

By default, download the most recent bill. If the user's task names a month (for example "la facture
d'août"), download the bill of that month instead.

## Where
- http://localhost:8000/account/ → left menu "Conso et factures"
  (direct page: http://localhost:8000/account/factures).
- The home page card "Ma dernière facture" → "Voir mes factures" leads to the same page.
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Conso et factures". The table "Mes factures" lists the last 6 bills, the most recent first, with
   the columns "Période", "Émise le", "N°", "Montant".
3. Pick the bill: the first row (most recent), or the row whose "Période" matches the month in the task.
   Write its period, number (N°) and amount in your notes before clicking.
4. Just before downloading, call `confirm_change` with `costs_money` = false and a summary in this form:
   "Download bill: <period>, n° <N°>, <amount>."
5. Only if the reply says the user approved: click "Télécharger (PDF)" in that row. The PDF is saved as a
   download named `Facture_FreeMobile_<N°>.pdf` (it does not open in a new tab). Stay on the page.
   If the user refused: click nothing, and answer that the bill was not downloaded.
6. Answer with: the period (month and year), the bill number and the amount.

## Never (in this task)
- Never click "Télécharger (PDF)" before `confirm_change` replied that the user approved.
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
- Never click buttons or links to pay, cancel, change plan, subscribe, order or delete:
  "Payer", "Régler", "Résilier", "Changer de forfait", "Souscrire", "Commander", "Supprimer".
- Never change any setting or personal detail. This task only reads and downloads.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".

## If something is not as described
- Only the last 6 bills are shown. If the user asks for an older one, say it is not available.
- If you cannot find the bills, or clicking does not download anything, stop and describe what you see.
