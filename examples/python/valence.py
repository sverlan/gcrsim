# The gate and the mark of the valence grammar. A function in the filters of component 2 lets a word in only when its weights add up
# to zero; the mark flags the clean words that come out of component 3. pure(...) says that the function has no state, so that
# --streaming can be used (the name pure is available in a Python file, like lit).
components = {
    2: {"filters": {"require": [pure(lambda s: s.count("P") == s.count("M"))]}},
    3: {"marks": {"terminal": r"\A[ab]*\Z"}},
}
