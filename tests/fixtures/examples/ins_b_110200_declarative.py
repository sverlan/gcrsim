# ins_b_110200.cfg without a Python callback (compare ins_b_110200.py).
history = True
show_detailed_application = True
print_hide = ""
print_max_len = 100
reject_strings = ""
reject_max_len = 100

components = {
    0: {  # every component
        "filters": {"forbid": [r"(p.).*\1.*\1", r"(f.).*\1.*\1", r"p\d\d", r"f\d\d"]},
    },
    1: {"marks": {"terminal": r"\A[$ABY]+\Z"}},
}
