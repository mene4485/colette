---
name: demo-travel
description: Use when the person is travelling abroad (for example to China) and wants to know if her plan works in that country (data, calls, texts) and whether she has to do anything before leaving, on the Free Mobile demo customer area. Read first; activating an option needs her spoken approval.
label: Travelling abroad
ask: I'm travelling to China. Does my plan work there?
keywords: travel | travelling | traveling | trip | abroad | overseas | holiday | vacation | roaming | china | chinese | foreign country | another country | united states | japan | canada | morocco
steps: Open your customer area | Log in | Check your plan abroad | Activate the option with you | Confirm with your approval
steps_view: Open your customer area | Log in | Check your plan abroad | Tell you what to do
order: 4
priority: 1
---
# Travelling abroad — demo customer area

"My plan" means the person's mobile plan (her subscription), not 5G technology. The question is:
does HER plan work in the country she named, and what must she do before leaving.
Answer ONLY from what the pages show. Never answer from general knowledge (networks, 5G coverage…).

## Where
- Left menu "Travelling abroad" (page "Using my line abroad"), also "My plan" → "Using my line abroad".

## Check (always first)
1. Open "Travelling abroad". Read "Included in your plan": where, data, calls and texts.
2. Find the country she named (China, United States…):
   - in "Included in your plan" → it works, nothing to activate;
   - in "Other destinations" → not included: read the prices without an option, and the option the page
     suggests (the Max option, its price and what it gives).
3. Answer in 2 or 3 simple sentences with the page's words, for example:
   "Your Free 5G plan works in Europe, but not in China: there, data costs €10 per GB and calls €2.19 a
   minute. Before you leave, you can activate the Max option, €9.99 a month: 35 GB and unlimited calls
   to France from China. Would you like me to do it?"
   Then stop: do not activate anything in this task unless the task asks to activate.

## Activate the option (only if the task asks for it)
1. Open "My options", find "Max option", click "Activate".
2. On the summary page, read the price and "Takes effect".
3. Call `confirm_change` with `costs_money` = true and a summary such as:
   "activate the Max option, €9.99 per month, for 35 GB and unlimited calls from China, starting now".
4. Only if the reply starts with "Approved": click "Confirm activation". If refused: click "Cancel".
5. Answer with the green message shown.

## Never
- Never answer from memory or general knowledge; if the page doesn't say, say you couldn't find it.
- Never activate an option, change the plan or pay without `confirm_change` replying "Approved".
- Never click "Reset the demo" or "Log out".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
