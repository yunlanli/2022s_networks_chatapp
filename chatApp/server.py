import socket

from .log import logger


class Server:

    def __init__(self, port, logger=logger):
        self.done = False
        self.port = port
        self.logger = logger

        self.logger.info(f"instantiated server @ port {self.port}")

    def handle_requests(self):
        while not self.done:
            msg, client_addr = self.sock.recvfrom(2048)
            msg = msg.decode()
            print(f"from {client_addr}: {msg}")

            ack = "ok"
            self.sock.sendto(ack.encode(), client_addr)

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
