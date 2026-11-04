r"""``gcrsim-convert`` and the conversion of Perl configurations."""
import subprocess
import sys

import gcrsim
from gcrsim.convert import convert_cfg
from conftest import CLI_ENV, CONVERT, PERL_FIXTURES

CFG = r'''# important parameters
$history = 1;
$show_detailed_application = 0;
$print_skip = "\@";  # no skip
$print_len = 100;
 $add_skip = "(p.).*\\1.*$";
 $add_skip_len = 40;
sub filter_next($$){
  return 1;
}
'''



def flat(toml):
    """The settings of converted configuration text (sections [model] and [run]) as one dictionary."""
    import tomllib

    return {k: v for section in tomllib.loads(toml).values() for k, v in section.items()}

def test_perl_configuration_becomes_toml():
    toml, warnings, has_filter = convert_cfg(CFG)
    assert has_filter and any("filter_next" in w for w in warnings)
    import tomllib

    data = flat(toml)
    assert data == {
        "history": True,
        "show_detailed_application": False,
        "print_hide": "",  # the Perl idiom for no skip
        "print_max_len": 100,
        "reject_strings": r"(p.).*\1.*\Z",  # the end anchor is now \Z
        "reject_max_len": 40,
    }


def test_anchors_inside_classes_stay():
    toml, _, _ = convert_cfg("$add_skip = '^[$AB]+$';\n")
    assert r"[$AB]+\Z" in toml


def test_convert_command_writes_model_and_conf(tmp_path):
    for name in ("ins_222.txt", "ins_222.cfg"):
        (tmp_path / name).write_bytes((PERL_FIXTURES / name).read_bytes())
    out = tmp_path / "new.txt"
    proc = subprocess.run(
        [*CONVERT, "ins_222.txt", "-o", str(out)],
        cwd=str(tmp_path), capture_output=True, env=CLI_ENV,
    )
    assert proc.returncode == 0, proc.stderr
    assert "print_max_len" in out.read_text()
    model = gcrsim.parse_model_file(str(out))
    assert model.ncomp == 1 and sum(len(r) for r in model.rules) > 30
    assert b"filter_next" in proc.stderr
    st = gcrsim.settings.resolve_config(model)
    assert st.print_max_len == 1000 and st.reject_strings == ""


def test_convert_command_to_stdout(tmp_path):
    (tmp_path / "m.txt").write_bytes(b"Axioms\n[a]\nRules\na->b\n")
    proc = subprocess.run([*CONVERT, "m.txt"], cwd=str(tmp_path), capture_output=True, env=CLI_ENV)
    assert proc.returncode == 0 and b'1 = ["a"]' in proc.stdout and b"a->b" in proc.stdout
    missing = subprocess.run([*CONVERT, "nope.txt"], cwd=str(tmp_path), capture_output=True, env=CLI_ENV)
    assert missing.returncode == 2


def test_perl_string_semantics():
    import tomllib

    toml, warnings, _ = convert_cfg(r'$add_skip = "a\\bz";' + "\n")  # \\ in a double-quoted string is one backslash
    assert flat(toml)["reject_strings"] == "a\\bz"
    toml, warnings, _ = convert_cfg(r'$add_skip = "\b";')  # backspace, not a word boundary
    assert flat(toml)["reject_strings"] == "\x08"
    toml, warnings, _ = convert_cfg(r'$add_skip = "\Q.\E";')
    assert toml == "" and warnings and "escape" in warnings[0]
    toml, warnings, _ = convert_cfg('$add_skip = "x$y";')
    assert toml == "" and "interpolates" in warnings[0]
    toml, warnings, _ = convert_cfg(r"$add_skip = 'a\\b';")  # single quotes: \\ is one backslash
    assert flat(toml)["reject_strings"] == "a\\b"


def test_perl_scalars():
    import tomllib

    toml, warnings, _ = convert_cfg('$history = "0";\n$show_detailed_application = undef;\n$print_len = 020;\n$add_skip_len = 1_000;')
    assert flat(toml) == {"history": False, "show_detailed_application": False, "print_max_len": 16, "reject_max_len": 1000}
    toml, _, _ = convert_cfg('$history = "0.0";')
    assert flat(toml)["history"] is True  # a true string in Perl


def test_config_directive_without_a_space_and_the_default_cfg(tmp_path):
    (tmp_path / "old.cfg").write_bytes(b"$print_len = 33;\n")
    (tmp_path / "m.txt").write_bytes(b"ConfigFileold.cfg\nAxioms\n[a]\nRules\na->b\n")
    out = tmp_path / "new.txt"
    proc = subprocess.run([*CONVERT, "m.txt", "-o", str(out)], cwd=str(tmp_path), capture_output=True, env=CLI_ENV)
    assert proc.returncode == 0 and "print_max_len = 33" in out.read_text()
    (tmp_path / "gcrsim.cfg").write_bytes(b"$print_len = 44;\n")
    (tmp_path / "n.txt").write_bytes(b"Axioms\n[a]\nRules\na->b\n")
    proc = subprocess.run([*CONVERT, "n.txt", "-o", str(tmp_path / "n2.txt")], cwd=str(tmp_path), capture_output=True, env=CLI_ENV)
    assert "print_max_len = 44" in (tmp_path / "n2.txt").read_text()


def test_converted_rules_are_validated_and_overlaps_are_flagged():
    new, warnings = gcrsim.convert_model("Axioms\n[a]\nRules\na->X,1;permit:a->b\na->X,1;permit:\n")
    assert len(warnings) == 2 and all("not converted" in w for w in warnings)
    assert new.count("# not converted") == 2
    new, warnings = gcrsim.convert_model("Axioms\n[aaa]\nRules\naa->b\nab->c\n")
    assert len(warnings) == 1 and "overlap" in warnings[0] and "'aa'" in warnings[0]


def test_converter_warns_about_regex_rules_that_can_overlap():
    from gcrsim.convert import convert_model
    _, warnings = convert_model("Axioms\n[aaa]\nRules\n(a+)->X\n")
    assert any("several lengths" in w for w in warnings)
