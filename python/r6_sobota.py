filesystem = [45, 80, 92, 79, 90]
filesystem.append(88)

for fs in filesystem:
    if fs >= 90:
        print(f"{fs} % - KRITICKE")
    elif fs >= 80:
        print(f"{fs} % - VAROVANIE")
    else:
        print(f"{fs} % - OK")

system = {"sid": "PRD", "cpu": 87, "prostredie": "produkcia"}

print(system["sid"])
print(system["cpu"])