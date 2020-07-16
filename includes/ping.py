from bluetooth import *

def ping(mac):
  it_went_well_flag = True
  client_socket = BluetoothSocket(RFCOMM)
  try:
    client_socket.connect((mac, 3))
  except btcommon.BluetoothError:
    it_went_well_flag = False
  finally:
    client_socket.close()
  return it_went_well_flag

