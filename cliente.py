import socket
import sys
import struct
import time
import ipaddress

class SlidingWindow(object):
    def __init__(self, size, max_retr, timeout, udp_port, ip, tcp):
        # inicializacao das variaveis necessarias para o controle da janela deslizante
        self.size = size
        self.max_retr = max_retr
        self.timeout = timeout
        self.length = 1000
        self.sock_tcp = tcp
        # criacao do socket UDP
        self.sock_udp = create_socket(ip, socket.SOCK_DGRAM)
        self.ip = ip
        self.udp_port = udp_port
    
    def window_send(self, data, key):
        # envia um numero de mensagens seguidas igual ou inferior ao tamanho maximo da janela
        for i in range(self.size - self.size_window):
            if i+key < len(data):
                self.send(data[i+key], i+key, self.max_retr)
                print("Pacote {} enviado".format(i+key))
                self.last += 1

    def send(self, data, key, retrans_left):
        # envia pedaco do arquivo via UDP
        self.sock_udp.sendto(self.send_msg(data), (self.ip, self.udp_port) )
        # armazena o clock de quando a mensagem foi enviada e o numero de retransferencias permitidas
        self.window[key] = (time.time() + self.timeout, retrans_left)
        self.size_window += 1

    def repeat(self, data, oldest_seq_number, retrans_left):
        print("Retransmitir pacote {}".format(oldest_seq_number))
        self.window.pop(oldest_seq_number)
        self.size_window -= 1
        self.send(data[oldest_seq_number], oldest_seq_number, retrans_left-1)

    def run(self, fname):
        data = self.send_data(fname)
        self.window = {}
        self.size_window = 0
        self.last = 0
        self.first = 0
        self.window_send(data, 0)
        while self.window:
            oldest_seq_number, (oldest_endtime, retrans_left) = next(iter(self.window.items()))
            # print("oldest seq number: ", oldest_seq_number)
            timeout = self._calculate_timeout(oldest_endtime)

            if timeout == 0:
                if retrans_left <= 0:
                    print("\nTimeout: Acabou o numero maximo de retransmissoes, pacote {} nao recebeu ACK".format(oldest_seq_number))
                    return -1
                self.repeat(data, oldest_seq_number, retrans_left)
                continue
            
            self.sock_tcp.settimeout(timeout)
            try:
                reply = self.sock_tcp.recv(6)
                if not reply:
                    print("Servidor fechou")
                    return -1
                    
                ack = struct.unpack('=HI', reply)
                print("ACK recebido para o pacote {}".format(ack[1]))
                if ack[0] == 7 and ack[1] in self.window.keys() and self.size_window <= 4:
                    self.window.pop(ack[1])
                    print(self.size_window)
                    # se o ACK recebido se refere ao inicio da janela, podemos move-la
                    if ack[1] == self.first:
                        print("first: ", self.first)
                        print(self.window.keys())
                        print("size_window: ", self.size_window)

                        for i in range(self.size):
                            if i+self.first in self.window.keys():
                                break
                            else:
                                self.size_window -= 1
                        self.first += self.size - self.size_window
                        print("size_window: ", self.size_window)
                        print("first: ", self.first)
                        if self.last < len(data):
                            self.window_send(data, self.last)
                            # self.send(data[self.last], self.last, self.max_retr) 
                            print("last: ", self.last)

            except socket.timeout:
                # manda de novo
                if retrans_left <= 0:
                    print("\nTimeout: Acabou o numero maximo de retransmissoes, pacote {} nao recebeu ACK".format(oldest_seq_number))
                    return -1
                self.repeat(data, oldest_seq_number, retrans_left)
        
        return 1

    def _calculate_timeout(self, end_time):
        return max(0, min(self.timeout, end_time - time.time()))

    def send_data(self, fname):
        # ler o arquivo em bytes
        with open(fname, "rb") as f:
            data = f.read()
        data_type = 6
        data_len = len(data)
        last_offset = data_len - (data_len % self.length)
        last_size = data_len - last_offset
        chunks = [(i*self.length, self.length) for i in range(int(data_len / self.length))]
        if last_size > 0:
            chunks.append((last_offset, last_size))
        chunks = [(int(offset/self.length), data[offset: offset + size])
                    for offset, size in chunks]
        # cria uma lista com todos os pacotes a serem enviados, incluindo todo o cabecalho
        packets = [(data_type, num_seq, len(data), data) for num_seq, data in chunks]
        
        return packets

    def send_msg(self, msg):
        message = b''
        message += struct.pack('H', msg[0])
        message += struct.pack('I', msg[1])
        message += struct.pack('H', msg[2])
        message += msg[3] # ja esta em bytes
        return message

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
                msg = SlidingWindow(4, 4, 1, udp_port, ip, s).run(fname)

                # se deu tudo certo na janela
                if msg == 1:
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