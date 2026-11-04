# Python translation of ins_a_110200.cfg (Perl).
import re

history = True
show_detailed_application = False
print_hide = ""
print_max_len = 100
reject_strings = ""
reject_max_len = 100

# Stop after a triple occurrence of the same pointer symbol.
_TRIPLE_P = re.compile(r"^.*(p.).*\1.*\1.*$", re.ASCII)
_TRIPLE_Q = re.compile(r"^.*(q.).*\1.*\1.*$", re.ASCII)
_TERMINAL = re.compile(r"^[$ABY]+$", re.ASCII)


def filter_next(s, c):
    """Reject strings with three occurrences of a pointer; report terminals."""
    if _TRIPLE_P.search(s):
        return False
    if _TRIPLE_Q.search(s):
        return False
    if _TERMINAL.search(s) and c == 0:  # component 1 (the argument is zero-based)
        print("Terminal?: " + s)
    return True
