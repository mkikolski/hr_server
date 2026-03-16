import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    # also try SO_BROADCAST just in case
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
except Exception:
    pass

sock.bind(("0.0.0.0", 15000))
print("Listening for UDP beacon on port 15000...")
while True:
    try:
        data, addr = sock.recvfrom(1024)
        print(f"Received beacon from {addr}: {data.decode('utf-8')}")
    except Exception as e:
        print(f"Error: {e}")
