import json
import re
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
            CHAT_MSG: self.handle_chat_msg,
            ACK_REG: self.handle_ack_reg,
            NACK_REG: self.handle_nack_reg,
            ACK_CHAT_MSG: self.handle_ack_chat_msg
        }
        self.done = False

        self.logger.info(
            f"instantiated client {self.username} @ port "
            f"{self.port} for server @ {self.server}:{self.sport}")

    def find_user_by_addr(self, addr):
        user_ip, user_port = addr
        for name, [ip, port, _] in self.peers.items():
            if user_ip == ip and user_port == port:
                return name

        return None

    def send(self):
        while not self.done:
            message = input('>>> ')

            # TODO: parse command
            send = re.match(r"send (?P<name>.*?) (?P<msg>.*)$", message)

            if send is not None:
                self.send_chat(send.group('name'), send.group('msg'))
            else:
                # TODO
                encoded = make(CHAT_MSG, message)
                self.sock.sendto(encoded, (self.server, self.sport))
                self.logger.info(f"sending to {self.server}: {message}")

    def send_chat(self, peer, msg):
        if peer not in self.peers:
            self.logger.error(f"can't send to {peer}, not in local table")
        else:
            encoded = make(CHAT_MSG, msg)
            [ip, port, online] = self.peers[peer]

            if online:
                self.sock.sendto(encoded, (ip, port))
                self.logger.info(f"{peer} online, sending: {shorten_msg(msg)}")
            else:
                # TODO
                pass

    def update_peers(self, _, message):
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

    def handle_chat_msg(self, addr, message):
        peer = self.find_user_by_addr(addr)
        if peer is not None:
            self.logger.info(
                f"ack'ed message ({shorten_msg(message)}) from {peer}")
            print(f">>> {peer}: {message}")

            encoded_msg = make(ACK_CHAT_MSG)
            self.sock.sendto(encoded_msg, addr)
            self.logger.info(
                f"ack'ed message ({shorten_msg(message)}) from {peer}")
        else:
            # drop the ack, when the peer retries,
            # hopefully we have their info in the local table
            self.logger.info(f"received from unknown peer {addr}: {message}")

    def handle_ack_chat_msg(self, addr, message):
        peer = self.find_user_by_addr(addr)
        if peer is not None:
            print(f">>> [Message received by {peer}.]")
        else:
            self.logger.info(f"{addr} has gone offline, but message "
                             f"{shorten_msg(message)} received.")

    def handle_ack_reg(self, _, message):
        print(">>> [Welcome, You are registered.]")
        self.update_peers(_, message)

    def handle_nack_reg(self, _, __):
        self.logger.error(f"{self.username} already registered, abort.")
        self.done = True

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
            self.handlers[typ](server_addr, data)

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
