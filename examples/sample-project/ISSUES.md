# Issues

## 1. An amount with one digit of cents is read wrong

`parse_amount("12.5")` gives 1205 cents, 12.05, where `12.5` means 12.50. Every amount with one digit after the point is
off: `0.5` is read as 0.05.

## 2. An expense that does not split evenly loses a cent

`ada,10.00,ada bob cy` leaves ada owed 6.67, and bob and cy owing 3.33 each, so the balances add up to 0.01, and
`settle` pays ada back 6.66 of the 6.67 she is owed. Each share should be in whole cents, with the cents left over going
one each to the first people the expense lists, so that the balances always add up to zero.

## 3. Feature: skip blank lines and comments in an expenses file

A blank line, or a line that starts with `#`, stops `python3 -m tally` with a `ValueError`. Both should be skipped, so
that a file can be laid out and annotated.

## 4. Feature: `--json`

`python3 -m tally --json FILE` should print the payments as a JSON list of objects with `from`, `to` and `amount`, the
amount as text such as `12.50`, for other programs to read.
