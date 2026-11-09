# Bankový agent vo Foundry: stav a ďalšie kroky

Stav k večeru 9. 11. 2026. Dokument opisuje, čo sa spravilo pri presune agenta z domáceho labu (`ai-labs/code_banka`)
do Azure AI Foundry, prečo sa to spravilo takto, čo zlyhalo a kde sa pokračuje. Návrh a bezpečnostné invarianty sú
v `../../code_banka/FOUNDRY_PORT.md`. Všetky firmy, zmluvy a čísla sú vymyslené.

---

## 1. Stav v skratke

| Vec | Stav |
| --- | --- |
| Vektorová tabuľka v Azure PostgreSQL | hotovo, 308 riadkov skopírovaných z lokálnej DB |
| Agent vo Foundry (`covenant-agent-code`, verzia 2) | beží, nasadený zo zdrojového kódu |
| T3 vo Foundry (36 dev prípadov) | **36/36**, 0 prehliadnutých porušení, 0 falošných poplachov, zhodné s domácim behom |
| T4 vo Foundry (útoky, sady A a F) | pripravené, **nespustené** |
| Testovací agent `covenant-agent-t4` (verzia 1) | nasadený, `active`, zatiaľ bez jediného volania |
| Útokové úryvky v Azure tabuľke | **neoverené**: nahrávanie padlo na hesle, či neskôr prebehlo, treba skontrolovať (sekcia 8, krok 2) |
| Nasadenie cez kontajner (ACR) | nefunguje, príčina nepotvrdená (sekcia 5) |
| T5, T6 vo Foundry | nerobené |
| Git | commitnuté 9. 11. 2026 spolu so zmazaním starého priečinka `ai-labs/foundry-agents/` |

Zajtra sa začína sekciou 8.

---

## 2. Čo agent robí a prečo je nasadený takto

Agent dostane `company_id` a `period` (napríklad `C01 2026Q1`) a vráti `breach`, `no_breach` alebo `human_review`
s dôvodmi a krokmi. Reťazec má šesť krokov: `extract` (LLM), `check_items` (kód), `retrieve` (kód a embedding),
`spec` (LLM), `verify` (kód), `evaluate` (kód). **O stave rozhoduje iba kód**, LLM len prevádza text na štruktúru.

Vo Foundry je nasadená **architektúra A** z `FOUNDRY_PORT.md`: celý reťazec je jeden nástroj.

- Medzi volajúcim a `agent.run()` nie je žiadny konverzačný model. Server (`foundry_app.py`) prijme text, overí ho,
  zavolá reťazec a vráti jeho JSON doslova. Nikto teda nemôže prepísať stav ani zmeniť poradie krokov.
- Je to **hosted agent**: vlastný kód bežiaci na infraštruktúre Foundry, nie prompt agent naklikaný v portáli.
  V portáli je viditeľný v sekcii Agents, vrátane trás (traces) každého volania.
- Vstup sa overuje regulárnym výrazom **pred** volaním reťazca, lebo `agent.load_statement()` skladá cestu k súboru
  zo vstupu. `../C01` alebo vložený pokyn skončia ako `human_review` s dôvodom `invalid_request`, bez volania modelu.
- Akákoľvek chyba končí ako `human_review` s dôvodom (fail closed). Overené v praxi: pri zlom kľúči k modelu agent
  nespadol, vrátil `human_review` s `extraction_failed`.
- Dokumenty (zmluvy, výkazy) sú súčasťou nasadeného balíka. Model ani volajúci nevyberajú, odkiaľ sa berú.
  Nevýhoda: zmena dokumentu znamená novú verziu agenta. Pre skutočné nasadenie by patrili do dôverného úložiska.

Kód reťazca je **nezmenená kópia** z `code_banka` (commit `ad984fc`). Overené 9. 11.: súbory `agent.py`, `config.py`,
`providers.py`, `covenants.py`, `sources.py`, `contract_rules.py`, `rag_prompt.py`, `search.py`, `thresholds.py`,
`thresholds.json`, `load_documents.py` a priečinok `data/` sú bajt po bajte zhodné s originálom. Prompt je verzia
`P3` s rovnakými hashmi ako v domácom behu (`spec c452f31216247933`, `extract 1036d697c7d0e062`).

---

## 3. Čo je kde

### Azure

| Zdroj | Názov | Skupina | Poznámka |
| --- | --- | --- | --- |
| Foundry účet | `stefanbobal-9304-resource` | `rg-stefan.bobal-3276` | Sweden Central |
| Foundry projekt | `stefanbobal-9304` | | endpoint `https://stefanbobal-9304-resource.services.ai.azure.com/api/projects/stefanbobal-9304` |
| Modely | `gpt-5-mini`, `text-embedding-3-small` | | GlobalStandard |
| PostgreSQL | `$AZURE_PG_SERVER` (v lokálnom `.env`) | `$AZURE_PG_RG` | PG 16, `Standard_D2ds_v4`, Sweden Central |
| Application Insights | `appi-covenant` + `law-covenant` | `rg-stefan.bobal-3276` | pripojené k projektu, zdroj trás |
| Container Registry | `acrcovenant27006` (Basic) | `rg-stefan.bobal-3276` | obraz `covenant-agent:v1`, teraz nepoužívaný |
| Connection | `agent-secrets` (Custom keys) | projekt | kľúče `openai_key`, `pg_password` |

Agenti v projekte:

| Agent | Verzie | Stav | Účel |
| --- | --- | --- | --- |
| `covenant-agent-code` | 1, 2 | `active` | hlavný agent, T3 bežal na verzii 2 |
| `covenant-agent-t4` | 1 | `active` | testovací agent pre T4, má navyše útokové dokumenty |
| `covenant-agent` | 1 až 7 | všetky `failed` | pokusy cez kontajner |
| `covenant-probe` | 1 | `failed` | diagnostická sonda (kontajner bez nastavení) |

Názov PostgreSQL servera, jeho skupina a prihlasovacie meno nie sú v repozitári. Sú v lokálnom súbore `.env`
vedľa skriptov (vzor: `.env.example`), odkiaľ si ich berú skripty aj príkazy v tomto dokumente
(`set -a; source .env; set +a`). Heslá v ňom nie sú.

Predplatné je **Free Trial** s limitom útrat. Dnes boli zaregistrovaní poskytovatelia `Microsoft.ContainerRegistry`,
`Microsoft.App`, `Microsoft.ContainerInstance`, `microsoft.insights`, `Microsoft.OperationalInsights`.

Priradené roly identity projektu: `AcrPull` a `Container Registry Repository Reader` na registry, `Foundry User`
na Foundry účte.

### Lokálne (`ai-labs/foundry_agents/banka_covenant_agent/`)

| Súbor | Účel |
| --- | --- |
| `foundry_app.py` | server (Responses protokol, port 8088), overenie vstupu, volanie reťazca |
| `foundry_deploy.py` | nasadenie (`deploy-code`, `deploy-code t4`, `deploy`, `probe`), volanie (`ask`), logy (`logs`) |
| `t3_foundry.py` | T3 proti agentovi vo Foundry |
| `t4_foundry.py` | T4 proti testovaciemu agentovi |
| `load_attacks_azure.py` | pridanie alebo zmazanie útokových úryvkov v Azure tabuľke |
| `test_foundry_app.py` | unit testy obalu (10 testov) |
| `Dockerfile`, `.dockerignore` | kontajnerová cesta (nepoužíva sa) |
| `.env` (lokálne, nie v gite), `.env.example` | názov PostgreSQL servera a prihlasovacie meno, bez hesiel |
| `requirements-foundry.txt` | závislosti agenta |
| `results/t3_foundry_foundry_run1.json` | výsledok T3 (priečinok `results/` je v `.gitignore`) |
| ostatné `.py`, `thresholds.json`, `data/` | kópia reťazca a dev dát z `code_banka` |

Skripty sa spúšťajú z virtuálneho prostredia `code_banka/.venv`. Dnes doň pribudli `azure-ai-projects` (2.10.0)
a `azure-identity`; v `code_banka/requirements.txt` nie sú.

---

## 4. Presun vektorovej databázy do Azure PostgreSQL

**Prečo:** režim `rag` potrebuje úryvky zmlúv vo vektorovej tabuľke, ktorú agent vo Foundry dosiahne.
Azure Database for PostgreSQL s rozšírením `pgvector` je najmenšia zmena: `search.py` ostáva bez úpravy, mení sa
len `PG_DSN`.

**Zdroj:** lokálny kontajner `pgvector-banka` (PG 16, pgvector 0.8.7, port 5433). Obsahuje tri tabuľky, po jednej
na embedding profil: `covenant_docs_bge`, `covenant_docs_gemini`, `covenant_docs_azure`.

**Čo sa prenieslo:** iba `covenant_docs_azure` (308 riadkov, 18 firiem: 12 dev a 6 testovacích, 1536 rozmerov,
model `text-embedding-3-small`). Vektory sa skopírovali tak, ako sú, embedding sa znova nevolal. Tabuľky pre `bge`
a `gemini` Foundry nepotrebuje.

**Ako** (na hostiteľovi nie je `psql`, použil sa klient z Docker obrazu):

```bash
set -a; source .env; set +a     # AZURE_PG_SERVER, AZURE_PG_RG, AZURE_PG_HOST, AZURE_PG_USER

# 1. povoliť vlastnú IP na firewalle servera (pozor: -s je server, --name je názov pravidla)
az postgres flexible-server firewall-rule create -g "$AZURE_PG_RG" \
  -s "$AZURE_PG_SERVER" --name allow-lab-home \
  --start-ip-address <moja IP> --end-ip-address <moja IP>

# 2. heslo do premennej, nie do súboru
read -rs PGPASSWORD; export PGPASSWORD
CONN="host=$AZURE_PG_HOST user=$AZURE_PG_USER dbname=postgres sslmode=require"

# 3. rozšírenie vector (v dumpe jednej tabuľky nie je)
docker run --rm -e PGPASSWORD pgvector/pgvector:pg16 psql "$CONN" -c 'CREATE EXTENSION IF NOT EXISTS vector;'

# 4. prenos
docker exec pgvector-banka pg_dump -U postgres --no-owner -t covenant_docs_azure postgres \
 | docker run -i --rm -e PGPASSWORD pgvector/pgvector:pg16 psql "$CONN"
```

**Kontrola:** `COPY 308`; počet riadkov lokálne aj v Azure 308, v Azure 18 firiem.

**Čo sa nespravilo:** T2 (kvalita vyhľadávania) sa proti Azure tabuľke nezopakoval. Nepriamy dôkaz, že vyhľadávanie
funguje, je T3 vo Foundry: 36/36, všetky prípady prešli krokom `retrieve`. Chunkovanie je rovnaké ako v lokálnej
`bge` tabuľke (definície delené po číslovaných bodoch, 110 z 308 riadkov má číslo bodu).

Aby sa k databáze dostal agent vo Foundry, pridalo sa pravidlo `allow-azure-services` (0.0.0.0). Stav firewallu
je však horší, než sa predpokladalo, pozri sekciu 9.

---

## 5. Nasadenie agenta vo Foundry

### 5.1 Obal reťazca

`foundry_app.py` používa knižnicu `azure-ai-agentserver-responses`. Tá poskytuje HTTP server, endpoint `/responses`,
kontrolu `/readiness` a telemetriu. Náš kód je len funkcia, ktorá z prijatého textu spraví volanie `agent.run()`.

Lokálne overené v Dockeri: `/readiness` vracia 200 a neplatný vstup (`../C01 2026Q1`) vráti `human_review`
s `invalid_request` bez volania modelu.

### 5.2 Pokus cez kontajner: nefunguje

Postup podľa dokumentácie: obraz do Azure Container Registry, potom verzia agenta s odkazom na obraz.

| Krok | Výsledok |
| --- | --- |
| `az acr create` | `MissingSubscriptionRegistration` → `az provider register --namespace Microsoft.ContainerRegistry` |
| `az acr build` (build v Azure) | `TasksOperationsNotAllowed`: Free Trial nepovoľuje ACR Tasks → lokálny `docker build` a `docker push` |
| verzia agenta 1 | `ImageError`: chýbala rola `AcrPull` (samotná `Container Registry Repository Reader` nestačila) |
| verzie 2 až 7 | všeobecný `ProvisioningError` bez podrobností |

Čo sa pri `ProvisioningError` skúsilo a nepomohlo: počkať na rozšírenie roly, rola `Foundry User` pre identitu
projektu, vytvorenie a pripojenie Application Insights, registrácia poskytovateľov `Microsoft.App`
a `Microsoft.ContainerInstance`. Sonda (`covenant-probe`: ten istý obraz bez nastavení a bez tajomstiev) padla
rovnako, čo **vylúčilo našu konfiguráciu**. Obraz sám je v poriadku (lokálne beží).

Keďže nasadenie zo zdrojového kódu v tom istom projekte funguje, **nie je príčinou predplatné ani platforma ako
celok**, ale cesta cez registry. Pravdepodobná príčina (nepotvrdená): chýba *project connection* na registry.
Návod na Terraform ju uvádza medzi predpokladmi, my sme nastavili len roly.

Poznámka: zoznam verzií (`list_versions`) ukazuje zlyhané verzie ako `active`. Skutočný stav dáva len detail
verzie (`get_version`). Skripty používajú detail.

### 5.3 Nasadenie zo zdrojového kódu: funguje

Foundry vie prijať zip so zdrojovým kódom a závislosti si nainštaluje sám (`remote_build`). Registry sa nepoužíva.

```bash
python foundry_deploy.py deploy-code
```

Skript zabalí reťazec, `data/` a `requirements.txt` (80 súborov, 89 KiB), nahrá ich cez
`create_version_from_code` (runtime `python_3_13`, vstupný bod `python foundry_app.py`) a čaká na stav `active`.
Prvé nasadenie trvalo 107 sekúnd, testovací agent 61 sekúnd. Do zipu nejde `.env`, testy, `data_test/` ani útoky.

### 5.4 Tajomstvá

Kľúč k modelu a heslo k databáze nie sú v kóde, v zipe ani v definícii agenta. Sú v connection `agent-secrets`
na projekte a agent ich dostane ako premenné prostredia cez odkazy:

```
AZURE_OPENAI_API_KEY = ${{connections.agent-secrets.credentials.openai_key}}
PGPASSWORD           = ${{connections.agent-secrets.credentials.pg_password}}
```

`PG_DSN` heslo neobsahuje, `libpq` si ho berie z `PGPASSWORD`. Platforma odkazy vyplní pri štarte relácie, takže
po oprave hodnoty v portáli stačí agenta zavolať znova, nové nasadenie netreba.

Obe prvé chyby boli preklepy pri zadávaní do portálu:

- Kľúč `openai_key` mal 83 znakov namiesto 84 → `401` v kroku `extract`.
- Heslo `pg_password` bolo tiež nesprávne (podľa tvojej opravy; výstup tejto chyby som nevidel).

Na hľadanie takýchto chýb server pri štarte zapisuje riadky `env-check`: či je premenná nastavená, jej dĺžku
a či ostala nevyplneným odkazom. Hodnotu nikdy. Čítajú sa cez `python foundry_deploy.py logs <agent> env-check`.

### 5.5 Trasy a logy

Po pripojení Application Insights ukazuje portál pri každom volaní trasu `invoke_agent`. V nej je vidieť reťazec:
`chat/completions` (krok `extract`), tri volania `embeddings` (krok `retrieve`: EBITDA, čistý dlh, limit)
a druhé `chat/completions` (krok `spec`). Kroky `check_items`, `verify` a `evaluate` v trase nie sú, lebo sú to
výpočty bez sieťového volania. Dotaz na waiver sa posiela len vtedy, keď firma má dokument typu waiver.

Príklad jedného volania: spolu 17,8 s, z toho volania modelu asi 11,5 s, zvyšok hlavne studený štart relácie.

---

## 6. Testy

### 6.1 T3 vo Foundry (celý reťazec, 36 dev prípadov)

```bash
python t3_foundry.py --tag foundry_run1 --compare ../../code_banka/results/t3_chain_h_azure_dev.json
```

| | Foundry, `covenant-agent-code` v2 | Domáci lab, `t3_chain_h_azure_dev` |
| --- | --- | --- |
| Orchestrácia | Foundry hosted agent | lokálny proces |
| LLM | `gpt-5-mini` | `gpt-5-mini` |
| Embedding | `text-embedding-3-small` | `bge-m3` |
| Prompt | P3, rovnaké hashe | P3 |
| Správne stavy | 36/36 | 36/36 |
| Prehliadnuté porušenia | 0 | 0 |
| Falošné poplachy | 0 | 0 |
| `human_review` (očakávané 3) | 3 | 3 |
| Zhoda vypočítaných hodnôt | 35/36 | 35/36 |
| Zlyhané volania | 0 | nemerané |
| Čas na prípad | medián 19,6 s (16,5 až 26,0) | priemer 13,3 s |

- Žiadny prípad sa od domáceho behu nelíši.
- Tri `human_review` majú správne dôvody: `C09-2026Q2` chýbajúca položka odpisov, `C09-2026Q3` a `C11-2026Q3`
  pásmo 2 % pri limite. O všetkých rozhodol krok `evaluate`, model nezlyhal.
- Rozdiel asi 6 až 7 sekúnd na prípad je štart novej relácie pri každom volaní.
- Beh bol spustený dvakrát. Prvý dal vo výpise terminálu tiež 36/36, ale skript spadol pri zápise výsledkov
  (chyba v skripte, opravená), takže uložený je len druhý beh. Nie je to plnohodnotné T5.

**Obmedzenie porovnania:** oproti domácemu behu sa líši orchestrácia aj embedding. Zhoda 36/36 hovorí, že ani jedna
zmena výsledok nepokazila, ale nedajú sa od seba oddeliť.

### 6.2 T4 vo Foundry (útoky): pripravené, nespustené

Útokové firmy majú identifikátory ako `C01_S1` a vlastné dokumenty v `code_banka/data_attacks_a` (55 prípadov)
a `data_attacks_f` (45 prípadov). Skripty ich čítajú priamo odtiaľ, aby oba laby útočili rovnakými súbormi.

Čo bolo treba pripraviť:

1. **Úryvky útokových dokumentov v Azure tabuľke** (`load_attacks_azure.py`): 100 firiem, 1 735 úryvkov. Skript
   len pridáva riadky, pôvodných 308 sa nedotkne, a hotové firmy pri opakovaní preskočí.
2. **Testovací agent s útokovými dokumentmi** (`deploy-code t4`): ten istý kód, navyše priečinky útokových sád
   a premenná `COVENANT_DATA_DIRS`. Hlavný agent útokové dokumenty nemá. Súbory s očakávanými odpoveďami do zipu
   nejdú.
3. **Úprava `foundry_app.py`**: prijíma aj `C01_S1` (vzor `C\d{2}(_[A-Z]\d)?`, stále bez znakov cesty) a do výstupu
   pridáva `retrieval_check` s počtom úryvkov cudzej firmy a poznámok analytika. Meria sa to v agentovi, kde
   vyhľadávanie beží, lebo zvonka to vidieť nie je.
4. **Vyhodnotenie** (`t4_foundry.py`): rovnaké pravidlá ako `code_banka/t4_attacks.py`. Overené prehraním
   310 riadkov z domácich T4 výsledkov: verdikty sa zhodli vo všetkých. Zlyhané volanie sa počíta zvlášť ako
   `error`, nie ako úspešný útok ani ako `human_review`.

Čo treba vedieť:

- **Domáce porovnanie s rovnakým modelom neexistuje.** Doma bežal T4 s haiku a qwen38 (0 úspešných z 378, asi
  19 % `human_review`). S `gpt-5-mini` to bude prvé meranie.
- **Sada F** vychádza z odložených testovacích firiem. Spustiť raz, nič na nej neladiť.
- Útokové riadky sú v tej istej tabuľke ako ostatné. Oddeľuje ich povinný filter na firmu, rovnako ako doma.

### 6.3 Čo sa netestovalo

T5 (opakovateľnosť) a T6 (latencia, tokeny, cena) vo Foundry, T2 proti Azure tabuľke, a architektúra B.

---

## 7. Problémy a riešenia (prehľad)

| # | Príznak | Príčina | Riešenie |
| --- | --- | --- | --- |
| 1 | `psql: command not found` | klient nie je na hostiteľovi | `psql` a `pg_dump` z Docker obrazu |
| 2 | `firewall-rule create` žiada `--server-name` | `-n` je názov pravidla | server cez `-s` |
| 3 | `MissingSubscriptionRegistration` | nové predplatné | `az provider register` |
| 4 | `TasksOperationsNotAllowed` | Free Trial bez ACR Tasks | lokálny `docker build` a `push` |
| 5 | `ImageError` pri verzii agenta | chýbala rola `AcrPull` | priradiť identite projektu |
| 6 | `ProvisioningError` pri kontajneri | nepotvrdené, asi chýba connection na registry | obídené nasadením zo zdrojového kódu |
| 7 | zoznam verzií hlási `active`, volanie vracia 409 | zoznam neukazuje skutočný stav | používať `get_version` |
| 8 | `401` v kroku `extract` | kľúč v connection mal 83 znakov namiesto 84 | zadať znova, overiť cez `env-check` |
| 9 | chyba databázy po oprave kľúča | zlé heslo v connection | zadať znova |
| 10 | `logs` vypísal prázdno | skript čítal najstaršiu reláciu | opravené, berie najnovšiu |
| 11 | `t3_foundry.py` spadol po 36 prípadoch | objekt SDK v metadátach sa nedal uložiť | opravené, metadáta sa overia pred behom |
| 12 | `load_attacks_azure.py`: `password authentication failed` | zlé heslo v `PGPASSWORD` v termináli | zadať znova, overiť krátkym pripojením |

---

## 8. Ako pokračovať

### Príprava terminálu

```bash
cd ~/devops-lab/ai-labs/foundry_agents/banka_covenant_agent
source ../../code_banka/.venv/bin/activate
az account show -o table                     # ak prihlásenie vypršalo: az login
export $(grep -E '^(AZURE_OPENAI_ENDPOINT|AZURE_OPENAI_LLM_DEPLOYMENT|AZURE_OPENAI_EMBED_DEPLOYMENT)=' ../../code_banka/.env | xargs)
set -a; source .env; set +a                  # názov PostgreSQL servera pre príkazy az
read -rs PGPASSWORD; export PGPASSWORD       # heslo admina databázy, potrebné len pre load_attacks_azure.py
```

Ak bol PostgreSQL server večer zastavený (sekcia 10), najprv ho spusti.

### Kroky

1. **Overiť, že agent žije:** `python foundry_deploy.py ask C01 2026Q1 covenant-agent-code` → `no_breach`.
2. **Skontrolovať útokové úryvky v tabuľke:** `python load_attacks_azure.py --dry-run`. S nastaveným heslom vypíše
   počet riadkov a koľko firiem ešte treba pridať. Cieľový stav je 2 043 riadkov (308 + 1 735) a 118 firiem.
   Ak niečo chýba: `python load_attacks_azure.py` (odhadom 5 až 10 minút).
3. **Jedno skúšobné volanie testovacieho agenta:** `python foundry_deploy.py ask C01_S1 2026Q3 covenant-agent-t4`.
   Vo výstupe má byť `retrieval_check` s `foreign_chunks: 0` a `notes_chunks: 0`.
4. **T4:** `python t4_foundry.py --tag foundry_af` (100 prípadov, odhadom 35 minút). Hlavné číslo je
   `successful attacks`, cieľ 0. Stĺpec `leak` má byť 0.
5. **Zmazať útokové riadky:** `python load_attacks_azure.py --remove`.
6. **Zosúladiť hlavného agenta s kódom:** `covenant-agent-code` beží na verzii 2 so starším `foundry_app.py`.
   Testovací agent má novší obal (reťazec je rovnaký). `python foundry_deploy.py deploy-code` vytvorí verziu 3;
   potom krátko zopakovať T3, aby výsledok platil pre aktuálny kód.
7. **T5:** T3 aspoň trikrát s rôznymi tagmi (`t3_foundry.py` nemá `--repeats`).
8. **Upratanie v Azure** (sekcia 9) a commit nových výsledkov.
9. **Voliteľne:** kontajnerová cesta (pridať project connection na registry) a Terraform. Terraform sa dá použiť
   cez provider AzAPI (`azapi_data_plane_resource`, typ `Microsoft.Foundry/agents@v1`), ale oficiálny návod pokrýva
   len kontajnerový obraz, nie nahratie zdrojového kódu.

---

## 9. Otvorené veci a riziká

- **Firewall PostgreSQL je otvorený celému internetu.** Na serveri je pravidlo `AllowAll`
  (0.0.0.0 až 255.255.255.255), ktoré sme nevytvorili my. Popri ňom sú `AllowAllAzureServicesAndResourcesWithinAzureIps`,
  naše `allow-azure-services` a `allow-lab-home`. Jedinou ochranou databázy je teda heslo. Dáta sú vymyslené, ale
  pravidlo `AllowAll` treba zvážiť zmazať. Agent vo Foundry potrebuje len prístup pre služby Azure.
- **Starý priečinok `ai-labs/foundry-agents/`** (so spojovníkom, pokus s prompt agentom) bol zámerne zmazaný.
  Nahrádza ho `ai-labs/foundry_agents/`. V histórii gitu ostáva (commit `bc181f4`).
- **Výsledky testov nie sú v gite.** `results/` je v `.gitignore`, rovnako ako v `code_banka`. Súbor
  `results/t3_foundry_foundry_run1.json` existuje len lokálne.
- **Zlyhaní agenti** `covenant-agent` (7 verzií) a `covenant-probe` ostali v projekte. Nič nestoja.
- **Registry `acrcovenant27006`** sa nepoužíva a míňa kredit. Zmazať, ak sa ku kontajneru nevrátime.
- **Hlavný a testovací agent majú rôzne verzie obalu** (krok 6 v sekcii 8).
- **`data/expected.json`** (očakávané odpovede dev sady) je súčasťou nasadeného balíka. Agent ho nečíta, ale do
  produkčného balíka nepatrí.

---

## 10. Vypnutie a zapnutie

Agenti vo Foundry sa vypínať nemusia: relácia sa po 15 minútach nečinnosti uvoľní a neúčtuje sa.

Kredit míňa hlavne PostgreSQL server (`Standard_D2ds_v4`). Zastavenie zároveň zavrie otvorený firewall:

```bash
# večer
set -a; source .env; set +a
az postgres flexible-server stop  -g "$AZURE_PG_RG" -n "$AZURE_PG_SERVER"
docker stop pgvector-banka        # lokálna DB, voliteľné

# ráno
set -a; source .env; set +a
az postgres flexible-server start -g "$AZURE_PG_RG" -n "$AZURE_PG_SERVER"
```

Zastavený server sa po 7 dňoch spustí sám. Kým je zastavený, agent vracia `human_review` s `retrieval_failed`,
čo je správne správanie.

---

## 11. Čo sa dá a nedá tvrdiť

Dá sa:

- Agent beží vo Foundry ako hosted agent s nezmeneným reťazcom a rovnakým promptom ako v domácom labe.
- Na 36 dev prípadoch dáva rovnaké stavy ako domáci beh s tým istým modelom: 36/36, žiadne prehliadnuté porušenie.
- Tajomstvá nie sú v kóde ani v nasadenom balíku.
- Pri chybe modelu alebo databázy agent nespadne a neháda, vráti `human_review`.

Nedá sa (zatiaľ):

- Že Foundry verzia odoláva útokom: T4 vo Foundry nebežal.
- Že je opakovateľná: uložený je jeden beh.
- Čokoľvek o skutočných zmluvách a PDF: dáta sú generované jednou šablónou.
- Že rozdiel v čase je daný Foundry: T6 sa nemeral, 19,6 s je čas z pohľadu volajúceho vrátane štartu relácie.
- Prečo zlyháva kontajnerová cesta: príčina je len odhad.
