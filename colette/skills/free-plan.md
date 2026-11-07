---
name: free-plan
description: Use when the person wants to change their Free Mobile plan (changer de forfait, passer à un forfait moins cher ou plus grand) in the Free Mobile customer area.
label: My plan
ask: I'd like to change my plan.
keywords: plan | subscription | offer | forfait
steps_view: Open your customer area | Log in | See your current plan
steps: Open your customer area | Log in | Find the plans | Choose the plan with you | Confirm with your approval
order: 2
---
# Change the Free Mobile plan (changer de forfait)

## Where
- https://mobile.free.fr/account/ → "Mon compte" → "Changer de forfait"
  (some pages show it under "Mon compte" → "Mon offre" → "Changer de forfait").
- If a login, a password or a text-message code is requested, call `ask_user` so the
  person types it herself, then wait. Never type an identifier, password or code yourself.

## Steps
1. Write down the current plan shown on the page.
2. If the task names exactly one plan that the page offers, use it. Otherwise do not choose one:
   call `ask_user` with a short question listing the plans the page shows and their monthly prices,
   and use the plan the person names.
3. Find the section of that plan. Read its monthly price. Click "Choisir ce forfait" in that section.
4. On the next page, read: the new monthly price, any fee, the date the change takes effect, and the
   legal notices. Do not tick the box yet.
5. Call `confirm_change` with `costs_money` = true and a short French summary, for example:
   "passer du Forfait Free 5G+ au Forfait 2€, 2 € par mois, sans frais, à partir du 1er décembre".
   Use only what the page shows. If the page shows no price or no date, say "non affiché".
6. Only if the reply says the user approved: tick the legal-notice box and click
   "Valider mon changement de forfait".
   If the user refused: do not tick the box, do not click, and answer that the change was cancelled.
7. Answer with what the page shows after validating.

## What Free's help pages say (for your summary; the page is what counts)
- Forfait 2€ → Free 5G+ / Free Max: effective within 24 hours; the billing date moves to the new start date.
- Free 5G+ / Free Max → Forfait 2€: only after three full paid months; a 10 € fee on the current bill;
  effective at the next renewal date.
- If the page says the change is not possible (for example from a promotional offer, or a greyed-out
  button), stop and answer with the page's message.

## Never
- Never pick the "best" plan yourself: the person chooses.
- Never tick the legal-notice box or click "Valider mon changement de forfait" before `confirm_change`
  replied that the user approved.
- Never add options or boosters, buy a phone, take insurance, cancel the line ("Résilier"), pay a bill,
  or change personal details.
- If a tool replies "Not done: ... Stop", stop and answer with that reply.
