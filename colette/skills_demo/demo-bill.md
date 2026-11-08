---
name: demo-bill
description: Use when the person wants to see or download their latest Free Mobile bill (invoice) on the Free Mobile demo customer area.
label: My bill
ask: I'd like to see my latest bill.
keywords: bill | bills | invoice | pdf
steps: Open your customer area | Log in | Find your bills | Show you where to download
order: 1
---
# See / download the most recent bill — demo customer area

## Where
- Customer area home → card "My latest bill" → "See my bills",
  or left menu "Usage & bills".

## Steps
1. Open "Usage & bills". The table "My bills" lists bills, the most recent first.
2. Read the first row: period (month and year), issue date, amount.
3. STOP on this page. Do NOT click "Download (PDF)", even if the person asked to download it:
   the file would land on YOUR computer, not hers. She clicks it herself on her own screen.
4. Answer in simple English with the month, the year and the amount, then exactly:
   To get it on your computer, click "Download (PDF)" on the first row yourself: I'm showing you where on your screen.

## Never (in this task)
- Never click "Download (PDF)" or any download link.
- This task only reads: never click "Change plan", never modify anything, nothing to confirm.

## Always ask the person first (every task)
- Before ANY action that cannot be undone, call `confirm_change` with a short English summary of what
  will happen, and act only if the reply starts with "Approved". This includes: downloading or opening
  a file (bill, PDF), saving, validating, confirming, sending, submitting a form, paying, ordering,
  subscribing, cancelling, deleting, changing a setting or a plan.
- One `confirm_change` per action. If the person says no, do not do it: stop and say nothing was done.
- Reading, opening a menu, going to a page or closing a cookie banner are not irreversible: no need to ask.
