import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.bind(("", 0))

try:
    sock.sendto(b"test", ("<broadcast>", 15000))
    print("Broadcast successful on <broadcast>")
except Exception as e:
    print(f"Error on <broadcast>: {e}")

try:
    sock.sendto(b"test", ("255.255.255.255", 15000))
    print("Broadcast successful on 255.255.255.255")
except Exception as e:
    print(f"Error on 255.255.255.255: {e}")
