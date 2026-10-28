pouzitie = [72, 88, 93, 80, 90]

for util in pouzitie:
    if util >= 90:
        print(f"{util} % - KRITICKE")
    elif util >= 80:
        print(f"{util} % - VAROVANIE")
    else:
        print(f"{util} % - OK")