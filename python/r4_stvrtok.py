cpu = [50, 97, 88, 85, 12]
cpu.append(95)
cpu.append(85)

for proc in cpu:
    if proc >= 95:
        print(f"{proc} % - KRITICKE!" )
    elif proc >= 85:
        print(f"{proc} % - VAROVANIE!")
    else:
        print(f"{proc} % - OK!")
