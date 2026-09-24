from scripts.silent_failure_gate import inspect_source


def test_detects_bare_except():
    findings = inspect_source("try:\n    work()\nexcept:\n    recover()\n")
    assert [finding.rule for finding in findings] == ["ARENA-SF001"]


def test_detects_exception_swallowed_with_pass():
    findings = inspect_source("try:\n    work()\nexcept ValueError:\n    pass\n")
    assert [finding.rule for finding in findings] == ["ARENA-SF002"]


def test_allows_explicit_logged_or_propagated_handling():
    source = """try:
    work()
except ValueError as exc:
    logger.warning("work failed: %s", exc)
    raise
"""
    assert inspect_source(source) == []


def test_bare_except_with_pass_reports_both_reasons():
    findings = inspect_source("try:\n    work()\nexcept:\n    pass\n")
    assert {finding.rule for finding in findings} == {"ARENA-SF001", "ARENA-SF002"}
