from bluetooth import *

print("performing inquiry...")

nearby_devices = discover_devices()

print("found %d devices" % len(nearby_devices))

for addr in nearby_devices:
    print(addr)
