import unittest

from tally.ledger import Expense, balances, read_expenses, settle


class ReadExpensesTest(unittest.TestCase):
    def test_a_row_is_a_payer_an_amount_and_who_it_was_for(self):
        self.assertEqual(read_expenses(["ada,12.00,ada bob\n"]), [Expense("ada", 1200, ("ada", "bob"))])


class BalancesTest(unittest.TestCase):
    def test_an_even_split(self):
        owed = balances([Expense("ada", 1200, ("ada", "bob")), Expense("bob", 300, ("ada", "bob"))])
        self.assertEqual(owed, {"ada": 450, "bob": -450})


class SettleTest(unittest.TestCase):
    def test_who_owes_most_pays_who_is_owed_most(self):
        payments = settle({"ada": 700, "bob": -500, "cy": -200})
        self.assertEqual(payments, [("bob", "ada", 500), ("cy", "ada", 200)])

    def test_nothing_owed_needs_no_payment(self):
        self.assertEqual(settle({"ada": 0, "bob": 0}), [])
