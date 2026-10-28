pouzitie = [45, 82, 91, 67, 95]

for util in pouzitie:
    if util > 90:
        print(f"KRITICKE: {util} %")
    elif util > 80:
        print(f"VAROVANIE {util} %")
    else:
        print(f"OK {util} %")