import socket
import threading
import sys
import struct
import os

MAX_SIZE = 1000

def udp_connection(ip_type):
    # cria socket de conexao UDP de acordo com o tipo de protocolo: ipv4 ou ipv6
    if ip_type == 6:
        sock_udp = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    else:
        sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # bind em qualquer porta
    sock_udp.bind(('localhost', 0))

    # retorna o socket criado e a porta ao qual foi conectado
    return (sock_udp, sock_udp.getsockname()[1])

def receive(sock_tcp):
    msg = sock_tcp.recv(1024)
    if not msg:
        print("Cliente desconectou, arquivo nao foi recebido por completo")
        sock_tcp.close()
    

def sliding_window(sock_udp, sock_tcp, fname, length):
    # cria estrutura de dados da janela deslizante
    if length % MAX_SIZE == 0:
        output = [str("") for _ in range(int(length/MAX_SIZE))]
    else: 
        output = [str("") for _ in range(int(length/MAX_SIZE)+1)]

    count = 0
    sock_udp.settimeout(5)

    # enquanto nao tiver quantidade de bytes igual ao tamanho do arquivo fica me loop
    while count < length:
        # recebe um pedaco do arquivo via UDP
        try: 
            data = sock_udp.recv(1008) # 1008?
        except socket.timeout:
            sock_tcp.settimeout(1)
            try:
                msg_test = sock_tcp.recv(1024)
                if not msg_test:
                    print("Cliente desconectou, arquivo nao foi recebido por completo")
                    return -1
            except socket.timeout:
                sock_tcp.settimeout(None)
                continue

        payload_size = len(data) - 8
        if payload_size == MAX_SIZE or payload_size == length%MAX_SIZE:
            count += payload_size
            file_data = struct.unpack('=HIH'+str(payload_size)+'s', data)

            if file_data[0] == 6:
                # armazena o pacote recebido na lista na posicao referente 
                # ao numero de sequencia do pacote recebido
                output[file_data[1]] = file_data[3].decode()
                # envio da mensagem de confirmacao via TCP
                ack = b''
                ack += struct.pack('H', 7)
                ack += struct.pack('I', file_data[1])
                if file_data[1] != 1:
                    try:
                        sock_tcp.send(ack)
                    except:
                        print("Cliente desconectou, arquivo nao foi recebido por completo")
                        return -1
                else: 
                    count -= payload_size
 
    file_ = os.path.join("output/", fname)
    os.makedirs("output/", exist_ok=True)
    with open(file_, "w") as out:
        for chunks in output:
            out.write(chunks)

    print(output)

    return 1

def client_thread(sock_tcp, ip_type):
    # recebe mensagem inicial que identifica o cliente
    hello = sock_tcp.recv(2)
    if not hello:
        print("Cliente desconectou")
        sock_tcp.close()
        return

    type_msg = struct.unpack('H', hello)[0]

    if type_msg == 1:
        # envia mensagem contendo a porta UDP para envio do arquivo
        sock_udp, udp_port = udp_connection(ip_type)
        connection = struct.pack('H', 2)
        connection += struct.pack('I', udp_port)
        sock_tcp.send(connection)

        # recebe mensagem contendo nome e tamanho do arquivo
        info_file = sock_tcp.recv(25)

        if not info_file:
            print("Cliente desconectou")
            sock_tcp.close()
            return

        length = len(info_file) - 10
        info_unpack = struct.unpack('=H'+str(length)+'sQ', info_file)

        if info_unpack[0] == 3:
            # envia mensagem confirmando que o envio pode comecar 
            ok = struct.pack('H', 4)
            sock_tcp.send(ok)
            # inicia processo da janela deslizante do receptor
            ret = sliding_window(sock_udp, sock_tcp, info_unpack[1].decode(), info_unpack[2])
            # sinaliza que todos os bytes do arquivo foram recebidos e o cliente pode desconectar
            if ret == 1:
                fim = struct.pack('H', 5)
                sock_tcp.send(fim)
            
    print("Finalizando comunicacao com o cliente")
    # finaliza conexao TCP
    sock_tcp.close()

def server_ipv6(port):
    # cria socket ipv6
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.bind(('localhost', int(port)))
    s.listen()

    while(1):
        csock, _ = s.accept()

        # cria thread do cliente
        thread = threading.Thread(target=client_thread, args=(csock, 6))
        thread.daemon = True
        thread.start()

def main():
    port = sys.argv[1]

    # cria nova thread para lidar com protocolo ipv6
    thread_ipv6 = threading.Thread(target=server_ipv6, args=(port,))
    thread_ipv6.daemon = True
    thread_ipv6.start()

    # cria socket ipv4
    s_ipv4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s_ipv4.bind(('localhost', int(port)))
    s_ipv4.listen()

    while(1):
        csock, _ = s_ipv4.accept()
        
        # cria thread do cliente
        thread = threading.Thread(target=client_thread, args=(csock, 4))
        thread.daemon = True
        thread.start()

if __name__ == "__main__":
    main()
