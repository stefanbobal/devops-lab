zaplnenie = 50
warning_limit = 80
critical_limit = 90


if zaplnenie >= critical_limit:
    print(f"KRITICKE: filesystem presiahol {critical_limit} %")
elif zaplnenie >= warning_limit:
    print(f"WARNING: filesystem presiahol {warning_limit} %")
else:
    print("Filesystem je OK!") 