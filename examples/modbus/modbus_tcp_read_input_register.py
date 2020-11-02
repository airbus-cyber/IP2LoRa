#!/usr/bin/python3
# scripts/examples/simple_tcp_client.py
import socket
import argparse

from umodbus import conf
from umodbus.client import tcp


parser = argparse.ArgumentParser(description="Modbus read input register client")
parser.add_argument('-H', '--host',  type=str, help="IP of modbus server")
parser.add_argument('-p', '--port',  type=int, help="Port of modbus server (Ex: 502)")
parser.add_argument('-s', '--slaveid',  type=int, help="Slave ID")
parser.add_argument('-a', '--address',  type=int, help="Starting address")
parser.add_argument('-q', '--quantity',  type=int, help="Quantity")


args = parser.parse_args()


# Enable values to be signed (default is False).
conf.SIGNED_VALUES = True

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((args.host, args.port))

# Returns a message or Application Data Unit (ADU) specific for doing
# Modbus TCP/IP.
message = tcp.read_input_registers(slave_id=args.slaveid, starting_address=args.address, quantity=args.quantity)

# Response depends on Modbus function code. This particular returns the
# amount of coils written, in this case it is.
response = tcp.send_message(message, sock)
print(response)

sock.close()