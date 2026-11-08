# Check bills (amounts and dates) without downloading — demo site

Use this skill when the user asks about bills without wanting the file: "Combien était ma dernière
facture ?", "Quand a-t-elle été prélevée ?", "Combien j'ai payé en septembre ?". This task only reads.
To get the PDF, use the bill download skill instead.

## Where
- http://localhost:8000/account/ → left menu "Conso et factures"
  (direct page: http://localhost:8000/account/factures).
- The home page card "Ma dernière facture" shows the most recent bill only.
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Conso et factures". The table "Mes factures" lists the last 6 bills, the most recent first, with
   the columns "Période", "Émise le", "N°", "Montant".
3. Find the row(s) the user asks about (the first row is the most recent).
4. Answer with the period, the issue date ("Émise le"), the number and the amount, as shown.
   Bills are paid by automatic debit ("Prélevée automatiquement").

## Never (in this task)
- Never click "Télécharger (PDF)" unless the user asks for the file.
- Never click buttons to pay, cancel, change plan, subscribe, order or delete.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".

## If something is not as described
- Only the last 6 bills are shown. If the user asks for an older one, say it is not available.
