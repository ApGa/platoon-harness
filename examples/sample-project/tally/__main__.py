"""`python3 -m tally FILE`: the payments that settle the expenses in FILE."""

from __future__ import annotations

import argparse
import sys

from .ledger import balances, read_expenses, settle
from .money import format_amount


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tally", description="Say who pays whom to settle shared expenses.")
    parser.add_argument("file", help="a CSV file of who paid, how much, and the people it was for")
    arguments = parser.parse_args(argv)
    with open(arguments.file, newline="") as file:
        payments = settle(balances(read_expenses(file)))
    for payer, payee, cents in payments:
        print(f"{payer} pays {payee} {format_amount(cents)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
