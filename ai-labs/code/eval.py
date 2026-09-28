"""Lab 06: measure retrieval quality on a small test set."""
from config import SIMILARITY_THRESHOLD
from search import find_similar

# (query, domain, db_type, expected SID or None if nothing should be found)
TESTS = [
    ("backint cannot verify SSL certificate", "backup", "HANA", "Q50"),
    ("backup target storage not reachable, timeout", "backup", "HANA", "D15"),
    ("log backups are late and log volume grows", "backup", "HANA", "P20"),
    ("archive log area full, RMAN failed", "backup", "Oracle", "P11"),
    ("custom report runs heavy SQL, dialog is slow", "performance", "HANA", "P30"),
    ("indexserver crashed unexpectedly", "database", "HANA", "D50"),
    ("RFC call fails because certificate expired", "interface", "HANA", "Q11"),
    ("disk almost full on /usr/sap", "os", "HANA", "D20"),
    ("Printer on floor 2 is out of paper", None, None, None),
    ("network switch firmware upgrade planned", None, None, None),
]

correct = 0
for query, domain, db_type, expected in TESTS:
    above = [r for r in find_similar(query, domain, db_type)
             if r["similarity"] >= SIMILARITY_THRESHOLD]
    found = above[0]["sid"] if above else None
    ok = found == expected
    correct += ok
    print(f"{'OK  ' if ok else 'FAIL'}  expected={expected}  found={found}  | {query}")

print(f"\nScore: {correct}/{len(TESTS)} at threshold {SIMILARITY_THRESHOLD}")
