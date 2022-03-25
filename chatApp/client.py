import json
import re
import socket
import threading
import time

from .log import logger
from .message import *
from .constant import BUF_SIZE, TIMEOUT


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
            ACK_CHAT_MSG: self.handle_ack_chat_msg,
            ACK_DEREG: self.handle_ack_dereg,
            ACK_SAVE_MSG: self.handle_ack_save,
            NACK_SAVE_MSG: self.handle_nack_save,
            OFFLINE_MSG: self.handle_offline_chat_msg,
            ACK_BROADCAST_MSG: self.handle_ack_broadcast_msg,
            BROADCAST_MSG: self.handle_broadcast_msg,
            STATUS: self.handle_status
        }
        self.timeout_handlers = {
            DEREGISTER: self.timeout_deregister,
            CHAT_MSG: self.timeout_chat,
            SAVE_MSG: self.timeout_save,
            BROADCAST_MSG: self.timeout_broadcast_msg
        }
        self.inflight = dict()  # inflight messages/requests
        self.mu = threading.Lock()  # mutext lock for self.inflight
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

    def record(self, id, addr, typ, data, max_retry=-1, locked=False):
        # max_retry = -1 -> can retry infinite times
        if not locked:
            self.mu.acquire()

        ts = get_ts()
        self.inflight[id] = (ts, addr, typ, data, max_retry)

        if not locked:
            self.mu.release()

    def rm_record(self, id):
        self.mu.acquire()

        if id in self.inflight:
            ts = self.inflight[id][0]
            duration = int(get_ts() * 1000 - ts * 1000)

            del self.inflight[id]
            self.logger.info(
                f"msg {id} acked, remove from inflight ({duration}ms)")

        self.mu.release()

    def udp_send(self,
                 typ,
                 data,
                 dest=None,
                 max_retry=-1,
                 id=None,
                 locked=False):
        encoded, id = make(typ, data, id)
        addr = None

        if type(dest) == tuple:
            addr = dest
        elif type(dest) == str:
            [ip, port, _] = self.peers[dest]
            addr = (ip, port)
        else:
            addr = (self.server, self.sport)

        self.sock.sendto(encoded, addr)
        self.record(id, addr, typ, data, max_retry, locked)

    def send(self):
        while not self.done:
            message = input('>>> ')

            send = re.match(r"send (?P<name>.*?) (?P<msg>.*)$", message)
            dereg = re.match(r"dereg (?P<name>.*?)$", message)
            reg = re.match(r"reg (?P<name>.*?)$", message)
            send_all = re.match(r"send_all (?P<msg>.*)$", message)

            if send is not None:
                self.send_chat(send.group('name'), send.group('msg'))
            elif dereg is not None:
                self.deregister(dereg.group('name'))
            elif reg is not None:
                self.register()
            elif send_all is not None:
                self.send_all(send_all.group('msg'))
            else:
                self.logger.error(f"unrecognized command: \"{message}\"")

    def send_chat(self, peer, msg):
        if peer not in self.peers:
            self.logger.error(f"can't send to {peer}, not in local table")
        elif not self.peers[peer][2]:
            # peer offline, send SAVE_MSG to server
            self.send_offline_chat(msg, peer)
        else:
            self.udp_send(CHAT_MSG, msg, dest=peer, max_retry=0)
            self.logger.info(f"{peer} online, sending: {shorten_msg(msg)}")

    def send_offline_chat(self, msg, peer=None):
        data = f"{peer} {msg}" if peer is not None else msg
        self.udp_send(SAVE_MSG, data, max_retry=0)
        self.logger.info(
            f"{peer} offline/timeout, send SAVE_MSG to server: {shorten_msg(msg)}"
        )

    def send_all(self, msg):
        self.udp_send(BROADCAST_MSG, msg, max_retry=5)
        self.logger.info(f"sending {shorten_msg(msg)} to all")

    def update_peers(self, id, addr, message):
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

    def handle_chat_msg(self, id, addr, message):
        peer = self.find_user_by_addr(addr)
        if peer is not None:
            print(f">>> {peer}: {message}")

            encoded_msg, _ = make(ACK_CHAT_MSG, id=id)
            self.sock.sendto(encoded_msg, addr)
            self.logger.info(
                f"ack'ed message ({shorten_msg(message)}) from {peer}")
        else:
            # drop the ack, when the peer retries,
            # hopefully we have their info in the local table
            self.logger.info(f"received from unknown peer {addr}: {message}")

    def handle_ack_chat_msg(self, id, addr, message):
        peer = self.find_user_by_addr(addr)

        if peer is not None:
            print(f">>> [Message received by {peer}.]")
        else:
            self.logger.info(f"{addr} has gone offline, but message "
                             f"{shorten_msg(message)} received.")

        self.rm_record(id)

    def handle_offline_chat_msg(self, id, addr, message):

        msgs = json.loads(message)

        if len(msgs) > 0:
            print(">>> [You have messages]")

        for (timestamp, src, message, typ) in msgs:
            prefix = "Channel-Message " if typ == CHANNEL_MESSAGE else ""
            print(f">>> {prefix} {src}:  {timestamp} {message}")

    def handle_ack_save(self, id, addr, message):
        self.logger.info(f"SAVE_MSG {id} acked by server")
        self.rm_record(id)
        print(">>> [Messages received by the server and saved]")

    def handle_nack_save(self, id, addr, message):
        self.logger.info(
            f"SAVE_MSG {id} nacked by server, resend chat directly to peer.")

        self.peers = json.loads(message)

        # resend chat message directly to peer
        self.mu.acquire()
        data = self.inflight[id][3]
        peer, msg = data.split(" ", maxsplit=1)
        dest = (self.peers[peer][0], self.peers[peer][1])
        self.mu.release()

        print(f">>> [Client {peer} exists!!]")
        print(">>> [Client table updated.]")

        self.rm_record(id)
        self.udp_send(CHAT_MSG, message, dest=dest, max_retry=0)

    def handle_ack_broadcast_msg(self, id, addr, message):
        print(">>> [Message received by Server.]")
        self.rm_record(id)

    def handle_broadcast_msg(self, id, addr, message):
        [src, msg] = message.split(" ", maxsplit=1)

        print(f">>> [Channel_Message {src}: {msg} ].")

        # ack server that we have recevied the channel message
        ack, _ = make(ACK_BROADCAST_MSG, id=id)
        self.sock.sendto(ack, (self.server, self.sport))

    def handle_ack_reg(self, id, addr, message):
        print(">>> [Welcome, You are registered.]")
        self.update_peers(id, addr, message)
        self.rm_record(id)

    def handle_nack_reg(self, id, addr, message):
        self.logger.error(f"{self.username} already registered, abort.")
        self.done = True

    def handle_ack_dereg(self, id, addr, message):
        print(">>> [You are Offline. Bye.]")

        # mark ourselve as offline
        self.peers[self.username][2] = False
        self.rm_record(id)

    def handle_status(self, id, addr, message):
        online = self.peers[self.username][2]
        self.logger.info(
            f"Received STATUS inquiry, send to server our online status: {online}"
        )

        resp, _ = make(ACK_STATUS, json.dumps(online), id=id)
        self.sock.sendto(resp, addr)

    def register(self):
        # register under self.username at the server
        info = json.dumps([self.username, True])
        self.udp_send(REGISTER, info)

    def deregister(self, client):
        self.udp_send(DEREGISTER, client, max_retry=5)

    def timeout_deregister(self, id, addr, data):
        print(">>> [Server not responding]")
        print(">>> [Exiting]")
        self.stop()

    def timeout_chat(self, id, addr, data):
        self.send_offline_chat(data)

    def timeout_save(self, id, addr, data):
        # Not mandatory to implement -> no op
        pass

    def timeout_broadcast_msg(self, id, addr, data):
        print(">>> [Server not responding.]")
        self.rm_record(id)

    def listen(self):
        while not self.done:
            resp, server_addr = self.sock.recvfrom(BUF_SIZE)
            typ, id, data = parse(resp)
            self.handlers[typ](id, server_addr, data)

    def timeout(self):
        while not self.done:
            now = get_ts()

            self.mu.acquire()

            for id in list(self.inflight):
                (ts, addr, typ, data, retries) = self.inflight[id]
                has_timeout = timeout(ts, now)

                if has_timeout and retries != 0:
                    # resend message
                    retries -= 1
                    retry_str = str(retries) if retries >= 0 else "inf"
                    self.logger.info(
                        f"Resending {id}, tries left after resend: {retry_str}"
                    )
                    self.udp_send(typ,
                                  data,
                                  dest=addr,
                                  max_retry=retries,
                                  id=id,
                                  locked=True)
                elif has_timeout and retries == 0:
                    self.logger.info(
                        f"No retries left for {id}, dispatching timeout handler"
                    )
                    self.timeout_handlers[typ](id, addr, data)
                    del self.inflight[id]

            self.mu.release()

            time.sleep(TIMEOUT / 1000)

    def stop(self):
        self.done = True
        self.sock.close()
        self.logger.info(f"client {self.username} gracefully exited")
        exit(0)

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((socket.gethostname(), self.port))

        self.logger.info(f"created UDP socket, bound to port {self.port}")

        self.register()

        listener = threading.Thread(target=self.listen,
                                    name=f"{self.username}-listener",
                                    daemon=True)
        sender = threading.Thread(target=self.send,
                                  name=f"{self.username}-sender",
                                  daemon=True)
        timer = threading.Thread(target=self.timeout,
                                 name=f"{self.username}-timer",
                                 daemon=True)

        listener.start()
        sender.start()
        timer.start()

        try:
            timer.join()
            sender.join()
            listener.join()
        except KeyboardInterrupt:
            self.logger.info("keyboard interrupt! exiting client...")
        finally:
            self.stop()
