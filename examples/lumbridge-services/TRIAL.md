# Lumbridge trial: leave Tutorial Island without help

This is an independent usability and accounting review of a synthetic case.
No OSRS knowledge is needed. Varrock and Falador are the 2 service lines;
the Grand Exchange reference means customer collections.

Use a fresh copy of `lumbridge.xlsx`, its source files and this guide.
Keep the answer key closed until you have recorded your results.
You do not need a Xero login, client data, macros or an AI agent.

## What you are reviewing

| Item | Value |
| --- | --- |
| Artefact | `lumbridge.xlsx`, 23,506 bytes |
| SHA-256 | `b150de6281fccb6dcb1d221c034b047eb610ad4064972c5d9ac9fca8916b8463` |
| Source commit | [`386c7ff31f7989b86445ef37d83a912fcb02bb47`](https://github.com/ryanduguid/au-fpa-pack/tree/386c7ff31f7989b86445ef37d83a912fcb02bb47/examples/lumbridge-services) |
| Distributed at | <https://duguid.com.au/assets/examples/lumbridge/lumbridge-sample-pack.zip> |
| Explained at | <https://duguid.com.au/examples/profit-vs-cash-flow/> |
| Prerequisites | Desktop Excel with automatic calculation. To rebuild instead, Python 3.11 and uv |
| Data | Fabricated throughout. No client, taxpayer or production data is involved |

The SHA-256 is for the `lumbridge.xlsx` member of the published ZIP, not for a
local rebuild. Compare it before you start if you received the file by any route
other than the download above. If you rebuild from source, a fresh export can
differ in package metadata or cache bytes from the distributed file; the figures
should not.

## Which evidence this produces

Keep these three categories apart when reporting or citing a result.

1. **Author-run technical checks.** Formula checks against the Python model, the
   repository suite and a native Excel run by the maintainer. Already complete and
   recorded in the sample record. They establish that the workbook calculates what
   its model says, nothing more.
2. **Maintainer trial.** The author opening the workbook and exercising it. Recorded
   as such, and not independent.
3. **Independent review.** This guide, completed by an accountant with no part in
   building the case. **None has been completed.** Until a named reviewer returns a
   result under the consent terms below, the independent-review status stays pending
   and no page, README or listing may claim otherwise.

## First run

If you received the workbook, open it in desktop Excel and enable automatic
calculation. Do not enable macros or external links. If you are reproducing
from source, follow the 2 commands in the example README first.

Record your Excel version, operating system, start time and whether you
used the supplied workbook or rebuilt it. Record any help you need.

1. Find the October to December revenue, profit before income tax and
   December closing cash. Identify which amounts are forecasts.
2. Find the lowest daily closing cash balance and the date it occurs.
   Explain why looking only at December cash could miss a funding problem.
3. Find invoice OPEN-V in `data/invoices.csv`. Trace its amount and receipt
   date into the workbook.
4. Change the receipt-delay control from 0 to 45 calendar days. Record the
   lowest daily balance, first negative date and October closing cash.
   State whether profit changed and explain the difference.
5. Identify the outstanding December GST, supplier and PAYG withholding
   balances. Explain why gross wages and net employee bank payments differ.
6. Check the profit-to-cash reconciliation for all 3 months. Explain
   how non-cash leave, customer debtors and tax payments enter the bridge.
7. Recommend one action for the owner before approving discretionary
   equipment spending. A dragon pickaxe is the fictional equipment upgrade.
8. Restore the delay to zero, save your trial copy, close and reopen it.
   Confirm the original results return.

The workbook's only supported scenario control is `Assumptions!B2`.
Blank cells in January's closing-cash column are intentional: future
invoice dates support receivables, but January payments are outside the forecast.
The README states the model's limits and source assumptions.

## Record your findings

| Item | Reviewer entry |
| --- | --- |
| Reviewer and date | |
| Excel version and operating system | |
| Started / finished | |
| Used supplied workbook or rebuilt | |
| Steps completed without help | |
| Help requested and exact obstacle | |
| Base quarterly revenue / pre-tax profit | |
| Base December cash / lowest daily cash and date | |
| Late-case lowest daily cash and date / first negative date | |
| Late-case October cash / change in profit | |
| December GST / supplier / PAYG balances | |
| Reconciliation differences | |
| Owner action and supporting evidence | |
| Incorrect or unsupported assumption found | |
| Save and reopen result | |

Use the answer key only after completing this table. Record differences
against the key instead of replacing your original answers.

## Report a deviation or a defect

Anything that did not behave as this guide describes is worth returning, including
a figure that differs from the key, a step whose wording sent you the wrong way, an
Excel version that refused the file, and a result you could not reproduce twice.

Record the step number, exactly what you did, what you observed and what you
expected, plus your Excel version and operating system. Attach a screenshot only if
it contains no client or personal data.

The channel you agreed with the maintainer is the default route for every finding.
Anything that could be a security weakness goes through the private reporting
process that [SECURITY.md](../../SECURITY.md) describes, and is never filed as a
public issue. Issues are switched off in this repository, so there is no public
issue route: return non-sensitive defects through the agreed channel as well. Once
the consent block below says Yes to publication, the maintainer records the defect
and its fix in a pull request that links your finding. Never send contact details or
a screenshot containing personal data for publication.

## Consent and attribution

Nothing you write here is published unless you say so below. Complete this block and
return it with your findings.

| Item | Reviewer entry |
| --- | --- |
| May the findings be published? | Yes / No |
| If yes, attribute them to | Name and organisation, or Anonymous |
| May your professional designation be named? | Yes / No |
| May the completed table be quoted in full? | Yes / Summary only |
| Any part to be withheld | |
| Date of consent | |
| Contact for follow-up | |

Consent may be withdrawn at any time. A published independent review names the
reviewer or states that they chose to remain anonymous, and it links this guide and
the exact artefact reviewed. Findings returned without a completed consent block
stay private and are used only to fix the case.

The trial passes only when the reviewer reproduces the figures, explains
the profit/cash difference and identifies the liabilities and owner action
without unrecorded help. Report elapsed time as an observation; it is not
evidence of time saved against another workflow.

Return the completed table and any issues to Ryan through a channel he
chooses. Nothing in this guide submits a report automatically.
