# Python translation of ins_222.cfg (Perl).
import re

history = True
print_hide = ""
print_max_len = 1000
reject_strings = ""
reject_max_len = 1000

# The original is a /x regex with a multi-line body; re.VERBOSE is the same.
_TERMINAL = re.compile(
    r"""^
       (A|C|B|D|c)*
       (
         \$(E|X|Y|Z|S|U|B|A|C|B|D|K|L|O|R) |
         \#(P|Q|V)
       )*
       $""",
    re.ASCII | re.VERBOSE,
)


def filter_next(s, c):
    if _TERMINAL.search(s) and c == 0:
        print("!!Terminal!!:%s (%d)" % (s, c + 1))
    return True
