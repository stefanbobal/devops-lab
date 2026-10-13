mounty = ["/", "/usr/sap", "/hana/data", "/hana/log"]

for mount in mounty:
    print(f"Kontrolujem {mount}")

    print("Hotovo")

vyuzitie = [45, 72, 91, 30, 67, 85]

for percento in vyuzitie:
    if percento > 90:
        print(f"{percento} % - CRITICAL")
    elif percento > 70:
        print(f"{percento} % - WARNING")
    else:
        print(f"{percento} % - OK!") 



