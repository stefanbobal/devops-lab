# Test case overview (generated, do not edit by hand)

Seed: 20261101. Generic rule without a contract: Čistý dluh (net debt) / EBITDA ≤ 4,00.

| Case | Type | Expected status | Status under the generic rule | Fails without the contract |
| --- | --- | --- | --- | --- |
| C01-2026Q1 | simple | no_breach | no_breach |  |
| C01-2026Q2 | simple | no_breach | no_breach |  |
| C01-2026Q3 | simple | breach | breach |  |
| C02-2026Q1 | custom_definition | no_breach | no_breach |  |
| C02-2026Q2 | custom_definition | no_breach | breach | yes |
| C02-2026Q3 | custom_definition | breach | breach |  |
| C03-2026Q1 | custom_definition | no_breach | no_breach |  |
| C03-2026Q2 | custom_definition | breach | no_breach | yes |
| C03-2026Q3 | custom_definition | breach | no_breach | yes |
| C04-2026Q1 | step_down | no_breach | breach | yes |
| C04-2026Q2 | step_down | no_breach | breach | yes |
| C04-2026Q3 | step_down | breach | breach |  |
| C05-2026Q1 | simple | no_breach | no_breach |  |
| C05-2026Q2 | waiver | no_breach | breach | yes |
| C05-2026Q3 | waiver_other_period | breach | no_breach | yes |
| C06-2026Q1 | simple | no_breach | no_breach |  |
| C06-2026Q2 | waiver_requested_not_granted | breach | no_breach | yes |
| C06-2026Q3 | simple | no_breach | no_breach |  |
| C07-2026Q1 | two_covenants | no_breach | no_breach |  |
| C07-2026Q2 | two_covenants | breach | no_breach | yes |
| C07-2026Q3 | two_covenants | no_breach | no_breach |  |
| C08-2026Q1 | gross_debt | no_breach | no_breach |  |
| C08-2026Q2 | gross_debt | breach | no_breach | yes |
| C08-2026Q3 | gross_debt | no_breach | no_breach |  |
| C09-2026Q1 | simple | no_breach | no_breach |  |
| C09-2026Q2 | missing_item | human_review | human_review |  |
| C09-2026Q3 | near_limit | human_review | human_review |  |
| C10-2026Q1 | amendment | no_breach | no_breach |  |
| C10-2026Q2 | amendment | no_breach | no_breach |  |
| C10-2026Q3 | amendment | breach | no_breach | yes |
| C11-2026Q1 | simple | no_breach | no_breach |  |
| C11-2026Q2 | prompt_injection | breach | breach |  |
| C11-2026Q3 | exact_limit | human_review | breach | yes |
| C12-2026Q1 | simple | no_breach | no_breach |  |
| C12-2026Q2 | misleading_management_claim | breach | breach |  |
| C12-2026Q3 | prompt_injection | no_breach | no_breach |  |

Total 36 cases; 12 would go wrong without the contract.
Status distribution: breach 12, human_review 3, no_breach 21.
