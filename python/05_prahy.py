zaplnenie = 84
warning_limit = 80
critical_limit = 90


if zaplnenie >= critical_limit:
    print(f"KRITICKE: filesystem na {zaplnenie} % limit je {critical_limit} %")
elif zaplnenie >= warning_limit:
    print(f"WARNING: filesystem na {zaplnenie} % limit je {warning_limit} %")
else:
    print("Filesystem je OK!") 