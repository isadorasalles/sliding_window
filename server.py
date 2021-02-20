import socket
import threading
import sys
import struct

MAX_SIZE = 3

def udp_connection(ip_type):
    if ip_type == 6:
        sock_udp = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    else:
        sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_udp.bind(('localhost', 0))
    return (sock_udp, sock_udp.getsockname()[1])

def sliding_window(sock_udp, sock_tcp, fname, length):
    if length % MAX_SIZE == 0:
        output = [str("") for _ in range(int(length/MAX_SIZE))]
    else: 
        output = [str("") for _ in range(int(length/MAX_SIZE)+1)]

    count = 0
    while count < length:
        data = sock_udp.recv(11) # 1008?
        payload_size = len(data) - 8
        count += payload_size
        print(struct.unpack('=HIH'+str(payload_size)+'s', data))
        file_data = struct.unpack('=HIH'+str(payload_size)+'s', data)

        if file_data[0] == 6:
            ack = b''
            ack += struct.pack('H', 7)
            ack += struct.pack('I', file_data[1])
            output[file_data[1]] = file_data[3].decode()
            sock_tcp.send(ack)
    
    with open("output.txt", "w") as out:
        for chunks in output:
            out.write(chunks)

    print(output)

def client_thread(sock_tcp, addr, ip_type):
    hello = sock_tcp.recv(2)
    type_msg = struct.unpack('h', hello)[0]

    if type_msg == 1:
        sock_udp, udp_port = udp_connection(ip_type)
        connection = b''
        connection += struct.pack('h', 2)
        connection += struct.pack('i', udp_port)
        sock_tcp.send(connection)
        info_file = sock_tcp.recv(25)
        length = len(info_file) - 10
        info_unpack = struct.unpack('=H'+str(length)+'sQ', info_file)

        if info_unpack[0] == 3:
            ok = struct.pack('H', 4)
            sock_tcp.send(ok)
            sliding_window(sock_udp, sock_tcp, info_unpack[1], info_unpack[2])
            fim = struct.pack('H', 5)
            sock_tcp.send(fim)

    sock_udp.close()
    sock_tcp.close()

def server_ipv6(port, id):
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.bind(('localhost', int(port)))
    s.listen()
    
    while(1):
        csock, addr = s.accept()
        print(csock)
        thread = threading.Thread(target=client_thread, args=(csock, addr, 6))
        thread.start()

def main():
    port = sys.argv[1]
    thread_ipv6 = threading.Thread(target=server_ipv6, args=(port, 1))
    thread_ipv6.start()
    s_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s_ipv4.bind(('localhost', int(port)))
    s_ipv4.listen()

    while(1):
        # accept dois sockets
        csock, addr = s_ipv4.accept()
        print(csock)
        thread = threading.Thread(target=client_thread, args=(csock, addr, 4))
        thread.start()


if __name__ == "__main__":
    main()
