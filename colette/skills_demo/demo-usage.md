---
name: demo-usage
description: Use when the person wants to know how much she used this month (data, data from Europe, calls, texts, MMS, extra charges) on the Free Mobile demo customer area. Read only.
keywords: usage | consumption | how much data | data left | data used | how much have i used
steps: Open your customer area | Log in | Open your usage | Read your usage
steps_view: Open your customer area | Log in | Open your usage | Read your usage
---
# Check usage this month — demo customer area

This task only reads.

## Where
- Left menu "Usage & bills" → "See my usage in detail", or the home card "My usage" → "See the details".

## Steps
1. Open "My usage". Read the period in the title ("From <date> to <date>") and the line
   "Data in France: <n>% of your plan used."
2. Read the table: for each row ("Data in France", "Data from Europe", "Calls", "Texts", "MMS",
   "Extra charges"), the "Used" value and the "Included in the plan" value.
3. Answer her question with the values as shown. If the question is general, give: the period, data used
   out of included, the percentage, calls, texts and extra charges. If she asks about today, say usage can
   take up to 48 hours to appear.

## Never
- Never click "Change plan", "Activate" or any option button, even if usage is high.
- Never download a bill. Never click "Reset the demo" or "Log out".
- If a value is not shown, say so. Never guess.

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
