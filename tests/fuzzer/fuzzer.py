"""Simple fuzzer for MantaTail. See https://en.wikipedia.org/wiki/Fuzzing

Usage:
- Start MantaTail: python3 -m mantatail
- Run fuzzer in another terminal: python3 fuzzer.py
- Go back to MantaTail terminal, and see if you get errors.
"""

import socket
import random
import sys


words = [
    "#bar",
    "#foo",
    "+g",
    "+o",
    "+xyz",
    "-g",
    "-o",
    "-xyz",
    "JOIN",
    "KICK",
    "MODE",
    "NICK",
    "PART",
    "PING",
    "PONG",
    "PRIVMSG",
    "QUIT",
    "USER",
    "",
]

print("Fuzzer starting. Please see if errors appear in the Mantatail terminal.")

while True:
    command = ""
    for line_number in range(1000):
        words_per_line = random.randint(1, 5)
        chosen_words = [random.choice(words) for word_number in range(words_per_line)]
        command += " ".join(chosen_words) + "\n"

    sock = socket.socket()
    try:
        sock.connect(("localhost", 6667))
    except ConnectionRefusedError:
        sys.exit("Connection Refused: Start Mantatail in a separate terminal before running fuzzer.py")

    sock.sendall(command.encode())

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        # shutdown() sometimes fails on macos
        pass
    sock.close()
