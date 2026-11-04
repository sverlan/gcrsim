# The expected terminal strings: a^n b^n for n = 0..20. In a real configuration this
# can come from a file, e.g.  EXPECTED = set(open("expected.txt").read().split("\n"))
EXPECTED = {"a" * n + "b" * n for n in range(21)}

print_max_len = 40
reject_max_len = 40

components = {
    1: {
        "marks": {
            # every string made only of terminal symbols is a terminal string; the expected
            # ones are not marked, so everything that is marked is a deviation from the plan
            "unexpected": {"pattern": r"\A[ab]*\Z", "expected": EXPECTED},
        },
    },
}
