from appscreenmap.security.applogs import masker


def test_masks_typed_secrets_and_token_shaped_values():
    mask = masker(["hunter22", None, "abc"])  # too-short values are ignored: they would mask ordinary words
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbHBoYSJ9.c2lnbmF0dXJlLXZhbHVl"
    line = f"login alpha/hunter22 ok; Authorization: Bearer {'x' * 24}; id_token={jwt}; abc; key AKIAABCDEFGHIJKLMNOP"
    out = mask(line)
    assert (
        "hunter22" not in out and "x" * 24 not in out and jwt not in out and "AKIAABCDEFGHIJKLMNOP" not in out
    )
    assert "login alpha/•••• ok" in out
    assert "[Bearer token · sha " in out and "[JWT · sha " in out and "[AWS access key id · sha " in out
    assert "; abc;" in out
