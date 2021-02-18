import socket
import sys
import struct

def infoFile_msg(csock, fname):
    infoFile_type = 3
    length = 12 # tamanho do arquivo em bytes
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
    # verificar caracteres que nao pertencem a tabela ascii
    return True

# pack, unpack
def main():
    ip = sys.argv[1]
    port = sys.argv[2]
    fname = sys.argv[3]
    if verify_fname(fname) == False:
        print("Nome nao permitido")
    else:
        # conexao
    
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, int(port)))
        hello = 1
        msg = struct.pack('h', hello)
        print('Enviado', msg)
        s.sendall(msg)
        data = s.recv(1024)
        connection = struct.unpack('=hi', data)
        if connection[0] == 2:
            print('Received', struct.unpack('=hi', data))
            infoFile_msg(s, fname)
            data = s.recv(1024)
            print('Received', struct.unpack('h', data))
            if struct.unpack('h', data)[0] == 4:
                udp_port = connection[1]
                sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock_udp.connect((ip, int(udp_port)))
        s.close()

if __name__ == "__main__":
    main()