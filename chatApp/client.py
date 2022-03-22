import json
import socket
import threading

from .log import logger
from .message import *
from .constant import BUF_SIZE


class Client:

    def __init__(self,
                 username,
                 server_ip,
                 server_port,
                 client_port,
                 logger=logger):
        self.username = username
        self.server = server_ip
        self.sport = server_port
        self.port = client_port
        self.logger = logger
        # dict of info of other clients (name, IP, port #, online status)
        self.peers = dict()
        self.handlers = {
            PEERS_UPDATE: self.update_peers,
            ACK_REG: self.handle_ack_reg,
            NACK_REG: self.handle_nack_reg,
            ACK_CHAT_MSG: self.handle_ack_chat_msg
        }
        self.done = False

        self.logger.info(
            f"instantiated client {self.username} @ port {self.port} for server @ {self.server}:{self.sport}"
        )

    def send(self):
        while not self.done:
            message = input('>>> ')
            encoded = make(CHAT_MSG, message)
            self.sock.sendto(encoded, (self.server, self.sport))
            self.logger.info(f"sending to {self.server}: {message}")

    def update_peers(self, message):
        for peer, info in json.loads(message).items():
            if peer not in self.peers:
                self.peers[peer] = info
                self.logger.info(f"added peer {peer}: {info} to local table")
            else:
                old_info = self.peers[peer]
                self.peers[peer] = info
                self.logger.info(
                    f"update peer {peer} info: {old_info} -> {info}")

        print(">>> [Client table updated.]")

    def handle_ack_reg(self, message):
        print(">>> [Welcome, You are registered.]")
        self.update_peers(message)

    def handle_nack_reg(self, _):
        self.logger.error(f"{self.username} already registered, abort.")
        self.done = True

    def handle_ack_chat_msg(self, _):
        pass

    def register(self):
        # register under self.username at the server
        info = json.dumps([self.username, True])
        encoded = make(REGISTER, info)
        self.sock.sendto(encoded, (self.server, self.sport))

    def deregister(self):
        pass

    def listen(self):
        while not self.done:
            resp, server_addr = self.sock.recvfrom(BUF_SIZE)
            typ, data = parse(resp)
            self.handlers[typ](data)

    def stop(self):
        self.done = True
        self.sock.close()
        self.deregister()
        self.logger.info(f"client {self.username} gracefully exited")

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((socket.gethostname(), self.port))

        self.logger.info(f"created UDP socket, bound to port {self.port}")

        self.register()

        listener = threading.Thread(target=self.listen,
                                    name=f"{self.username}-listener")
        sender = threading.Thread(target=self.send,
                                  name=f"{self.username}-sender")

        listener.start()
        sender.start()

        try:
            sender.join()
            listener.join()
        except KeyboardInterrupt:
            self.logger.info("keyboard interrupt! exiting client...")
        finally:
            self.stop()
