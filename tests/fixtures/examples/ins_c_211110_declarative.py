# ins_c_211110.cfg without a Python callback (compare ins_c_211110.py).
history = True
show_detailed_application = True
print_hide = ""
print_max_len = 100
reject_strings = ""
reject_max_len = 100

components = {
    0: {"filters": {"forbid": [r"(e.).*\1.*\1", r"(f.).*\1.*\1", r"e\d\d", r"f\d\d"]}},
    1: {"marks": {"terminal": r"\A[a$ABY]+\Z"}},
}
