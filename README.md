# Info
- Name: Yunlan Li
- UNI: yl4387

# Usage

Install the package:

```shell
./install.sh
```

Run the program:

- Server mode:
  ```shell
  ChatApp -s <port>
  ```

- Client mode:
  ```shell
  ChatApp -c <name> <server-ip> <server-port> <client-port>
  ```

## Demo

1. demonstration of basic functionalities: send, send_all, reg, dereg, silent leave, error detection, etc

![demo_1](https://user-images.githubusercontent.com/25857014/160049908-56fe4eee-d009-4c62-8a37-ace42461232c.png)


2. demonstartion of timeout, retry, silent leave, save message

![silent_leave](https://user-images.githubusercontent.com/25857014/160049914-c4bd08be-5c71-440d-b7a5-e52720efd1da.png)

3. demonstartion of server checking client status on receiving save offline message

![status_ack](https://user-images.githubusercontent.com/25857014/160054654-d1c24a36-036e-4563-8056-ad0e09fb9a01.png)


# Features

- [x] Registration (silent leave, notified leave)
- [x] Chatting between clients
- [x] Deregistration (dereg/reg <username> command)
- [x] Offline Chat
- [x] Group Chat
  
All functionalities described in the Homework instruction are implemented, except for a minor modification where if a user enters a **newline** when prompted for input, a new prompt will be displayed. This behavior is similar to most shell behavior.
  
# System Design
  
Both client mode and server mode are multi-threaded.
  
## Client Mode
  Three threads run concurrently:
  1. a **listener** thread that listens for incoming UDP messages from either the server or peers
  2. a **sender** thread that continuously asks for user input from stdin, parse the request, and dispatch it to the correct handler
  3. a **timeout** thread that checks inflight UDP messages every 500 millisecond. If a UDP message has timed out, retry by disptaching it to the corresponding timeout handler if max retries haven't been used up, otherwise log the error to stdout.
  
## Server Mode
  Two threads run concurrently, similar **listener** and **timeout** thread are used. A **sender** is thread is not necessary since the server doesn't takes user input.
  
## Data Structures

Each **request** is identified with a unique ID, generated with Python's [uuid4][1], and stored in a dictionary along with a tuple containing the follow information:
- timestamp of message sent
- address (ip, port) of the destination of the message
- type of the message: all defined in /chatApp/message.py
- message content
- max number of retries, with -1 indicating infinite retries

Both the local **table** of peers in client mode, and the table of clients in server mode are a dictionary with the **username** as the key, and `[ip, port, online]` as its value.

The server stores offline chat messages sent by client in a dictionary with the destined **username** as the key and as corresponding value a tuple containing: timestamp, source client username, message content, type of message (channel or dm).

Both the client and server contains a dictionary of **message handlers** and **timeout handlers**, with the type of message as the key, and a function that takes in message id, source address of message and message content as arguments.
  
## UDP Message Format

  A message contains type, id and content, deliminited by space. All messages are created using the helper function `make` and parsed with `parse` in /chatApp/message.py.

[1]: https://docs.python.org/3/library/uuid.html
