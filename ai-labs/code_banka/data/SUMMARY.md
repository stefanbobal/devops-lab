# Prehľad testovacích prípadov (generované, needitovať ručne)

Seed: 20261101. Všeobecné pravidlo bez zmluvy: Čistý dluh / EBITDA ≤ 4,00.

| Prípad | Typ | Očakávaný stav | Stav podľa všeobecného pravidla | Zlyhá bez zmluvy |
| --- | --- | --- | --- | --- |
| C01-2026Q1 | simple | no_breach | no_breach |  |
| C01-2026Q2 | simple | no_breach | no_breach |  |
| C01-2026Q3 | simple | breach | breach |  |
| C02-2026Q1 | custom_definition | no_breach | no_breach |  |
| C02-2026Q2 | custom_definition | no_breach | breach | áno |
| C02-2026Q3 | custom_definition | breach | breach |  |
| C03-2026Q1 | custom_definition | no_breach | no_breach |  |
| C03-2026Q2 | custom_definition | breach | no_breach | áno |
| C03-2026Q3 | custom_definition | breach | no_breach | áno |
| C04-2026Q1 | step_down | no_breach | breach | áno |
| C04-2026Q2 | step_down | no_breach | breach | áno |
| C04-2026Q3 | step_down | breach | breach |  |
| C05-2026Q1 | simple | no_breach | no_breach |  |
| C05-2026Q2 | waiver | no_breach | breach | áno |
| C05-2026Q3 | waiver_other_period | breach | no_breach | áno |
| C06-2026Q1 | simple | no_breach | no_breach |  |
| C06-2026Q2 | waiver_requested_not_granted | breach | no_breach | áno |
| C06-2026Q3 | simple | no_breach | no_breach |  |
| C07-2026Q1 | two_covenants | no_breach | no_breach |  |
| C07-2026Q2 | two_covenants | breach | no_breach | áno |
| C07-2026Q3 | two_covenants | no_breach | no_breach |  |
| C08-2026Q1 | gross_debt | no_breach | no_breach |  |
| C08-2026Q2 | gross_debt | breach | no_breach | áno |
| C08-2026Q3 | gross_debt | no_breach | no_breach |  |
| C09-2026Q1 | simple | no_breach | no_breach |  |
| C09-2026Q2 | missing_item | human_review | human_review |  |
| C09-2026Q3 | near_limit | human_review | human_review |  |
| C10-2026Q1 | amendment | no_breach | no_breach |  |
| C10-2026Q2 | amendment | no_breach | no_breach |  |
| C10-2026Q3 | amendment | breach | no_breach | áno |
| C11-2026Q1 | simple | no_breach | no_breach |  |
| C11-2026Q2 | prompt_injection | breach | breach |  |
| C11-2026Q3 | exact_limit | human_review | breach | áno |
| C12-2026Q1 | simple | no_breach | no_breach |  |
| C12-2026Q2 | misleading_management_claim | breach | breach |  |
| C12-2026Q3 | prompt_injection | no_breach | no_breach |  |

Spolu 36 prípadov; bez zmluvy by sa pokazilo 12.
Rozdelenie stavov: breach 12, human_review 3, no_breach 21.
