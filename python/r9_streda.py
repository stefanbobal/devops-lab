matica = {"tp":28, "fn":2, "fp":10, "tn":60}

print(f"TP: {matica['tp']}, FN: {matica['fn']}, FP: {matica['fp']}, TN: {matica['tn']}")

spolu = matica['tp'] + matica['fn'] + matica['fp'] + matica['tn']

print(f"Spolu: {spolu}")

if matica['fn'] >= 1:
    print("POZOR: detektor prehliadol skutocny problem!")
else:
    print("Vsetko v poradku!")