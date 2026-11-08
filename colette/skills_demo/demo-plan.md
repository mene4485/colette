---
name: demo-plan
description: Use when the person wants to change their Free Mobile plan (switch to a cheaper or bigger plan) on the Free Mobile demo customer area.
label: My plan
ask: I'd like to change my plan.
keywords: plan | subscription | offer
steps_view: Open your customer area | Log in | See your current plan
steps: Open your customer area | Log in | Find the plans | Choose the plan with you | Confirm with your approval
order: 2
---
# Change the plan — demo customer area

## Where
- Customer area home → left menu "My plan" → button "Change plan".
- The plans page lists 4 plans, each with its monthly price and a "Choose this plan" button
  (the current plan shows "Your current plan" instead).

## Steps
1. Open "My plan" and write down the current plan and its price.
2. Click "Change plan".
3. If the task names exactly one plan of the list (by name or by price), use it. Otherwise do not
   choose: call `ask_user` with a short question listing the plans and their monthly prices
   (e.g. "There's the 2 euro plan, the Free Series at 9.99 euros and the Max at 29.99 euros. Which one would you like?"),
   and use the plan the person names.
4. Click "Choose this plan" in the section of that plan.
5. On the "Summary of your plan change" page, read the current plan, the new plan with its price, and the
   "Effective date".
6. Call `confirm_change` with `costs_money` = true and a short English summary, for example:
   "switch from the Free 5G 300 GB Plan to the €2 Plan, €2 per month, no fee, starting December 1".
7. Only if the reply starts with "Approved": click "Confirm plan change".
   If refused: click nothing (or "Cancel") and answer that the change was cancelled.
8. Answer with what the confirmation page shows.

## Never
- Never pick a plan yourself: the person chooses.
- Never click "Confirm plan change" before `confirm_change` replied "Approved".
- Never change options, personal details, or click "Reset the demo".

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
