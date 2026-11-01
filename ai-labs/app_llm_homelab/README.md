# LLM Homelab · Experiment Studio

Podrobná architektúra, fungovanie, dátový model a návrh využitia pre bankového agenta:
[APP-LLM-HOMELAB.md](../APP-LLM-HOMELAB.md).

Lokálna aplikácia v HTML, CSS a JavaScripte na analýzu RAG/LLM behov.
**Odporúčané nasadenie: jeden Docker image pre rozhranie aj Python API.**
Použi [DOCKER.md](DOCKER.md): build, import existujúcich výsledkov do PostgreSQL,
spustenie kontajnera a prístup cez SSH tunel. Existujúci pgvector zostáva databázou.

**PostgreSQL režim je pripravený:** import pôvodných výsledkov a trvalé hodnotenie
cez Python API — postup v [DATABASE.md](DATABASE.md). Pri tomto režime netreba výsledky
kopírovať z VM do Windowsu. Nižšie je pôvodný samostatný súborový režim.
Samostatný priečinok vedľa `code`; benchmark skripty sa nemenia.
Žiadny build, framework, CDN, prihlasovanie, platené volania ani upload výsledkov na server.

## Spustenie

Na počítači s Node.js (18+):

```bash
cd ~/devops-lab/ai-labs/app_llm_homelab
node server.mjs
```

Otvor **http://127.0.0.1:8008**. Server počúva iba na localhost a servuje iba súbory aplikácie.
Vo Windows prejdi do svojho checkoutu `devops-lab/ai-labs/app_llm_homelab`
a spusti rovnaký `node server.mjs`. Ukončenie servera: Ctrl+C.

Alternatíva bez Node, na Ubuntu s existujúcim Pythonom:

```bash
cd ~/devops-lab/ai-labs/app_llm_homelab
python -m http.server 8008 --bind 127.0.0.1
```

Ak server beží vo VM a prehliadač vo Windows, otvor samostatné SSH spojenie z Windows:

```powershell
ssh -L 8008:127.0.0.1:8008 sapops@k8s-lab
```

Potom vo Windows otvor http://127.0.0.1:8008. Python server sprístupňuje len app priečinok;
nespúšťaj ho z priečinka s tajnými kľúčmi. Priame otvorenie index.html cez file://
nie je podporované kvôli JavaScript modulom.

## Import výsledkov

Vyber **Načítať výsledky** a priečinok `results` (alebo jeden konkrétny beh).
Načítajú sa všetky obsiahnuté behy; ďalší import nahradí aktuálny výber dát.
Prehliadač vyberá súbory z počítača, na ktorom beží — SSH tunel z neho nespraví
prehliadač VM disku. Skopíruj si behy na Windows, napríklad do nového adresára:

```powershell
scp -r sapops@k8s-lab:~/devops-lab/ai-labs/code/results ./homelab-results
```

Preferovaná štruktúra každého behu:

```text
rag-dev-.../
  manifest.json
  calls/*.json
  contexts/*.json
  results.csv
  quality_review.csv
```

- Calls JSON je zdroj úplných promptov, odpovedí a usage údajov.
- Manifest dopĺňa aktuálny incident, guidance a nastavenia.
- Context JSON zobrazí vybrané historické incidenty a similarity.
- results.csv a review_packet.csv môžu doplniť polia; JSON má prednosť.
- quality_review.csv sa spojí podľa call_id v danom behu.
- CSV parser podporuje viacriadkové odpovede, úvodzovky a UTF-8 BOM.
- Bez manifestu či JSON zobrazíme dostupné metriky, ale upozorníme na chýbajúce údaje.
- Samostatné súbory je možné vybrať cez CSV / JSON. Viac rôznych behov s rovnakými
  názvami súborov importuj cez priečinky, aby sa zachovalo priradenie k behom.
- Logy GPU, summary.json, konzolové logy a nesúvisiace súbory sa do počtu volaní nezarátajú.

Identita volania je beh + call_id. Pri manifeste používame fingerprint + created_at;
rovnaký export z viacerých súborov sa nezapočíta znovu. Nezávislé opakované behy s
rovnakým nastavením sa podľa času vytvorenia zachovajú samostatne. Opravné behy
majú vlastnú identitu; aplikácia ich automaticky nepovažuje za náhradu pôvodných chýb.

## Grafy a interpretácia

Prehľad obsahuje p50/p95 latencie úspešných volaní, známe LLM náklady, tokeny,
spoľahlivosť, koreláciu výstupných tokenov a latencie a tabuľku jednotlivých volaní.
Na bod/balku v grafe prejdi myšou pre detail. Filtre: beh, LLM, embedding, režim a hľadanie.
Chýbajúca cena zostáva neznáma. Známy súčet nie je celá faktúra.
Lokálna cena 0 znamená iba nulový API poplatok. Embeddingy, elektrina a infraštruktúra
nie sú v súčte. Budúce ceny Argonu zostávajú odhadom podľa cost_status pôvodného behu.
Cold loads ostávajú v latencii; výber možno exportovať vrátane load_duration_s.

RAG vs. bez RAG má vlastný výber dvoch behov. Globálny filter behu/režimu sa v tejto
obrazovke nepoužíva; filter modelu a embeddingu sa používa. Porovnávajú sa spoločné
scenáre/modely, iba status ok. Priemer RAG kombinácií sa porovnáva s priemerom
kontrolných odpovedí. Kontrolnú odpoveď nepočítame osemkrát ako nezávislý výsledok.
Manifesty kontrolujeme na zhodu modelov, capu, kontextu, timeoutu, repeats a scenárov;
nie je to dôkaz plnej reprodukovateľnosti serverového modelu či hardvéru.

Korelácia je prieskumná; šesť incidentov v 480 kombináciách nie je 480 nezávislých
incidentov. Z grafu nevyplýva kauzalita ani všeobecné poradie modelov.

## Ručné hodnotenie

Vyber odpoveď v tabuľke alebo na karte Hodnotenie odpovedí. Prezri incident, rubric,
históriu a odpoveď. Zadaj päť skóre 0–2, kritickú chybu yes/no a poznámku.
Skóre 0 sa používa iba ako skutočne pridelené hodnotenie; prázdne pole nie je nula.
Celkové skóre sa počíta až po vyplnení všetkých piatich kritérií.
Technické zlyhania nehodnoť automaticky ako zlú diagnózu. Bez RAG nepenalizuj
chýbajúcu historickú citáciu, ak sa model správne odvoláva na aktuálny dôkaz.

Režim skrytej identity odstráni model a cenu z detailu/listu. Nie je to formálne slepé
randomizované hodnotenie: identita môže byť odhadnuteľná z filtrov, poradia či textu.

Uložiť hodnotenie zapisuje iba skóre a poznámky do localStorage tohto prehliadača.
Raw prompty a výsledky sa do localStorage neukladajú; po obnovení stránky ich importuj
znova. V tom istom prehliadači sa uložené skóre priradí späť k identite behu a call_id.
Lokálne uložené skóre má prednosť pred importovaným quality_review.csv.
Pri zakázanom/plnom úložisku aplikácia upozorní; skóre do zavretia zostáva v pamäti.

Pred odchodom vyber konkrétny beh vo filtri Beh a klikni Export hodnotení podľa behu.
Výsledný quality_review.csv je kompatibilný s benchmarkom; ulož ho ku správnemu behu
(pôvodný súbor si zálohuj). Import výsledkov neprepisuje VM súbory.
Vyčistiť načítané dáta vyprázdni pamäť aplikácie, uložené skóre ponechá.
Na úplné vymazanie skóre odstráň dáta stránky pre tento localhost v nastaveniach prehliadača.

Demo obsahuje iba syntetické hodnoty a je výrazne označené. Nikdy ho neprezentuj ako
výsledok vlastného benchmarku. Exportovať možno aj filtrované metriky a odpovede do CSV.

## Testy

```bash
node --test data.test.mjs
```

Overujú multiline CSV, deduplikáciu, oddelenie behov, neznáme ceny, skórovanie a párovanie
kontrol bez násobenia pozorovaní. Aplikácia neobsahuje automatického LLM hodnotiteľa.
