# Zaplnenie filesystémov v percentách (vymyslené dáta)
filesystems = {
    "/": 45,
    "/usr/sap": 72,
    "/hana/data": 91,
    "/hana/log": 55,
    "/backup": 97,
    "/sapmnt": 88,
}

limit = 70

for mount, usage in filesystems.items():
    if usage > limit:
        print(f"KRITICKÉ: {mount} je zaplnený na {usage} %")
    else:
        print(f"OK: {mount} ({usage} %)")
print (f"Počet filesystémov: {len(filesystems)}")
