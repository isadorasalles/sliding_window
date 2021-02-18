import socket
import threading
import sys
import struct

def receive(csock, size):
    # while True:
    data = csock.recv(size)
        # if len(data) == 0:
        #     break
    return data

def connection_msg(csock, udp_port):
    connection_type = 2
    message = b''
    message += struct.pack('h', connection_type)
    message += struct.pack('i', udp_port)
    csock.sendall(message)

def udp_connection():
    sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_udp.bind(('localhost', 0))
    print(sock_udp.getsockname())
    return (sock_udp, sock_udp.getsockname()[1])

def client_thread(csock, addr):
    
    hello = receive(csock, 2)
    type_msg = struct.unpack('h', hello)[0]
    
    if type_msg == 1:
        sock_udp, udp_port = udp_connection()
        connection_msg(csock, udp_port)
        info_file = receive(csock, 25)
        length = len(info_file) - 10
        info_unpack = struct.unpack('=H'+str(length)+'sQ', info_file)
    
        # alocar estruturas de dados para janela deslizante
        if info_unpack[0] == 3:
            ok = 4
            msg = struct.pack('h', ok)
            csock.sendall(msg)
            print(info_unpack)
            sock_udp.listen() # listen udp?

    csock.close()

def main():
    port = sys.argv[1]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', int(port)))
    s.listen()
    while(1):
        csock, addr = s.accept()
        thread = threading.Thread(target=client_thread, args=(csock, addr))
        thread.start()


if __name__ == "__main__":
    main()
