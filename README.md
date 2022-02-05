# MantaTail

MantaTail is a sandbox IRC server developed to test IRC clients and functionality.

It is still in development and is therefore missing some central features.

### Currently supported features:

- Capability Negotiation (limited)
- Message of the day
- Join channel
- Part from channel
- Send message to channel
- Send private message to other user
- Set / Remove channel operator
- Set channel topic
- Kick user from channel
- Ban user from channel
- Change nick
- Set away status
- Quit from server

## How to use Mantatail

You can connect to Mantatail via an IRC client of you choice (I recommend [Mantaray](https://github.com/Akuli/mantaray)) or via a network utility such as Netcat.

To start Mantatail, cd to the mantatail folder and run `python3 server.py`.
Thereafter, you can connect to the server by connecting to `localhost 6667`.

## For developers

If you are interested in contributing to Mantatail, thank you! You are most welcome to do so.

To start, please follow these steps:

1. Fork the repository and `git clone` it to your local machine
2. Create a virtual environment and activate it
   - Mac/Linux: `python3 -m venv env` -> `source env/bin/activate`
   - Windows: `py -m venv env` -> `env\Scripts\activate`
3. Download the necessary dependencies for development
   - Mac/Linux/Windows `pip install -r requirements-dev.txt`
4. Happy coding!

### Tests

Mantatail relies on Pytest for testing. In order to run the test suite, use `python3 -m pytest`

### Fuzzing

The fuzzer spams the server with random commands to reveal eventual errors.
To run the fuzzer, make sure `server.py` is not running, cd to `tests/fuzzer` and run `python3 fuzzer.py`.

If you are developing a new feature, you can substitute the list `words` with a list containing limited amount of relevant data.

For example, if you are working with the feature of banning a user, a reasonable data set could be:
`words = ["MODE", "mode", "Mode", "#chan", "#%invalidchan "+", "-", "b", "B", "^", ":", "Param1", ":Param2", "Param with spaces"]`

### Resources

Some handy resources for developing IRC-related programs:

- [Ircdocs.horse](https://ircdocs.horse/)
- [RFC1459](https://datatracker.ietf.org/doc/html/rfc1459)

### Pull Requests

Any pull request will automatically be checked for proper format by `black`, `pyflakes`, `mypy` (--strict mode), as well as by `pytest`

To make sure the PR will pass these checks, please use the following commands before pushing:

- `black *.py tests/*.py`
- `mypy --strict *.py`
- `python3 -m pytest`
- `python3 -m pyflakes *.py tests/`
