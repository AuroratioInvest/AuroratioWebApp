import pytest
from fastapi import HTTPException

from dependencies import (
    create_access_token,
    get_active_user,
    get_current_user,
    require_active_admin,
    require_admin,
)
from models import MembershipLevel, User


def _user(*, email: str, membership: MembershipLevel, active: bool = True) -> User:
    return User(
        email=email,
        hashed_password="not-used-by-these-tests",
        membership_level=membership,
        is_active=active,
    )


def test_admin_token_authenticates_and_authorizes(db_session):
    admin = _user(email="admin@example.com", membership=MembershipLevel.aurum)
    db_session.add(admin)
    db_session.commit()

    token = create_access_token(admin.id)
    authenticated = get_current_user(token=token, db=db_session)

    assert authenticated.id == admin.id
    assert require_admin(authenticated).id == admin.id
    assert require_active_admin(authenticated).id == admin.id


def test_non_admin_is_forbidden(db_session):
    customer = _user(email="customer@example.com", membership=MembershipLevel.classic)
    db_session.add(customer)
    db_session.commit()

    authenticated = get_current_user(
        token=create_access_token(customer.id),
        db=db_session,
    )

    with pytest.raises(HTTPException) as exc_info:
        require_admin(authenticated)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin access required"


def test_inactive_admin_is_rejected_by_active_admin_guard(db_session):
    admin = _user(
        email="inactive-admin@example.com",
        membership=MembershipLevel.aurum,
        active=False,
    )
    db_session.add(admin)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        require_active_admin(get_active_user(admin))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Account suspended"


def test_invalid_token_is_rejected(db_session):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token="not-a-valid-jwt", db=db_session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"
