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
        # self.sock_tcp.settimeout(timeout)
        self.sock_udp = create_socket(ip, socket.SOCK_DGRAM)
        self.ip = ip
        self.udp_port = udp_port
    
    def window_initialize(self, data):
        # envia um numero de mensagens seguidas igual ou inferior ao tamanho maximo da janela
        for i in range(self.size):
            if i < len(data):
                self.send(data[i], i, self.max_retr)

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
        self.window_initialize(data)
        self.last = self.size-1
        print(self.window)
        while self.window:
            oldest_seq_number, (oldest_endtime, retrans_left) = next(iter(self.window.items()))
            timeout = self._calculate_timeout(oldest_endtime)

            if timeout == 0:
                if retrans_left <= 0:
                    print("Timeout: Acabou o numero maximo de retransmissoes, pacote {} nao recebeu ACK".format(oldest_seq_number))
                    return "timeout"
                self.repeat(data, oldest_seq_number, retrans_left)
                continue
            
            self.sock_tcp.settimeout(timeout)
            try:
                reply = self.sock_tcp.recv(6)
                ack = struct.unpack('=HI', reply)
                print("ACK recebido para o pacote {}".format(ack[1]))
                if ack[0] == 7 and ack[1] in self.window.keys() and self.size_window <= 4:
                    self.window.pop(ack[1])
                    self.size_window -= 1
                    self.last += 1
                    if self.last < len(data):
                        self.send(data[self.last], self.last, self.max_retr)   
                    print(self.window)
                    # se o ack chegou para outro numero de sequencia diferente do mais antigo
                    # e o timeout do mais antigo foi atingido, reenvia
                    # if ack[1] != oldest_seq_number and self._calculate_timeout(oldest_endtime) == 0:
                    #     if retrans_left <= 0:
                    #         print("Timeout: Acabou o numero maximo de retransmissoes, pacote {} nao recebeu ACK".format(oldest_seq_number))
                    #         return "timeout"
                    #     self.repeat(data, oldest_seq_number, retrans_left)

            except socket.timeout:
                # manda de novo
                if retrans_left <= 0:
                    print("Timeout: Acabou o numero maximo de retransmissoes, pacote {} nao recebeu ACK".format(oldest_seq_number))
                    return "timeout"
                self.repeat(data, oldest_seq_number, retrans_left)
        
        return "ok"

    def _calculate_timeout(self, end_time):
        return max(0, min(self.timeout, end_time - time.time()))

    def send_data(self, fname):
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
    with open(fname, "rb") as f:
        data = f.read()
    infoFile_type = 3
    length = len(data) # tamanho do arquivo em bytes
    message = b''
    message += struct.pack('H', infoFile_type)
    message += str.encode(fname)
    message += struct.pack('Q', length)
    csock.sendall(message)

def verify_fname(fname):
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

# selective reapt: retransmissao apenas dos que nao recebeu ack
# go-back-N: todos os frames sao retransmitidos se nao receber ACK do primeiro

def create_socket(ip, type_):
    ip_type = ipaddress.ip_address(ip)
    if ip_type.version == 6:
        return socket.socket(socket.AF_INET6, type_)
    return socket.socket(socket.AF_INET, type_)
    
def main():
    ip = sys.argv[1]
    port = sys.argv[2]
    fname = sys.argv[3]
    if verify_fname(fname) == False:
        print("Nome nao permitido")
    else:
        # conexao
        s = create_socket(ip, socket.SOCK_STREAM)
        s.connect((ip, int(port)))
        hello = 1
        msg = struct.pack('H', hello)
        print('Enviado', msg)
        s.sendall(msg)
        data = s.recv(1024)
        connection = struct.unpack('=HI', data)
        if connection[0] == 2:
            print('Received', struct.unpack('=HI', data))
            infoFile_msg(s, fname)
            data = s.recv(1024)
            print('Received', struct.unpack('H', data))
            ok = struct.unpack('H', data)[0]
            if ok == 4:
                print("udp_port: ", connection[1])
                msg = SlidingWindow(3, 3, 1, connection[1], ip, s).run(fname)
                if msg == "ok":
                    s.settimeout(None)
                    fim = s.recv(2)
                    fim = struct.unpack('H', fim)
                    if fim[0] == 5:
                        print("Arquivo enviado corretamente!")
                        s.close()
                        
                else:
                    s.close()

if __name__ == "__main__":
    main()