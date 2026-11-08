import unittest

from tally.money import format_amount, parse_amount


class ParseAmountTest(unittest.TestCase):
    def test_whole_amounts_and_amounts_with_cents(self):
        self.assertEqual(parse_amount("12"), 1200)
        self.assertEqual(parse_amount("12.50"), 1250)
        self.assertEqual(parse_amount(" 0.05 "), 5)

    def test_a_negative_amount(self):
        self.assertEqual(parse_amount("-3.20"), -320)


class FormatAmountTest(unittest.TestCase):
    def test_cents_are_two_digits(self):
        self.assertEqual(format_amount(1250), "12.50")
        self.assertEqual(format_amount(5), "0.05")
        self.assertEqual(format_amount(-320), "-3.20")
