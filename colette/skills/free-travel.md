---
name: free-travel
description: Use when the person is travelling abroad (for example to China) and wants to know if her Free Mobile plan works in that country (data, calls, texts) and whether she has to do anything before leaving (option to activate). Read first; any activation needs her spoken approval.
label: Travelling abroad
ask: I'm travelling abroad. Does my plan work there?
keywords: travel | travelling | traveling | trip | abroad | overseas | holiday | vacation | roaming | china | chinese | foreign country | another country | voyage | etranger | étranger | chine
steps: Open your customer area | Log in | Check your plan abroad | Check your travel options | Confirm with your approval
steps_view: Open your customer area | Log in | Check your plan abroad | Check your travel options | Tell you what to do
order: 4
priority: 1
---
# Travelling abroad: does the plan work there, what to do before leaving — Free Mobile

The person names a country (for example China). Find, ON THE WEBSITE, whether her plan covers that
country and what she must do before leaving. Use only what the pages show: never answer from memory,
never guess a price, an amount of data or a list of countries.

## Where
- Free Mobile customer area: https://mobile.free.fr/account/ (pages in French).
- If a cookie banner appears, choose the option that refuses cookies or continues without accepting
  ("Refuser", "Continuer sans accepter", "Reject all").
- If a login, a password or a text-message code is requested, call `ask_user` so the
  person types it herself, then wait. Never type an identifier, password or code yourself.

## Steps (check only)
1. "Mon forfait" (or "Mon offre"): write down the name of her plan and what it includes abroad. Open the
   plan details if there is a link ("Détails", "Voir le détail", "Mon forfait en détail"). Look for
   words like "depuis l'étranger", "à l'international", "Europe et DOM", "destinations", "roaming",
   and look for the country she named (China = "Chine").
2. "Mon forfait" → "Mes options": read the lines "Option Voyage" (calls and texts from abroad),
   "Service de données" / "Data à l'étranger" (mobile data abroad) and "Option Internationale" (calls
   from France to abroad, not needed for a trip). For each, write down if it is active
   ("Activée", "Désactiver" button shown) or not ("Activer", "Détails" button shown) and the price shown.
3. If the customer area does not say whether the country is covered, look for a link to the destinations
   or the international prices ("Tarifs à l'étranger", "Destinations incluses", "Tarifs internationaux",
   "Voir les destinations") and read it for that country. If you still cannot find it, say so.
4. Answer in 2 or 3 simple English sentences: does her plan work in that country (data / calls and
   texts, with the amount or price shown), and what she must do before leaving (for example: "the
   Voyage option is not active: you need it to call from China"), or that nothing is needed.

## Only if she asks you to activate something
- An activation is irreversible and may cost money: call `confirm_change` FIRST with a summary such as
  "activate the Voyage option to call and text from China, with a 10 euro advance", and
  `costs_money` = true if a price or an advance is shown.
- Only if the reply starts with "Approved": click the option's "Détails" / "Activer" button.
- If the page asks for a bank card (card number, expiry date, code): STOP. Never type card details.
  Call `ask_user` so the person types them herself on the page, or answer that she has to finish the
  payment herself, and say what is left to do.
- Click the final button ("Payer et activer", "Activer", "Valider") only after her approval and only
  once she has typed the card details herself.

## Never (in this task)
- Never activate, deactivate, pay, change the plan or change any setting without `confirm_change`
  having replied "Approved".
- Never type a bank card number, a password or a code.
- Never click "Changer de forfait", "Résilier", "Commander" or "Souscrire".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan, activating or deactivating an option.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
