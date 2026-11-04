# Python translation of ins_b_110200.cfg (Perl).
import re

history = True
show_detailed_application = True
print_hide = ""
print_max_len = 100
reject_strings = ""
reject_max_len = 100

_REJECT = [
    re.compile(r"(p.).*\1.*\1", re.ASCII),
    re.compile(r"(f.).*\1.*\1", re.ASCII),
    re.compile(r"p\d\d", re.ASCII),
    re.compile(r"f\d\d", re.ASCII),
]
_TERMINAL = re.compile(r"^[$ABY]+$", re.ASCII)


def filter_next(s, c):
    for rx in _REJECT:
        if rx.search(s):
            return False
    if _TERMINAL.search(s) and c == 0:
        print("Terminal?: " + s)
    return True
