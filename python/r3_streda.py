casy = [300, 1200, 650, 180, 1000]

for cas in casy:
    if cas >= 1000:
        print(f"{cas} ms - POMALE")
    elif cas >= 500:
        print(f"{cas} ms - SPOMALENE")
    else:
        print(f"{cas} ms - OK")