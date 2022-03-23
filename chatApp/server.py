import json
import socket

from .log import logger
from .message import *
from .constant import BUF_SIZE


class Server:

    def __init__(self, port, logger=logger):
        self.done = False
        self.port = port
        self.logger = logger
        self.clients = dict()
        self.handlers = {
            REGISTER: self.handle_register,
            CHAT_MSG: self.handle_chat,
            DEREGISTER: self.handle_deregister,
            SAVE_MSG: self.handle_save
        }

        self.logger.info(f"instantiated server @ port {self.port}")

    def client_info_str(self, name):
        return f"({', '.join(map(str, self.clients[name]))})"

    def broadcast_client_info(self, user):
        user_info = json.dumps({user: self.clients[user]})

        for client, [ip, port, online] in self.clients.items():
            if online and client != user:
                self.logger.info(
                    f"Broadcast client {user} info: "
                    f"{self.clients[user]} to {client} @ {ip}:{port}")
                resp, _ = make(PEERS_UPDATE, user_info)
                self.sock.sendto(resp, (ip, port))

    def handle_requests(self):
        while not self.done:
            msg, client_addr = self.sock.recvfrom(BUF_SIZE)
            typ, id, content = parse(msg)

            self.handlers[typ](id, client_addr, content)

    def handle_register(self, id, dest, info):
        ip, port = dest
        [name, status] = json.loads(info)

        self.logger.info(f"client @ {ip}:{port} wants to register as {name}.")

        if name not in self.clients:
            # client doesn't exist, register for the first time
            self.logger.info(f"Accepted. Client {name} registered.")

            self.clients[name] = [ip, port, status]
            resp, _ = make(ACK_REG, json.dumps(self.clients), id)
            self.sock.sendto(resp, dest)

            self.broadcast_client_info(name)
        elif dest == (ip, port):
            # same client, re-register
            online = self.clients[name][2]
            if online:
                self.logger.info(
                    f"client {name} @ {ip}:{port} already registered -> no op, sending ack."
                )
                resp, _ = make(ACK_REG, id=id)
                self.sock.sendto(resp, dest)
            else:
                # client went back online
                # TODO: send saved messages if any
                self.logger.info(
                    f"client {name} @ {ip}:{port} went back online, re-registered."
                )
                self.clients[name][2] = True
                resp, _ = make(ACK_REG, json.dumps(self.clients), id)
                self.sock.sendto(resp, dest)

                self.broadcast_client_info(name)
        else:
            # an IP has already registered as name, deny request
            self.logger.info(
                f"Denied. {name} already registered: {self.client_info_str(name)}"
            )
            resp, _ = make(NACK_REG, id=id)
            self.sock.sendto(resp, dest)

    def handle_deregister(self, id, dest, info):
        ip, port = dest
        name = info

        self.logger.info(f"client {name} @ {ip}:{port} wants to de-register.")

        # mark client as offline
        self.clients[name][2] = False

        self.logger.info(f"de-registered client {name} @ {ip}:{port}.")

        # ack
        resp, _ = make(ACK_DEREG, id=id)
        self.sock.sendto(resp, dest)

        # broadcast updated client info
        self.broadcast_client_info(name)

    def handle_chat(self, id, dest, message):
        logger.info(f"message from {dest} received: {message}")

        resp, _ = make(ACK_CHAT_MSG, id=id)
        self.sock.sendto(resp, dest)

    def handle_save(self, id, dest, message):
        logger.info(f"save message from {dest} received: {message}")
        [to, msg] = message.split(" ", maxsplit=1)

        # Client side ensures that `to` is a client
        # to not in self.clients will not occur
        online = self.clients[to][2]

        if online:
            print(f">>> [Client {to} exists!!]")
            resp, _ = make(NACK_SAVE_MSG, json.dumps(self.clients), id=id)
            self.sock.sendto(resp, dest)
        else:
            # TODO: save message for client `to`
            resp, _ = make(ACK_SAVE_MSG, id=id)
            self.sock.sendto(resp, dest)

    def stop(self):
        self.sock.close()
        self.logger.info("server gracefully exited")

    def start(self):
        # bind to a UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", self.port))

        self.logger.info(f"created UDP socket, bound to port {self.port}")

        try:
            self.handle_requests()
        except KeyboardInterrupt:
            self.logger.info("keyboard interrupt! closing socket...")
            self.stop()
