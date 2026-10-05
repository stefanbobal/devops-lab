zaplnenie = 50
limit = 80


if zaplnenie > limit:
    print("KRITICKE: filesystem je nad limitom")
elif zaplnenie == limit:
    print("POZOR: filesystem dosiahol limit")    
else:
    print("OK: filesystem je v poriadku")    