# Explore the available options — demo site

Use this skill when the user asks which options they have, which options exist, or what an option costs.
This task only reads. To turn an option on or off, use the option activate / deactivate skills.

The demo site offers exactly these options:
- "Messagerie vocale visuelle" — Gratuite
- "Blocage des numéros surtaxés" — Gratuite
- "Option Data Europe +10 Go" — 5,00 €/mois
- "Option Appels Internationaux" — 3,99 €/mois
- "Option Max" — 9,99 €/mois

## Where
- http://localhost:8000/account/ → left menu "Mes options"
  (direct page: http://localhost:8000/account/options).
- "Mon forfait" → "Gérer mes options" and the home card "Nouveau : l'option Max" → "En savoir plus"
  lead to the same page.
- If you are not logged in, log in first with `fill_free_login` (see the Free Mobile login skill).

## Steps
1. If a cookie banner appears, click "Continuer sans accepter".
2. Open "Mes options". For each option, read: its name, what it does (the grey text), its price
   ("Gratuite" or "<price>/mois"), and its state ("Activée" or "Non activée").
3. Answer the user's question: the active options first, then the others with their prices.
   Describe each option in one simple sentence from the page text.

## Never (in this task)
- Never click "Activer" or "Désactiver": this task only reads.
- Never recommend an option on your own; only describe what the page shows.
- Never click "Réinitialiser la démo" (footer) or "Se déconnecter".
