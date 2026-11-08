# tally

Split shared expenses, and say who pays whom to settle them. It is a small Python package written for platoon-harness's
examples, each of which works on a copy of it, and [ISSUES.md](ISSUES.md) lists its known defects and the features asked
of it.

An expenses file has a line for each expense: who paid, how much, and the people it was for, separated by spaces, who may
include the payer. Each pays an equal share:

```console
$ cat trip.csv
ada,90.00,ada bob cy
bob,30.00,bob cy
cy,12.00,ada cy
$ python3 -m tally trip.csv
cy pays ada 39.00
bob pays ada 15.00
```

It needs Python 3.9 or later and nothing else. Its tests are the standard library's `unittest`:

```console
$ python3 -m unittest
```
