import statistics

casy = [180, 190, 195, 200, 200, 205, 205, 210, 210, 215,
        220, 220, 230, 240, 250, 260, 300, 450, 900, 4000]

hranice = statistics.quantiles(casy, n=100, method="inclusive")

p50 = hranice[49]
p95 = hranice[94]
p99 = hranice[98]

print(f"Počet meraní: {len(casy)}")
print(f"p50: {p50} ms")
print(f"p95: {p95} ms")
print(f"p99: {p99} ms")
print(f"Medián na kontrolu: {statistics.median(casy)} ms")