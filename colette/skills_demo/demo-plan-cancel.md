---
name: demo-plan-cancel
description: Use when the person wants to cancel a plan change she asked for earlier (scheduled plan change) and keep her current plan, on the Free Mobile demo customer area.
keywords: cancel my plan change | cancel the plan change | cancel the change of plan | keep my plan | keep my current plan | scheduled change
steps: Open your customer area | Log in | Find the scheduled change | Confirm with your approval
order: 99
---
# Cancel a scheduled plan change — demo customer area

A change is only scheduled if "My plan" shows it.

## Where
- Left menu "My plan".

## Steps
1. Open "My plan". Find the blue box "Change scheduled to <new plan> on <date>."
   If there is no such box, answer that no plan change is scheduled and stop.
2. Write down the current plan (under "Current plan"), the scheduled plan and the date.
3. Call `confirm_change` with `costs_money` = false and a summary such as:
   "cancel the switch to the €2 Plan planned on December 1, and keep the Free 5G 300 GB Plan".
4. Only if the reply starts with "Approved": click "Cancel this change" in the blue box.
   If refused: click nothing and answer that the scheduled change is kept.
5. Check the green box "The scheduled plan change has been cancelled." and answer with it.

## Never
- Never click "Change plan" or "Choose this plan": this task only cancels.
- Never click "Cancel this change" before `confirm_change` replied "Approved".
- Never click "Reset the demo" or "Log out".
- If a tool replies "Not done: ... Stop", stop and answer with that reply.

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
