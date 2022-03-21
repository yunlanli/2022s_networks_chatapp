import json
import socket

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

        self.logger.info(
            f"instantiated client {self.username} @ port {self.port} for server @ {self.server}:{self.sport}"
        )

    def get_message(self):
        while True:
            message = input('>>> ')
            encoded = make(CHAT_MSG, message)
            self.sock.sendto(encoded, (self.server, self.sport))
            self.logger.info(f"sending to {self.server}: {message}")

            resp, server_addr = self.sock.recvfrom(BUF_SIZE)

    def register(self):
        # register under self.username at the server
        info = json.dumps([self.username, True])
        encoded = make(REGISTER, info)
        self.sock.sendto(encoded, (self.server, self.sport))

        # check if registration is successful
        resp, _ = self.sock.recvfrom(BUF_SIZE)
        typ, content = parse(resp)

        if typ == ACK_REG:
            print(">>> [Welcome, You are registered.]")

            self.peers = json.loads(content)
            print(">>> [Client table updated.]")
        else:
            self.logger.error(f"{self.username} already registered, abort.")
            exit(0)

    def deregister(self):
        pass

    def stop(self):
        self.sock.close()
        self.deregister()
        self.logger.info(f"client {self.username} gracefully exited")

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((socket.gethostname(), self.port))

        self.logger.info(f"created UDP socket, bound to port {self.port}")

        self.register()

        try:
            self.get_message()
        except KeyboardInterrupt:
            self.logger.info("keyboard interrupt! exiting client...")
            self.stop()
