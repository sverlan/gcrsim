# Marks every terminal word (only a's and b's) and keeps it.
import re

print_max_len = 30
reject_max_len = 30
_WORD = re.compile(r"^[ab]*$")


def filter_next(s, component, ctx):
    if component == 0 and _WORD.match(s):
        ctx.mark("terminal")
    return True
