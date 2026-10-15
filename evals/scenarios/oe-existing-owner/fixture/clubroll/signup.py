"""Joining the club."""
from .validation import check_email, check_name


def sign_up(store, address, name):
    """Add a member. Input the club's rules refuse raises ValueError (InvalidEmail or InvalidName), and so does an
    address that is already a member."""
    address = check_email(address)
    name = check_name(name)
    if store.has_member(address):
        raise ValueError(f"{address} is already a member")
    return store.add_member(address, name)
