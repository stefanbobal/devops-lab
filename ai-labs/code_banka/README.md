# code_banka: agent na sledovanie úverových podmienok (covenant monitoring)

Domáci lab na pohovor. **Všetky firmy, zmluvy, výkazy a čísla sú vymyslené.**
Žiadne skutočné klientske dáta ani firemný kód.

## Use case

Banka financuje firmy. Úverová zmluva obsahuje podmienky (covenants), napríklad
„čistý dlh / EBITDA ≤ 4,0“. Firma každý štvrťrok pošle finančné výkazy, ktoré dnes
analytik ručne prepisuje a kontroluje. Agent:

1. vytiahne čísla z výkazu (LLM alebo Document Intelligence),
2. **vypočíta pomery v Pythone**, nie v LLM,
3. cez RAG nájde v zmluve definície, limity platné pre dané obdobie, výnimky (waivers)
   a poznámky analytikov,
4. rozhodne: `breach` / `no_breach` / `human_review`, s citáciou článku a strany,
5. pri porušení alebo neistote založí úlohu pre analytika.

## Experiment: bez RAG vs. RAG vs. celá zmluva

| Režim | Čo agent dostane | Mapa na runner |
| --- | --- | --- |
| bez RAG | výkaz a všeobecné pravidlo | `no_history` |
| RAG | výkaz a nájdené články zmluvy, výnimky a poznámky | `rag` |
| celá zmluva | výkaz a všetky dokumenty klienta | `curated` |

Metriky: správnosť rozhodnutia, správnosť citácie, podiel `human_review`,
tokeny, cena a latencia za beh. Asi polovica prípadov musí byť postavená tak,
aby sa bez zmluvy pokazila (vlastná definícia EBITDA, výnimka, zmenený limit).

## Čo je prevzaté z `../code`

Motor bez dát: `config.py`, `providers.py`, `llm_metrics.py`, `rag_test.py`,
`test_rag_benchmark.py`, `search.py`, `rag_prompt.py`, `sweep_eval.py`,
`check_cloud.py`, `llm_prices.json`, `requirements.txt`, `docker-compose.yml`.

Zmeny oproti originálu:

- tabuľky `covenant_docs_<profil>`, nie `incident_memory_<profil>`, aby sa nedotkli incidentového labu;
- vlastná DB: kontajner `pgvector-banka` na porte **5433**, `PG_DSN` zodpovedá heslu z `docker-compose.yml`;
- `load_threshold` presunutý z `rag.py` do `thresholds.py` (incidentové demo `rag.py` sa nekopíruje);
- testy si vytvárajú vlastný dočasný súbor s thresholdmi.

Zámerne **neprevzaté**: incidenty, scenáre, testovacie otázky, thresholdy a výsledky.
Thresholdy treba **znova nakalibrovať** na nových dokumentoch; incidentové hodnoty tu neplatia.

## TODO

- [ ] `data/`: 10–15 vymyslených firiem: zmluva (Markdown/PDF), 2–4 štvrťročné výkazy, výnimky, poznámky analytikov
- [ ] `load_documents.py`: delenie zmluvy po článkoch (chunking) s metadátami firma / článok / strana / platnosť
- [ ] `search.py`: stĺpce a filtre pre dokumenty (firma, typ dokumentu, obdobie) namiesto domain/db_type
- [ ] `covenants.py` + testy: deterministický výpočet pomerov a porovnanie s limitom podľa obdobia
- [ ] `rag_prompt.py`: prompt pre rozhodnutie a citáciu; štruktúrovaný JSON výstup
- [ ] scenáre a očakávané výsledky (rozhodnutie a citovaný článok); časť s prompt injection vo výkaze
- [ ] automatické hodnotenie rozhodnutia a citácie (runner zatiaľ hodnotí iba ručne)
- [ ] kalibrácia thresholdov (`sweep_eval.py` načíta testy z `eval.py`, prepísať na nové testy)
- [ ] OpenTelemetry trace každého behu; voliteľne Azure AI Foundry a Application Insights
- [ ] GitHub Actions: `python -m unittest` a regresná evaluácia

## Spustenie (zatiaľ iba motor)

```bash
cd ~/devops-lab/ai-labs/code_banka
docker compose up -d          # vlastná DB na porte 5433
python -m unittest -v test_rag_benchmark
```
