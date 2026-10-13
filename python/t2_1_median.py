import statistics

casy =[190, 200, 205, 210, 220, 5000]

#priemer rucne:vsetko scitam a vydelim poctom
sucet = 0
for cas in casy:
    sucet = sucet + cas
priemer = sucet / len(casy)
print(f"Priemer rucne: {priemer} ms")


# to iste cez kniznicu + median
print(f"Priemer: {statistics.mean(casy)} ms")
print(f"Median: {statistics.median(casy)} ms")

priemer = statistics.mean(casy)
median = statistics.median(casy)

if priemer > 2 * median:
    print("Pozor: par krokov taha priemer hore!")

