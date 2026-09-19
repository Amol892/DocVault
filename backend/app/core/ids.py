import secrets
import string

ID_LENGTH = 12

_FIRST_CHARS = string.ascii_letters
_OTHER_CHARS = string.digits + string.ascii_letters


def generate_random_id(length: int = ID_LENGTH) -> str:
    """Random primary key: base62, first character always a letter (52 * 62**11 ~ 3e21 keys).

    Prevents enumeration and leakage of row counts. It is not an access control; authorization
    lives in api/deps.py. The primary-key constraint is the backstop for the (practically
    impossible) collision.
    """
    return secrets.choice(_FIRST_CHARS) + "".join(
        secrets.choice(_OTHER_CHARS) for _ in range(length - 1)
    )
