from scripts.password_utils import generate_password, validate_password


def test_generate_password_letters_first():
    pwd = generate_password(2, 4, letters_first=True)
    assert len(pwd) == 6
    assert pwd[:2].isalpha() and pwd[:2].islower()
    assert pwd[2:].isdigit()


def test_generate_password_digits_first():
    pwd = generate_password(2, 4, letters_first=False)
    assert len(pwd) == 6
    assert pwd[:4].isdigit()
    assert pwd[4:].isalpha()


def test_generate_password_valid_length():
    assert validate_password(generate_password(3, 3, True))
    assert validate_password(generate_password(10, 6, False))


def test_invalid_total_length_raises():
    try:
        generate_password(1, 1, True)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_validate_password_rules():
    assert not validate_password("abc12")
    assert not validate_password("a" * 17)
    assert not validate_password("abc@123")
    assert validate_password("ab1234")
