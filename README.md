# MantaTail

MantaTail is a sandbox IRC server developed to test IRC clients and functionality.

It is still at an early stage of production, and is therefore missing several crucial features.

### Currently supported features:

- Message of the day
- Join channel
- Part from channel
- Supported error messages:
  - [No such channel, Unknown command, You're not on that channel]

### Connect to MantaTail

To connect your IRC server to MantaTail, connect to `127.0.0.1 port 6667`.

## For developers

If you are interested in contributing to Mantatail, thank you! You are most welcome to do so.

To start, please follow these steps:

1. Fork the repository and `git clone` it to your local machine
2. Create a virtual environment and activate it
   - Mac/Linux: `python3 -m venv env` -> `source env/bin/activate`
   - Windows: `py -m venv env` -> `env\Scripts\activate`
3. Download the necessary dependencies for development
   - Mac/Linux `python3 -m pip install -r requirements-dev.txt`
   - Windows `py -m pip install -r requirements.txt`
4. Happy coding!

### Resources

Some handy resources for developing IRC-related programs:

- [Ircdocs.horse](https://ircdocs.horse/)
- [RFC1459](https://datatracker.ietf.org/doc/html/rfc1459)

### Pull Requests

Any pull request will automatically be checked for proper format by `black`.
It will also be checked for type hinting with `mypy` (--strict mode).

To make sure the PR will pass these checks, please use `black file.py`. Also run `mypy --strict file.py` to make sure there are no current type checking errors.
