import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tally.__main__ import main


class MainTest(unittest.TestCase):
    def test_it_prints_each_payment(self):
        with tempfile.TemporaryDirectory() as folder:
            expenses = Path(folder, "trip.csv")
            expenses.write_text("ada,30.00,ada bob cy\n")
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                self.assertEqual(main([str(expenses)]), 0)
        self.assertEqual(printed.getvalue(), "bob pays ada 10.00\ncy pays ada 10.00\n")
