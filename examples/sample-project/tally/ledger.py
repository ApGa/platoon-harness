"""Expenses, what each person is owed, and the payments that settle it."""

import csv
from collections.abc import Iterable
from dataclasses import dataclass

from .money import parse_amount


@dataclass(frozen=True)
class Expense:
    """What `payer` paid, in cents, for the people in `among`, who may include the payer."""

    payer: str
    amount: int
    among: tuple[str, ...]


def read_expenses(lines: Iterable[str]) -> list[Expense]:
    """Expenses from CSV rows of a payer, an amount and the people it was for, separated by spaces."""
    return [Expense(payer, parse_amount(amount), tuple(among.split())) for payer, amount, among in csv.reader(lines)]


def balances(expenses: Iterable[Expense]) -> dict[str, int]:
    """What each person is owed, in cents, or owes, below zero."""
    owed: dict[str, int] = {}
    for expense in expenses:
        owed[expense.payer] = owed.get(expense.payer, 0) + expense.amount
        share = expense.amount // len(expense.among)
        for person in expense.among:
            owed[person] = owed.get(person, 0) - share
    return owed


def settle(owed: dict[str, int]) -> list[tuple[str, str, int]]:
    """Payments, as payer, payee and cents, that bring each balance to zero: whoever owes most pays whoever is owed most
    as much as the smaller of the two, until nobody is owed anything."""
    debtors, creditors = _largest_first({name: -cents for name, cents in owed.items()}), _largest_first(owed)
    payments = []
    while debtors and creditors:
        debtor, creditor = debtors[0], creditors[0]
        paid = min(debtor[1], creditor[1])
        payments.append((debtor[0], creditor[0], paid))
        debtor[1] -= paid
        creditor[1] -= paid
        if not debtor[1]:
            debtors.pop(0)
        if not creditor[1]:
            creditors.pop(0)
    return payments


def _largest_first(amounts: dict[str, int]) -> list[list]:
    """Each name with an amount above zero, as a name and its amount, the largest first, and by name among equals."""
    return sorted(([name, cents] for name, cents in amounts.items() if cents > 0), key=lambda pair: (-pair[1], pair[0]))
