import pytest
from lakmus.schemas import CheckInput, CheckResult, CheckStatus, InputType, Trust
from lakmus.validate import validate_check_result


def test_validate_check_result_ok():
    result = CheckResult(
        id="r1",
        status=CheckStatus.done,
        input=CheckInput(type=InputType.text, extracted_text="hello"),
        trust=Trust(score=50),
    )
    validated = validate_check_result(result)
    assert validated.id == "r1"


def test_validate_check_result_dict_ok():
    data = {
        "id": "r2",
        "status": "done",
        "input": {"type": "text", "extracted_text": "hello"},
        "trust": {"score": 30},
    }
    validated = validate_check_result(data)
    assert validated["id"] == "r2"


def test_validate_check_result_missing_required():
    data = {"status": "done"}
    with pytest.raises(ValueError):
        validate_check_result(data)
