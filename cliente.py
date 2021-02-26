import socket
import sys
import struct
import time
import ipaddress
import threading
import os

def thread_receive(Window, sock_tcp):
    while True:
        # verifica se ja chegaram todos os ack
        Window.lock_end.acquire()
        if Window.count_receive == len(Window.datagrams):
            print("Saindo da thread recv")
            Window.lock_end.release()
            break
        Window.lock_end.release()

        # pega o pacote mais antigo que esta no dicionario de enviados que nao receberam ack
        Window.lock_send_window.acquire()
        while len(Window.window.items()) == 0:
            Window.not_empty.wait()
        oldest_seq_number, (oldest_endtime, retrans_left) = next(iter(Window.window.items()))
        Window.lock_send_window.release()

        # calcula timeout
        timeout = Window._calculate_timeout(oldest_endtime)
        # se o timeout e zero retransmite
        if timeout == 0:
            if retrans_left <= 0:
                print("\nTimeout: Acabou o numero maximo de retransmissoes, pacote {} nao recebeu ACK".format(oldest_seq_number))
                os._exit(1)
            
            Window.repeat(oldest_seq_number)
            continue
        
        # seta timeout
        sock_tcp.settimeout(timeout)
        
        try:
            # espera pela chegada de um ACK
            reply = sock_tcp.recv(6)
            if not reply:
                print("Servidor fechou")
                os._exit(1)

            ack = struct.unpack('=HI', reply)
            if ack[0] == 7:
                Window.ack_received(ack[1])

        except socket.timeout:
            # deu timeout tenta retransmitir
            if retrans_left <= 0:
                print("\nTimeout: Acabou o numero maximo de retransmissoes, pacote {} nao recebeu ACK".format(oldest_seq_number))
                os._exit(1)
            
            Window.repeat(oldest_seq_number)

def thread_send(Window):
    while True:
        # verifica se ja chegaram todos os ack
        Window.lock_end.acquire()
        if Window.count_receive == len(Window.datagrams):
            print("Saindo da thread send")
            Window.lock_end.release()
            break
        Window.lock_end.release()


        Window.lock_send_window.acquire()
        # envia um novo pacote se estiver sobrando posicoes na janela
        while len(Window.window) == Window.size:
            Window.not_full.wait()
        if Window.last < len(Window.datagrams):
            Window.send(Window.last, Window.max_retr)
            Window.last += 1
            Window.not_empty.notify()

        Window.lock_send_window.release()

class SlidingWindow(object):
    def __init__(self, datagrams, ip, udp_port, window_size=4, max_retr=5, timeout=5.0):
        # inicializacao das variaveis necessarias para o controle da janela deslizante
        self.size = window_size
        self.max_retr = max_retr
        self.timeout = timeout
        self.window = {}
        self.payload_size = 1000
        self.datagrams = datagrams
        self.last = 0
        self.count_receive = 0

        # variaveis de exclusao mutua
        self.lock_send_window = threading.Lock()
        self.lock_end = threading.Lock()

        # variaveis de condicao
        self.not_empty = threading.Condition(self.lock_send_window)
        self.not_full = threading.Condition(self.lock_send_window)

        #criacao do socket UDP
        self.sock_udp = create_socket(ip, socket.SOCK_DGRAM)
        self.ip = ip
        self.udp_port = udp_port
    
    def send(self, key, retrans_left):
        # envia pedaco do arquivo via UDP
        self.sock_udp.sendto(self.send_msg(self.datagrams[key]), (self.ip, self.udp_port) )
        print("Pacote {} enviado".format(key))
        # armazena o clock de quando a mensagem foi enviada e o numero de retransferencias permitidas
        self.window[key] = (time.time() + self.timeout, retrans_left)

    def repeat(self, oldest_seq_number):
        self.lock_send_window.acquire()
        retrans_left = self.window[oldest_seq_number][1]
        self.window.pop(oldest_seq_number)
        print("Retransmitir pacote {}".format(oldest_seq_number))
        self.send(oldest_seq_number, retrans_left-1)
        self.lock_send_window.release()

    def ack_received(self, key):
        self.lock_send_window.acquire()
        print("ACK recebido para o pacote {}".format(key))
        # verifica se o pacote que recebeu ack nao tinha recebido ack antes
        if key in self.window.keys():
            # disponibiliza uma posicao na janela
            self.window.pop(key)
            # incrementa contador de acks
            self.lock_end.acquire()
            self.count_receive += 1
            self.lock_end.release()
            # notifica que a janela possui espaco
            self.not_full.notify()
        self.lock_send_window.release()
    
    def _calculate_timeout(self, end_time):
        return max(0, min(self.timeout, end_time - time.time()))

    def send_msg(self, msg):
        message = b''
        message += struct.pack('H', msg[0])
        message += struct.pack('I', msg[1])
        message += struct.pack('H', msg[2])
        message += msg[3] # ja esta em bytes
        return message

def send_data(fname, length):
    # ler o arquivo em bytes
    with open(fname, "rb") as f:
        data = f.read()
    data_type = 6
    data_len = len(data)
    last_offset = data_len - (data_len % length)
    last_size = data_len - last_offset
    chunks = [(i*length, length) for i in range(int(data_len / length))]
    if last_size > 0:
        chunks.append((last_offset, last_size))
    chunks = [(int(offset/length), data[offset: offset + size])
                for offset, size in chunks]
    # cria uma lista com todos os pacotes a serem enviados, incluindo todo o cabecalho
    packets = [(data_type, num_seq, len(data), data) for num_seq, data in chunks]
    
    return packets

def infoFile_msg(csock, fname):
    # envia mensagem com as informacoes do arquivo a ser enviado
    with open(fname, "rb") as f:
        data = f.read()
    message = struct.pack('H', 3)
    message += str.encode(fname)
    message += struct.pack('Q', len(data))
    csock.sendall(message)

def verify_fname(fname):
    # verifica se o nome do arquivo eh valido
    if '.' not in fname:
        return False
    elif len(fname) > 15:
        return False
    elif fname.count('.') > 1:
        return False
    elif len(fname.split('.')[1]) < 3:
        return False
    elif fname.isascii() == False:
        return False
    return True

def create_socket(ip, type_):
    # cria socket de acordo com a versao do IP: IPv4 ou IPv6
    ip_type = ipaddress.ip_address(ip)
    if ip_type.version == 6:
        return socket.socket(socket.AF_INET6, type_)
    return socket.socket(socket.AF_INET, type_)
    
def main():
    ip = sys.argv[1]
    port = sys.argv[2]
    fname = sys.argv[3]

    if verify_fname(fname) == True:
        # O final da string termina quando o servidor le o terceiro caractere depois do (.)
        fname_ = fname.split(".")
        fname = fname_[0]+'.'+fname_[1][:3]

        # criando socket e iniciando conexao
        s = create_socket(ip, socket.SOCK_STREAM)
        s.connect((ip, int(port)))

        print('Enviando mensagem inicial')
        hello = struct.pack('H', 1)
        s.sendall(hello)

        # recebe mensagem contendo a porta UDP para envio do arquivo
        conn = s.recv(6)
        if not conn:
            print("Servidor fechou")
            s.close()
            return

        conn = struct.unpack('=HI', conn)
        if conn[0] == 2:
            udp_port = conn[1]
            print('Porta UDP recebida:', udp_port)

            print('Enviando informacoes do arquivo')
            infoFile_msg(s, fname)

            # recebe mensagem informando que esta tudo pronto para comecar o envio do arquivo
            ok = s.recv(2)
            if not ok:
                print("Servidor fechou")
                s.close()
                return

            print('Esta tudo pronto para iniciar o envio do arquivo!\n')
            ok = struct.unpack('H', ok)[0]

            if ok == 4:
                # controle da janela deslizante do transmissor
                datagrams = send_data(fname, 1000)
                Window = SlidingWindow(datagrams, ip, udp_port)
           
                tsend = threading.Thread(target=thread_send, args=(Window,))
                tsend.daemon = True
                tsend.start()

                trecv = threading.Thread(target=thread_receive, args=(Window, s))
                trecv.daemon = True
                trecv.start()

                tsend.join()
                trecv.join()
            
                s.settimeout(None)
                # recebe mensagem indicando que o servidor ja recebeu o arquivo completo
                end = s.recv(2)
                if not end:
                    print("Servidor fechou")
                    s.close()
                    return

                end = struct.unpack('H', end)
                if end[0] == 5:
                    print("\nArquivo enviado corretamente!")
        s.close()
    else:
        print("Nome nao permitido")

if __name__ == "__main__":
    main()