filesystemy = ["/usr/sap", "/hana/data", "/hana/log", "/hana/shared"]
filesystemy.append("/sapmnt")

for fs in filesystemy:
    print(fs)

print(f"Pocet filesystemov: {len(filesystemy)}")

instancia = "00"
print(f"Instancia {instancia} bezi")

