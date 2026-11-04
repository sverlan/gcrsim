# ins_222.cfg without a Python callback (compare ins_222.py): one declarative mark
# with a custom message instead of a callback that prints.
history = True
print_hide = ""
print_max_len = 1000
reject_strings = ""
reject_max_len = 1000

# One line: verbose mode (?x) is not allowed in patterns, because # is an ordinary symbol.
TERMINAL = (r"\A(?:A|C|B|D|c)*" r"(?:\$(?:E|X|Y|Z|S|U|B|A|C|B|D|K|L|O|R)|\#(?:P|Q|V))*" r"\Z")

components = {
    1: {"marks": {"terminal": {"pattern": TERMINAL, "message": "!!Terminal!!:{string} ({component})"}}},
}
