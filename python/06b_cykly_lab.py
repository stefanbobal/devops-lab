nasetrene = [45000, 90000, 120000, 100000, 100001]

for suma in nasetrene:
    if suma > 100000:
        print(f"Mam nasetrebe {suma} USD, to mi staci!")
    elif suma > 50000:
        print(f"Mam nasetrebe {suma} USD, je to hrozne malo!")
    else:
        print(f"Mam nasetrene {suma} USD som chudobny ako rybar!")



planety = ["kasiopeja", "merkur", "venusa", "zem", "mars", "saturn", "jupiter", "uran", "neptun"]

for planeta in planety:
    if planeta == "merkur":
        print(f"Planeta {planeta} sa nachadza v slnecnej sustave")
    elif planeta == "venusa":
        print(f"Planeta {planeta} sa nachadza v slnecnej sustave")
    elif planeta == "zem":
        print(f"Planeta {planeta} sa nachadza v slnecnej sustave")
    elif planeta == "mars":
        print(f"Planeta {planeta} sa nachadza v slnecnej sustave")
    elif planeta == "saturn":
        print(f"Planeta {planeta} sa nachadza v slnecnej sustave")
    else:
        print(f"Planeta {planeta} sa nenachadza v slnecnej sustave")