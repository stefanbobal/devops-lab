def moze_zavriet(alert):
    return alert["sid"] == "DEV" and alert["zavaznost"] == "P3"

alert1 = {"sid": "DEV", "zavaznost": "P3"}
alert2 = {"sid": "PRD", "zavaznost": "P3"}
alert3 = {"sid": "DEV", "zavaznost": "P1"}

print(moze_zavriet(alert1))  # True
print(moze_zavriet(alert2))  # False
print(moze_zavriet(alert3))  # False