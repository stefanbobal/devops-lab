TESTS = [
    # --- normal (14): bežné otázky, slabšie pokryté témy ---
    ('full data backup aborted, storage quota for backups reached', 'backup', 'HANA', {"INC-0013"}, 'normal'),
    ('RMAN full backup exceeds the maintenance window, only one channel used', 'backup', 'Oracle', {"INC-0019"}, 'normal'),
    ('users wait when saving, one session holds a row lock for hours', 'performance', 'Oracle', {"INC-0036"}, 'normal'),
    ('application servers cannot connect to the database after reboot, listener stopped', 'database', 'Oracle', {"INC-0047"}, 'normal'),
    ('HANA data disk almost full, unused tables never cleaned up', 'database', 'HANA', {"INC-0038"}, 'normal'),
    ('HANA database in lockdown, temporary license expired, only SYSTEM can log on', None, None, {"INC-0042"}, 'normal'),
    ('HANA host is swapping heavily because another process eats memory', 'os', 'HANA', {"INC-0064"}, 'normal'),
    ('sapdata filesystem 99 percent full, tablespace autoextend cannot grow', 'os', 'Oracle', {"INC-0069"}, 'normal'),
    ('outbound SOAP calls to partner return 401 unauthorized after password expiry', None, None, {"INC-0054"}, 'normal'),
    ('batch interfaces fail because technical user got locked after wrong passwords', 'security', 'HANA', {"INC-0077"}, 'normal'),
    ('scheduled job fails with logon error after the job step user changed password', 'jobs', 'Oracle', {"INC-0084"}, 'normal'),
    ('short dumps after kernel patch, mixed kernel versions in exe directory', 'basis', 'HANA', {"INC-0087"}, 'normal'),
    ('work processes cannot connect after Oracle patch, kernel client not updated', 'basis', 'Oracle', {"INC-0090"}, 'normal'),
    ('savepoint takes very long, critical phase is blocked', 'database', 'HANA', {"INC-0100"}, 'normal'),

    # --- paraphrase (8): ako to píšu ľudia, bez slov z titulkov ---
    ('backups are slow to even start, nobody cleaned entries from years ago', 'backup', 'HANA', {"INC-0014"}, 'paraphrase'),
    ('only colleagues in one office complain about slow system, everyone else is fine', 'performance', 'HANA', {"INC-0117"}, 'paraphrase'),
    ('it takes half a minute until the SAP GUI logon screen appears', 'performance', 'HANA', {"INC-0097"}, 'paraphrase'),
    ('at month end our overnight processing needs double the time and disks look busy', 'performance', 'Oracle', {"INC-0007"}, 'paraphrase'),
    ('database server waits a lot for disk, one storage path is missing', 'os', 'Oracle', {"INC-0071"}, 'paraphrase'),
    ('someone tried to log on as SAP* from a machine we do not know', 'security', 'HANA', {"INC-0092"}, 'paraphrase'),
    ('we received the same customer orders twice from the partner', 'interface', 'HANA', {"INC-0153"}, 'paraphrase'),
    ('standard cleanup jobs never ran after we moved the system, log tables keep growing', 'jobs', 'HANA', {"INC-0186"}, 'paraphrase'),

    # --- trap (6): rovnaké slová, iná príčina ---
    ('upload of payment files to the bank fails with SSL error, our client certificate expired', 'interface', 'HANA', {"INC-0150"}, 'trap'),
    ('backup to cloud storage rejected, request time skewed, host clock 15 minutes off', 'backup', 'HANA', {"INC-0108"}, 'trap'),
    ('SAP GUI logon with SNC fails because the PSE on the application server expired', 'security', 'HANA', {"INC-0074"}, 'trap'),
    ('database cannot call external HTTPS services, wallet certificate verification error', 'security', 'Oracle', {"INC-0091"}, 'trap'),
    ('archivelog backup cannot run, tape library is offline', 'backup', 'Oracle', {"INC-0020"}, 'trap'),
    ('backint agent disappeared during peak memory usage, killed by the kernel', 'backup', 'HANA', {"INC-0105"}, 'trap'),

    # --- slovak (6) ---
    ('filesystem /hana/shared je plný starými inštalačnými médiami', 'os', 'HANA', {"INC-0063"}, 'slovak'),
    ('po zmene parametra optimalizéra robí Oracle samé full table scany', 'performance', 'Oracle', {"INC-0128"}, 'slovak'),
    ('inštancia po reštarte nenabehne, /hana/shared nie je pripojený', 'os', 'HANA', {"INC-0166"}, 'slovak'),
    ('ročná uzávierka skončila chybou, vyčerpal sa číselný rad', 'jobs', 'HANA', {"INC-0094"}, 'slovak'),
    ('prenos súborov cez SFTP zlyhal, zmenil sa host key servera', 'interface', 'HANA', {"INC-0056"}, 'slovak'),
    ('tlačiť sa nedá, vyčerpali sa čísla spoolu', None, None, {"INC-0082"}, 'slovak'),

    # --- nothing (6): správne = nič nenájsť ---
    ('What is a good recipe for goulash?', None, None, None, 'nothing'),
    ('Company Christmas party is booked for December', None, None, None, 'nothing'),
    ('Laptop battery drains too fast after Windows update', None, None, None, 'nothing'),
    ('Microsoft Teams meeting audio is choppy', None, None, None, 'nothing'),
    ('Kubernetes pod keeps restarting with CrashLoopBackOff', 'os', 'HANA', None, 'nothing'),
    ('How do I reset the Wi-Fi password in the guest network?', 'security', 'HANA', None, 'nothing'),
]