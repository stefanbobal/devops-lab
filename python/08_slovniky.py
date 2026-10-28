system = {"sid": "PRD", "cpu": 88, "databaza": "ORACLE", "prostredie": "produkcia"}

print(system["sid"])
print(system["databaza"])

print(f"System {(system["sid"])} bezi na {(system["databaza"])} a ma CPU {(system["cpu"])} %")
