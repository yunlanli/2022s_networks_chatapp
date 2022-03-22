#!/usr/bin/env bash

tmux send-keys -Rt cli.3 "pip install ." Enter

tmux send-keys -t cli.2 ^c
tmux send-keys -t cli.1 ^c
tmux send-keys -t jason.1 ^c

tmux send-keys -Rt cli.2 "ChatApp -s 10000" Enter
tmux send-keys -Rt cli.1 "ChatApp -c yunlan 127.0.0.1 10000 10001" Enter
tmux send-keys -Rt jason.1 "ChatApp -c jason 127.0.0.1 10000 10002" Enter
