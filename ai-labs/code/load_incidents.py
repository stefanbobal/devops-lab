"""Lab 03: create the incident_memory table and load fictional historical incidents."""
import numpy as np
import ollama
import psycopg
from pgvector.psycopg import register_vector

from config import EMBED_DIM, EMBED_MODEL, PG_DSN

# (sid, domain, db_type, date, title, evidence, root_cause_status, resolution)
INCIDENTS = [
    ("Q50", "backup", "HANA", "2026-09-10", "HANA Backup Failure",
     "Data backup failed. Backint returned SSL handshake error. backup.log shows failed external backup call.",
     "CONFIRMED", "Renewed expired client certificate for backint agent."),
    ("D15", "backup", "HANA", "2026-08-22", "HANA Backup Failure",
     "Log backups piling up. Backint could not reach backup target. Network timeout to storage endpoint.",
     "CONFIRMED", "Storage team restored backup target availability."),
    ("P20", "backup", "HANA", "2026-07-14", "HANA log backup overdue",
     "Log backup interval exceeded. Log volume filling up. Backint process hung.",
     "NOT_CONFIRMED", "Restarted backint agent, backups resumed."),
    ("P11", "backup", "Oracle", "2026-06-03", "Oracle RMAN backup failed",
     "RMAN job ended with error. Archive log destination full.",
     "CONFIRMED", "Cleaned archive log destination and added space."),
    ("P30", "performance", "HANA", "2026-09-02", "High dialog response time",
     "Dialog response time above 2 seconds. Most work processes busy. Expensive SQL from a custom report.",
     "CONFIRMED", "Stopped long-running custom report and optimized its SQL."),
    ("Q30", "performance", "HANA", "2026-08-11", "SAP system slow for users",
     "Users report slowness. High CPU on HANA host. Delta merge running during business hours.",
     "NOT_CONFIRMED", "Rescheduled delta merge outside business hours."),
    ("P40", "performance", "Oracle", "2026-07-31", "Long running batch jobs",
     "Month-end batch jobs running twice as long. Database wait events on I/O.",
     "CONFIRMED", "Infrastructure team fixed storage I/O bottleneck."),
    ("P50", "database", "HANA", "2026-08-28", "HANA memory allocation limit reached",
     "Column store unloads. Out of memory dumps. Large table fully loaded into memory.",
     "CONFIRMED", "Partitioned the large table and raised allocation limit."),
    ("D50", "database", "HANA", "2026-06-19", "HANA indexserver restart",
     "Indexserver crashed and restarted. Crash dump matches a known bug in the revision.",
     "CONFIRMED", "Applied HANA revision update recommended by SAP Note."),
    ("Q11", "interface", "HANA", "2026-09-15", "RFC connection failure",
     "RFC destination to external system failing. Certificate in STRUST expired, SSL handshake fails.",
     "CONFIRMED", "Imported new certificate in STRUST."),
    ("P60", "interface", "HANA", "2026-05-27", "IDoc processing stuck",
     "IDocs in status 64 not processed. Background job for RBDAPP01 not scheduled.",
     "CONFIRMED", "Rescheduled IDoc processing job."),
    ("D20", "os", "HANA", "2026-08-05", "Filesystem /usr/sap almost full",
     "Filesystem usage at 95 percent. Old trace files and work directory logs accumulated.",
     "CONFIRMED", "Cleaned old traces and set up housekeeping."),
]


def build_memory_text(domain, db_type, title, evidence, resolution):
    """Compact, normalized text that gets embedded (not raw logs)."""
    return (f"Domain: {domain}\nDatabase: {db_type}\nTitle: {title}\n"
            f"Evidence: {evidence}\nResolution: {resolution}")


conn = psycopg.connect(PG_DSN, autocommit=True)
conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
register_vector(conn)

conn.execute("DROP TABLE IF EXISTS incident_memory")
conn.execute(f"""
    CREATE TABLE incident_memory (
        id serial PRIMARY KEY,
        sid text, domain text, db_type text, incident_date date,
        title text, evidence text, root_cause_status text, resolution text,
        embedding_text text,
        embedding_model text,
        embedding vector({EMBED_DIM})
    )
""")

for sid, domain, db_type, date, title, evidence, status, resolution in INCIDENTS:
    text = build_memory_text(domain, db_type, title, evidence, resolution)
    vector = ollama.embed(model=EMBED_MODEL, input=text)["embeddings"][0]
    conn.execute(
        """INSERT INTO incident_memory
           (sid, domain, db_type, incident_date, title, evidence,
            root_cause_status, resolution, embedding_text, embedding_model, embedding)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (sid, domain, db_type, date, title, evidence, status, resolution,
         text, EMBED_MODEL, np.array(vector)),
    )
    print("Stored:", sid, title)

print("Done.")
