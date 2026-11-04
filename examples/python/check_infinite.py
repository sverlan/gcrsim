# Checking against an infinite language. The expected language, { a^n b^n }, is not regular, so no regular expression says "equal
# numbers"; a function does (pure(...) says that it has no state, so --streaming can be used). Every terminal word of the grammar is marked "unexpected" unless the function says that it is fine.
components = {
    1: {
        "marks": {
            "unexpected": {
                "pattern": r"\A[ab]*\Z",
                "expected_re": pure(lambda s: s == "a" * (len(s) // 2) + "b" * (len(s) // 2)),
            }
        }
    },
}
