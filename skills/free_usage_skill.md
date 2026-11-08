# Check usage stats (consommation) — demo site

Use this skill when the user asks how much they have used this month: internet data, calls, SMS, MMS,
data used abroad, or out-of-plan charges ("hors forfait"). This task only reads.

## Where
- http://localhost:8000/account/ → left menu "Conso et factures" → "Voir le détail de ma consommation"
  (direct page: http://localhost:8000/account/conso).
- The home page card "Ma consommation" → "Voir le détail" leads to the same page.
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Ma consommation". Read the period in the title ("Du <date> au <date>") and the line
   "Internet en France : <n> % de votre forfait utilisé.".
3. Read the table: for each row ("Internet en France", "Internet depuis l'Europe", "Appels", "SMS", "MMS",
   "Hors forfait"), the "Consommé" value and the "Inclus dans le forfait" value.
4. Answer the user's question with the values as shown. If the question is general, give: the period,
   internet used out of included, the percentage, calls, SMS, and the out-of-plan amount.

## Never (in this task)
- Never click "Changer de forfait", "Activer" or any option button, even if usage is high:
  only mention it if the user asks for advice.
- Never download a bill unless the task asks for it (then use the bill skill).
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".

## If something is not as described
- The page says usage can appear with a 48-hour delay: mention it if the user asks about today.
- If a value is not shown, say so. Never guess.
