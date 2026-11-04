# ins_a_110200.cfg without a Python callback: the rejections are component
# conditions and the "Terminal?" message is a declarative mark.
history = True
show_detailed_application = False
print_hide = ""
print_max_len = 100
reject_strings = ""
reject_max_len = 100

components = {
    # stop after a triple occurrence of the same pointer symbol
    0: {"filters": {"forbid": [r"\A.*(p.).*\1.*\1.*\Z", r"\A.*(q.).*\1.*\1.*\Z"]}},
    # strings that passed every filter and consist only of terminal symbols (component 1)
    1: {"marks": {"terminal": {"pattern": r"\A[$ABY]+\Z", "message": "Terminal?: {string}"}}},
}
