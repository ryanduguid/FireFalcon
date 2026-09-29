# Supplier information for a firm's AI register

The National AI Centre's Guidance for AI Adoption (October 2025) asks organisations to
keep an AI register as part of its fourth practice, sharing essential information, and
asks developers to share technical details, test results, limitations and risks with
the organisations that deploy their systems. Items 4.1.1 and 4.3.2 of its
[implementation guidance](https://www.ai.gov.au/staying-safe-and-responsible/essential-ai-practices/guidance-ai-adoption-implementation-guidance)
set out both. The table below gives the supplier's side of that record for this pack,
checked against the version it names on 29 September 2026.

The first seven rows follow the columns of the National AI Centre's
[AI register template](https://www.ai.gov.au/staying-safe-and-responsible/essential-ai-practices/ai-systems-register),
so a firm can start those columns from them; the other rows serve the rest of its
register and its risk assessment. The firm adds the template's remaining columns (owner,
status, purpose, registered date and screening outcome) and its own use case,
deployment environment, risk and impact assessment, controls and review cycle.

`tests/test_ai_register_entry.py` fails when the package version moves without this
table. Supplier information is not a certification, an approval of any use or a
statement that a firm's use complies with anything. The firm decides what client data
may be used, under its AI-use policy and its legal, professional, contractual and
privacy obligations.

| Field | Entry |
| --- | --- |
| Name and version | au-fpa-pack 0.1.2 (import `pyfpa`, command `openfpa`), an Australian FP&A kernel and agent skills that build cash forecasts and management briefings from a company's own records |
| Source and updates | Extends [openfpa](https://github.com/JeffBrines/openfpa) by Guiderail; Ryan Duguid maintains the Australian additions. MIT licence, with no warranty or support agreement. Releases are on PyPI with [release notes](../RELEASE_NOTES.md), and an installed version changes only when the firm upgrades it. A Claude Code marketplace entry pointing at this repository installs the skills as the `openfpa` plugin, whose manifest carries its own version. |
| Intended use cases | Gives an agent a deterministic kernel for Australian cash timing (30 June years, GST and BAS, payroll on-costs, Xero AU mapping) and a workflow for learning a business, running the month and scoring forecasts against actuals |
| Known limitations and prohibited use | Forecasting aid, not tax advice or a funding decision. The generated files do not establish native Excel recalculation or forecast accuracy. An approval record is an acknowledgement a practitioner writes, not authentication and not proof that a client consented. |
| Foreseeable misuse and failure | One client's information reaches another client's work through portfolio learning: promotion is default-deny, and nothing reaches the shared library without an approval bound to that exact candidate by its digest. Xero API data is used to adapt forecasts, which Xero's developer terms (as last updated on 4 December 2025) restrict: every source records whether it came through the API, and the [Xero recipe](recipes/xero-au.md) asks the company owner to confirm and record a check of the current terms before a learning skill uses an API source. Whether a particular workflow falls within those terms stays the firm's decision. |
| Data sources and type | A company's own records, such as ledger and Xero exports, payroll assumptions and dated receipts and payments, kept with the company's memory, corrections, forecasts and decisions in its `.fpa/` workspace on the local machine. The workspace stays until the firm deletes it; retention and deletion are the firm's. |
| Key stakeholders affected | May include the company whose records are modelled, the people who make funding decisions from its forecasts, and the firm's other clients if cross-client learning is approved |
| Contains an AI model | No. The firm's agent, with its host's model, follows the skills. Once a person approves the proposed model architecture, the agent writes company-specific forecast code, connectors and skills into the company's workspace, and a challenger forecast replaces the current one only with a recorded human approval. |
| Datasets and training | The worked examples are fabricated or built from public data. The pack trains and fine-tunes no AI model; its research loop scores forecast challengers against the company's own closed periods. |
| Technical requirements | Python 3.11 or later; an agent runtime that loads skills for the agent workflow; desktop Excel with automatic calculation for the workbook outputs |
| Network access | The kernel fetches public RBA and ABS series when the agent refreshes a driver, sending no company data. Live Xero extraction, where a company adds it, is separate per-company code with credentials the host manages. A host that uses a hosted model sends the conversation, and any workspace content the agent reads, to that model's provider. |
| Where a person decides | The funding decision stays with a person. The onboarding skill stops for approval before the agent scaffolds models, connectors or skills. The research loop may test challenger forecasts with changed assumptions on its own, but none replaces the current forecast, and no cross-client prior is promoted, without a recorded approval. |
| Acceptance and testing | A change reaches `main` only when the required CI checks pass, and they run the test suite on fabricated and public data, including the worked [Lumbridge case](../examples/lumbridge-services/README.md) with its inputs, method and limits |
| Independent assurance | None. No external audit, certification or practitioner review. |
| Report a problem | A vulnerability through the [security policy](../SECURITY.md). Issues are switched off here, so report a wrong result in the Australian layer through the [contact page](https://duguid.com.au/contact/), and one in the shared kernel in [openfpa's issues](https://github.com/JeffBrines/openfpa/issues), reproduced with fabricated data, never client data. |
| For the firm to complete | Owner, status, purpose and business goals, registered date and screening outcome (the template's firm columns); installed version, agent runtime and model provider, which companies' records it may hold, whether cross-client learning is permitted, whether any source comes through the Xero API, impact and risk assessment outcome and treatment, any audit requirement, next review date |

## ISO/IEC 42001

AS ISO/IEC 42001:2023 is the Australian identical adoption of ISO/IEC 42001:2023, a
management system standard for organisations that provide or use AI systems.
Certification against it is voluntary and is carried out by external certification
bodies, not by ISO. The table above is supplier information a firm may use in its own
AI register, risk assessment or other governance records. It is not a certification,
an audit or a conformity assessment, and it does not establish that any organisation's
AI management system conforms to the standard or that this pack is certified, approved
or assured under it.
