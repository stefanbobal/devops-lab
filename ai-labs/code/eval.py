"""Lab 06: measure retrieval quality on a test set (200 fictional incidents)."""
from config import EMBED_MODEL, SIMILARITY_THRESHOLD
from search import find_similar

# (query, domain, db_type, acceptable incident IDs, or None if nothing should be found)
TESTS = [
    ('backint SSL handshake error, client certificate expired', 'backup', 'HANA', {"INC-0001"}),
    ('backup fails: unable to get local issuer certificate', 'backup', 'HANA', {"INC-0101"}),
    ('backup endpoint certificate name does not match host name', 'backup', 'HANA', {"INC-0102"}),
    ('backup target storage not reachable, timeout', 'backup', 'HANA', {"INC-0002"}),
    ('log backups are late and log volume grows', 'backup', 'HANA', {"INC-0003", "INC-0018"}),
    ('archive destination full, archiver stuck, users cannot commit', 'backup', 'Oracle', {"INC-0022", "INC-0004"}),
    ('RMAN fails with ORA-19809, recovery area full', 'backup', 'Oracle', {"INC-0109"}),
    ('custom report runs heavy SQL, dialog is slow', 'performance', 'HANA', {"INC-0005"}),
    ('users complain everything takes forever, delta merge during the day', 'performance', 'HANA', {"INC-0006"}),
    ('commits take long, log file sync waits', 'performance', 'Oracle', {"INC-0033"}),
    ('queries slow because optimizer statistics are old', 'performance', 'Oracle', {"INC-0034"}),
    ('users cannot save, enqueue table is full', 'performance', 'HANA', {"INC-0031"}),
    ('indexserver crashed unexpectedly', 'database', 'HANA', {"INC-0009"}),
    ('out of memory because one query used huge memory', 'database', 'HANA', {"INC-0131", "INC-0008"}),
    ('tablespace full, inserts fail with ORA-01653', 'database', 'Oracle', {"INC-0046"}),
    ('batch job failed with snapshot too old', 'database', 'Oracle', {"INC-0139", "INC-0049"}),
    ('RFC call fails because certificate expired in STRUST', 'interface', 'HANA', {"INC-0010"}),
    ('mails not sent, SMTP TLS handshake fails', 'interface', 'Oracle', {"INC-0157"}),
    ('IDocs stuck in status 64', 'interface', 'HANA', {"INC-0011"}),
    ('partner changed server certificate, HTTPS call fails', 'interface', 'HANA', {"INC-0055"}),
    ('disk almost full on /usr/sap', 'os', 'HANA', {"INC-0012"}),
    ('host clock is wrong, SSL logons fail', 'os', 'HANA', {"INC-0065"}),
    ('transparent huge pages cause latency spikes', 'os', 'HANA', {"INC-0165"}),
    ('browser shows certificate error on web dispatcher', 'security', 'HANA', {"INC-0173", "INC-0075"}),
    ('SAML SSO stopped working after identity provider certificate renewal', 'security', 'HANA', {"INC-0073"}),
    ('transport import failed, object locked in another request', 'basis', 'HANA', {"INC-0085"}),
    ('jobs stay in status released, no background work processes', 'jobs', 'HANA', {"INC-0080"}),
    ('záloha HANA zlyhala, certifikát backint agenta vypršal', 'backup', 'HANA', {"INC-0001"}),
    ('používatelia sa sťažujú, že systém je pomalý počas mesačnej uzávierky', 'performance', 'HANA', {"INC-0124"}),
    ('certificate verify failed during data backup', None, None, {"INC-0101", "INC-0001"}),
    ('Printer on floor 2 is out of paper', None, None, None),
    ('network switch firmware upgrade planned', None, None, None),
    ('office coffee machine needs descaling', None, None, None),

]

correct = 0
for query, domain, db_type, expected in TESTS:
    above = [r for r in find_similar(query, domain, db_type)
             if r["similarity"] >= SIMILARITY_THRESHOLD]
    found = above[0]["incident_id"] if above else None
    score = f"{above[0]['similarity']:.2f}" if above else "  - "
    ok = (found is None) if expected is None else (found in expected)
    correct += ok
    exp_txt = "none" if expected is None else "/".join(sorted(expected))
    print(f"{'OK  ' if ok else 'FAIL'}  expected={exp_txt:<19} found={str(found):<9} {score}  | {query}")

print(f"\nModel: {EMBED_MODEL}")
print(f"Score: {correct}/{len(TESTS)} at threshold {SIMILARITY_THRESHOLD}")