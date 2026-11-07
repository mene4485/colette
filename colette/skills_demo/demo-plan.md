---
name: demo-plan
description: Use when the person wants to change their Free Mobile plan (changer de forfait, passer à un forfait moins cher ou plus grand) on the Free Mobile demo customer area.
label: Mon forfait
ask: Je voudrais changer de forfait.
keywords: forfait | abonnement | offre
steps_view: Ouvrir votre espace abonné | Vous connecter | Voir votre forfait actuel
steps: Ouvrir votre espace abonné | Vous connecter | Trouver les forfaits | Choisir le forfait avec vous | Valider avec votre accord
order: 2
---
# Change the plan (changer de forfait) — demo customer area

## Where
- Customer area home → left menu "Mon forfait" → button "Changer de forfait".
- The plans page lists 4 plans, each with its monthly price and a "Choisir ce forfait" button
  (the current plan shows "Votre forfait actuel" instead).

## Steps
1. Open "Mon forfait" and write down the current plan and its price.
2. Click "Changer de forfait".
3. If the task names exactly one plan of the list (by name or by price), use it. Otherwise do not
   choose: call `ask_user` with a short question listing the plans and their monthly prices
   (e.g. « Il y a le forfait à 2 euros, la Série Free à 9,99 euros et le Max à 29,99 euros. Lequel voulez-vous ? »),
   and use the plan the person names.
4. Click "Choisir ce forfait" in the section of that plan.
5. On the "Récapitulatif" page, read the current plan, the new plan with its price, and the
   "Date d'effet".
6. Call `confirm_change` with `costs_money` = true and a short French summary, for example:
   "passer du Forfait Free 5G 300 Go au Forfait 2€, 2 € par mois, sans frais, à partir du 1er décembre".
7. Only if the reply starts with "Approved": click "Valider le changement de forfait".
   If refused: click nothing (or "Annuler") and answer that the change was cancelled.
8. Answer with what the confirmation page shows.

## Never
- Never pick a plan yourself: the person chooses.
- Never click "Valider le changement de forfait" before `confirm_change` replied "Approved".
- Never change options, personal details, or click "Réinitialiser la démo".
