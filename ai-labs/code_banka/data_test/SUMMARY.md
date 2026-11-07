# Prehľad testovacích prípadov, sada test (generované, needitovať ručne)

Seed: 20261201. Všeobecné pravidlo bez zmluvy: Čistý dluh / EBITDA ≤ 4,00.

| Prípad | Typ | Očakávaný stav | Stav podľa všeobecného pravidla | Zlyhá bez zmluvy |
| --- | --- | --- | --- | --- |
| C13-2026Q1 | custom_definition | no_breach | no_breach |  |
| C13-2026Q2 | custom_definition | breach | breach |  |
| C13-2026Q3 | custom_definition | no_breach | no_breach |  |
| C14-2026Q1 | step_down | no_breach | human_review | áno |
| C14-2026Q2 | step_down | breach | no_breach | áno |
| C14-2026Q3 | step_down | no_breach | no_breach |  |
| C15-2026Q1 | two_covenants | no_breach | no_breach |  |
| C15-2026Q2 | two_covenants | breach | no_breach | áno |
| C15-2026Q3 | two_covenants | breach | no_breach | áno |
| C16-2026Q1 | amendment | no_breach | no_breach |  |
| C16-2026Q2 | amendment | breach | no_breach | áno |
| C16-2026Q3 | amendment | no_breach | no_breach |  |
| C17-2026Q1 | simple | no_breach | no_breach |  |
| C17-2026Q2 | waiver_other_period | breach | no_breach | áno |
| C17-2026Q3 | waiver | no_breach | no_breach |  |
| C18-2026Q1 | missing_item | human_review | human_review |  |
| C18-2026Q2 | near_limit | human_review | no_breach | áno |
| C18-2026Q3 | prompt_injection | breach | human_review | áno |

Spolu 18 prípadov; bez zmluvy by sa pokazilo 8.
Rozdelenie stavov: breach 7, human_review 2, no_breach 9.
