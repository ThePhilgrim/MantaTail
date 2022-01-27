"""Simple fuzzer for MantaTail. See https://en.wikipedia.org/wiki/Fuzzing

To fuzz:

 1. Make sure you don't have any unnecessary prints in mantatail. They will
    cause the fuzzer to think that mantatail crashed; it doesn't try to
    distinguish prints from error messages.

 2. Make sure that Mantatail isn't running.

 3. Run this script.
"""

import collections
import os
import random
import socket
import subprocess
import threading
from pathlib import Path

# Change to the directory where this script is, so it doesn't matter whether
# you run "python3 fuzzer.py" or "python3 tests/fuzzer/fuzzer.py"
os.chdir(Path(__file__).parent)


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
    "TOPIC",
    "PING",
    "PONG",
    "PRIVMSG",
    "QUIT",
    "USER",
    "",
    ":",
]

# Example of what Mantatail prints:
#
#    Got connection from ('127.0.0.1', 33224)
#    Got connection from ('127.0.0.1', 33226)
#    Got connection from ('127.0.0.1', 33228)
#    Got connection from ('127.0.0.1', 33230)
#    Exception in thread Thread-12909:
#    Traceback (most recent call last):
#      File "/usr/lib/python3.9/threading.py", line 954, in _bootstrap_inner
#        self.run()
#      File "/usr/lib/python3.9/threading.py", line 892, in run
#        self._target(*self._args, **self._kwargs)
#      File "/home/akuli/MantaTail/mantatail.py", line 198, in recv_loop
#        call_handler_function(state, user, args)
#      File "/home/akuli/MantaTail/commands.py", line 133, in handle_mode
#        process_channel_modes(state, user, args)
#      File "/home/akuli/MantaTail/commands.py", line 396, in process_channel_modes
#        if args[1][0] not in ["+", "-"]:
#    IndexError: string index out of range
#    Got connection from ('127.0.0.1', 33232)
#    Got connection from ('127.0.0.1', 33234)
#    Got connection from ('127.0.0.1', 33236)
#    Got connection from ('127.0.0.1', 33238)
#
# To figure out what commands caused the crash, i.e. what was sent from address
# tuple ('127.0.0.1', 33230), we keep the most recent address tuples and
# commands here.
recent_commands = collections.deque(maxlen=100)


def print_commands(source_string):
    # avoid looping over the deque while it might change
    recent_commands_copy = list(recent_commands)

    for address_tuple, commands in recent_commands_copy:
        if str(address_tuple) == source_string:
            print(commands)


def output_reading_thread():
    source = None
    output_lines = []

    for line in mantatail_process.stdout:
        line = line.decode()
        if line.startswith("Got connection from"):
            if source and output_lines:
                print("\n\n")
                print("-------- CRASH BEGIN --------")
                print("*** Commands: ***")
                print_commands(source)
                print("*** Errors: ***")
                print("".join(output_lines))
                print("-------- CRASH END --------")

            source = line.replace("Got connection from", "").strip()
            output_lines.clear()
        else:
            output_lines.append(line)


def fuzzing_loop():
    print("Fuzzing...")
    while True:
        commands = ""
        for line_number in range(500):
            words_per_line = random.randint(1, 5)
            chosen_words = [random.choice(words) for word_number in range(words_per_line)]
            commands += " ".join(chosen_words) + "\n"

        sock = socket.socket()
        sock.connect(("localhost", 6667))
        recent_commands.append((sock.getsockname(), commands))
        sock.sendall(commands.encode())

        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            # shutdown() sometimes fails on macos
            pass
        sock.close()


# Start Mantatail in a separate process while fuzzing.
#
# -u tells python that prints should be displayed immediately.
# This is the default when the output is going to a terminal, but not when it
# is being captured by the subprocess module.
mantatail_process = subprocess.Popen(
    ["python3", "-u", "mantatail.py"], cwd="../..", stdout=subprocess.PIPE, stderr=subprocess.STDOUT
)
try:
    print(mantatail_process.stdout.readline())  # Wait for mantatail to start
    threading.Thread(target=output_reading_thread).start()
    fuzzing_loop()
finally:
    mantatail_process.kill()
