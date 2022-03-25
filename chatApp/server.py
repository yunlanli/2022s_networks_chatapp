import json
import socket
import time
from threading import Thread, Lock

from .log import logger
from .message import *
from .constant import BUF_SIZE


class Server:

    def __init__(self, port, logger=logger):
        self.done = False
        self.port = port
        self.logger = logger
        self.clients = dict()
        self.msg_store = dict()
        self.inflight = dict()
        self.mu = Lock()
        self.handlers = {
            REGISTER: self.handle_register,
            CHAT_MSG: self.handle_chat,
            DEREGISTER: self.handle_deregister,
            SAVE_MSG: self.handle_save,
            BROADCAST_MSG: self.handle_broadcast_msg,
            ACK_BROADCAST_MSG: self.handle_ack_broadcast_msg,
            ACK_STATUS: self.handle_status_ack
        }
        self.timeout_handlers = {
            BROADCAST_MSG: self.timeout_broadcast_msg,
            STATUS: self.timeout_status
        }

        self.logger.info(f"instantiated server @ port {self.port}")

    def find_client_by_addr(self, addr):
        user_ip, user_port = addr
        for name, [ip, port, _] in self.clients.items():
            if user_ip == ip and user_port == port:
                return name

        return None

    def client_info_str(self, name):
        return f"({', '.join(map(str, self.clients[name]))})"

    def record(self, id, addr, typ, data):
        ts = get_ts()
        self.inflight[id] = (ts, addr, typ, data)

    def rm_record(self, id):
        if id in self.inflight:
            ts = self.inflight[id][0]
            duration = int(get_ts() * 1000 - ts * 1000)

            del self.inflight[id]
            self.logger.info(
                f"msg {id} acked, remove from inflight ({duration}ms)")

    def broadcast_client_info(self, user):
        user_info = json.dumps({user: self.clients[user]})

        for client, [ip, port, online] in self.clients.items():
            if online and client != user:
                self.logger.info(
                    f"Broadcast client {user} info: "
                    f"{self.clients[user]} to {client} @ {ip}:{port}")
                resp, _ = make(PEERS_UPDATE, user_info)
                self.sock.sendto(resp, (ip, port))

    def broadcast_chat(self, from_cli, to_cli, chat):
        [to_ip, to_port, online] = self.clients[to_cli]
        dest = (to_ip, to_port)

        if online:
            data = f"{from_cli} {chat}"
            resp, id = make(BROADCAST_MSG, data)
            self.sock.sendto(resp, dest)
            self.logger.info(
                f"broadcast message from {from_cli} to {to_cli}: {shorten_msg(chat)}"
            )

            self.record(id, dest, BROADCAST_MSG, data)
        else:
            self.save_msg(from_cli, to_cli, chat, typ=CHANNEL_MESSAGE)

    def wait_status(self, id):
        cond = True

        while cond:
            self.mu.acquire()
            cond = id in self.inflight
            self.mu.release()

    def save_msg(self, src, dest, msg, typ=REGULAR_MESSAGE):
        timestamp = get_ts()
        record = (timestamp, src, msg, typ)

        if dest in self.msg_store:
            self.msg_store[dest].append(record)
        else:
            self.msg_store[dest] = [record]

        self.logger.info(
            f"Message {shorten_msg(msg)} for {dest} from {src} saved!")

    def clear_msg(self, client):
        msgs = self.msg_store[client] if client in self.msg_store else []
        self.msg_store.pop(client, None)

        return msgs

    def handle_requests(self):
        while not self.done:
            msg, client_addr = self.sock.recvfrom(BUF_SIZE)
            typ, id, content = parse(msg)

            self.mu.acquire()
            self.handlers[typ](id, client_addr, content)
            self.mu.release()

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
                self.logger.info(
                    f"client {name} @ {ip}:{port} went back online, re-registered."
                )

                # check for offline messages and send to client if any
                data = json.dumps(self.clear_msg(name))
                resp, _ = make(OFFLINE_MSG, data)
                self.sock.sendto(resp, dest)

                # set client status to true and broadcast table
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

    def handle_status_ack(self, id, dest, message):
        client = self.find_client_by_addr(dest)

        if id not in self.inflight:
            self.logger.info(
                "The client {client} didn't ack in time (500ms), discarding this message."
            )
        else:
            # update client status, broadcast updated status
            online = json.loads(message)

            if online != self.clients[client][2]:
                self.clients[client][2] = online
                self.broadcast_client_info(client)

            self.rm_record(id)

    def handle_save(self, id, dest, message):
        logger.info(f"save message from {dest} received: {message}")
        src = self.find_client_by_addr(dest)
        [to, msg] = message.split(" ", maxsplit=1)

        # check the status of the client
        resp, status_id = make(STATUS)
        self.sock.sendto(resp, dest)
        self.record(status_id, dest, STATUS, "")

        def callback(from_cli, to_cli, status_id, save_id, dest, msg):
            self.wait_status(status_id)

            self.mu.acquire()
            online = self.clients[to_cli][2]

            if online:
                resp, _ = make(NACK_SAVE_MSG,
                               json.dumps(self.clients),
                               id=save_id)
                self.sock.sendto(resp, dest)
            else:
                self.save_msg(from_cli, to_cli, msg)

                resp, _ = make(ACK_SAVE_MSG, id=save_id)
                self.sock.sendto(resp, dest)
            self.mu.release()

        Thread(target=callback,
               args=(src, to, status_id, id, dest, msg),
               daemon=True).start()

    def handle_broadcast_msg(self, id, dest, info):
        src = self.find_client_by_addr(dest)
        self.logger.info(f"BROADCAST_MSG from {src}: {shorten_msg(info)}")

        # send ack to the sender
        resp, _ = make(ACK_BROADCAST_MSG, id=id)
        self.sock.sendto(resp, dest)

        # broadcast
        for client in list(self.clients):
            if client != src:
                self.broadcast_chat(src, client, info)

    def handle_ack_broadcast_msg(self, id, dest, info):
        self.rm_record(id)

    # All timeout handlers are called with lock held
    def timeout_broadcast_msg(self, id, dest, info):
        resp, id = make(STATUS)
        self.sock.sendto(resp, dest)
        self.record(id, dest, STATUS, "")

        def callback(id, dest, info):
            self.wait_status(id)

            # we now know the status of the client @ dest
            # we now broacast_chat (save if client offline, otherwise broadcast)
            self.mu.acquire()
            to_cli = self.find_client_by_addr(dest)
            [from_cli, chat] = info.split(" ", maxsplit=1)

            self.broadcast_chat(from_cli, to_cli, chat)
            self.mu.release()

        # use a separate thread to perform actions
        # after status is acked or timed out
        Thread(target=callback, args=(id, dest, info), daemon=True).start()

    def timeout_status(self, id, dest, info):
        # update client status, broadcast updated status
        client = self.find_client_by_addr(dest)
        prev_status = self.clients[client][2]
        self.logger.info(
            f"The client {client} didn't ack STATUS in time (500ms).")

        if prev_status:
            self.clients[client][2] = False
            self.broadcast_client_info(client)

    def timeout(self):
        while not self.done:
            now = get_ts()

            self.mu.acquire()

            for id in list(self.inflight):
                (ts, addr, typ, data) = self.inflight[id]
                has_timeout = timeout(ts, now)

                if has_timeout:
                    self.logger.info(
                        f"Message {id} timed out, dispatching timeout handler")

                    self.timeout_handlers[typ](id, addr, data)
                    del self.inflight[id]

            self.mu.release()

            time.sleep(TIMEOUT / 1000)

    def stop(self):
        self.done = True
        self.sock.close()
        self.logger.info("server gracefully exited")

    def start(self):
        # bind to a UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", self.port))

        self.logger.info(f"created UDP socket, bound to port {self.port}")

        listener = Thread(target=self.handle_requests,
                          name="req_handler",
                          daemon=True)
        timeout = Thread(target=self.timeout, name="timeout", daemon=True)

        listener.start()
        timeout.start()

        try:
            listener.join()
            timeout.join()
        except KeyboardInterrupt:
            self.logger.info("keyboard interrupt! closing socket...")
            self.stop()
