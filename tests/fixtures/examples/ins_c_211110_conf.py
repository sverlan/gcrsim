# Python translation of ins_c_211110.cfg (Perl).
import re

history = True
show_detailed_application = True
print_hide = ""
print_max_len = 100
reject_strings = ""
reject_max_len = 100

# Reject strings in which the same pointer symbol occurs three times.
_REJECT = [
    re.compile(r"(e.).*\1.*\1", re.ASCII),
    re.compile(r"(f.).*\1.*\1", re.ASCII),
    re.compile(r"e\d\d", re.ASCII),
    re.compile(r"f\d\d", re.ASCII),
]
_TERMINAL = re.compile(r"^[a$ABY]+$", re.ASCII)


def filter_next(s, c):
    for rx in _REJECT:
        if rx.search(s):
            return False
    if _TERMINAL.search(s) and c == 0:  # component 1 (the argument is zero-based)
        print("Terminal?: " + s)
    return True
