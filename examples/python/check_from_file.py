# Checking against a long list of expected words kept in a file (a^n b^n for n up to 20), read from the folder of this file.
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED = set(open(os.path.join(HERE, "expected_anbn.txt")).read().split("\n"))

components = {1: {"marks": {"unexpected": {"pattern": r"\A[ab]*\Z", "expected": EXPECTED}}}}
