# banka_covenant_agent: bankový agent ako Foundry hosted agent

Kópia reťazca z `../../code_banka` (commit `ad984fc`) bez zmeny logiky: `agent.py`, `covenants.py`, `sources.py`,
`contract_rules.py`, `rag_prompt.py`, `search.py`, `load_documents.py`, `providers.py`, `config.py`, `thresholds.*`
a dev dáta `data/`. Pridané sú len `foundry_app.py` (server), `foundry_deploy.py`, `Dockerfile`, `requirements-foundry.txt`
a `test_foundry_app.py`. Návrh a invarianty: `../../code_banka/FOUNDRY_PORT.md` (architektúra A).

Kópia sa nesynchronizuje sama. Ak sa v `code_banka` zmení prompt alebo overovanie, treba to preniesť sem a zapísať
nový commit; inak sa Foundry verzia porovnáva s iným kódom než V1.

Bez `data_test/` a bez útokov (do nasadeného balíka nepatria). Tajomstvá idú cez Foundry connection, nie cez súbory.
Lokálny `.env` (vzor `.env.example`, nie je v gite) drží len názov PostgreSQL servera a prihlasovacie meno.

Stav, postup nasadenia, výsledky testov a ďalšie kroky: `STAV_FOUNDRY_A_DALSIE_KROKY.md`.
