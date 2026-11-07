---
name: free-bill
description: Use when the person wants to see or download their latest Free Mobile bill (facture) from the Free Mobile customer area.
label: Ma facture
ask: Je voudrais télécharger ma dernière facture.
keywords: facture | factures | pdf
steps: Ouvrir votre espace abonné | Vous connecter | Trouver vos factures | Télécharger la dernière facture
order: 1
---
# Download the most recent Free Mobile bill

## Where
- Free Mobile customer area: https://mobile.free.fr/account/
- Pages are usually in French.

## Steps
1. If a cookie banner appears, choose the option that refuses cookies or continues without accepting
   ("Refuser", "Continuer sans accepter", "Reject all").
2. Si une connexion, un mot de passe ou un code SMS est demandé, appelle `ask_user` pour que la
   personne le tape elle-même, puis attends. Never type an identifier, password or code yourself.
3. Find the list of bills:
   - on the home page (Accueil), under "Suivi de consommation", or
   - in the menu "MON FORFAIT MOBILE" → "Conso et factures".
4. Pick the bill with the most recent date. Write its month and year in your notes before clicking.
5. Click the download or PDF button of that bill. The bill may open as a PDF in a new tab whose address
   looks like `https://mobile.free.fr/account/v2/api/SI/invoice/<number>?display=1`.
   Leave that tab open: do not close it.
6. Answer with the month and year of the bill and its amount if shown.

## Never (in this task)
- Never click buttons or links to pay, cancel, change plan, subscribe, order or delete:
  "Payer", "Régler", "Résilier un contrat", "Changer de forfait", "Souscrire", "Commander", "Supprimer".
- Never change any setting. This task only reads and downloads: there is nothing to confirm.

## If something is not as described
- Only the last 12 bills are kept in the customer area. If the user asks for an older one, say it is not available.
- If you cannot find the bills, or clicking does not open or download a PDF, stop and describe what you see.
