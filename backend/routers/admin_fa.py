from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_active_admin
from models import (
    FAAuthorization,
    FAAuthorizationStatus,
    IBKRAccountMapping,
    TradingProvider,
    User,
    UserBotState,
    UserModulePosition,
)
from schemas import (
    FAAuthorizationCreate,
    FAAuthorizationResponse,
    FAAuthorizationUpdate,
    IBKRAccountMappingCreate,
    IBKRAccountMappingResponse,
    IBKRAccountMappingUpdate,
    UserModulePositionCreate,
    UserModulePositionResponse,
    UserModulePositionUpdate,
    UserTradingControlsUpdate,
)
from services.fa_service import (
    activate_fa_authorization,
    disable_user_trading,
    enable_user_trading,
    get_or_create_fa_authorization,
    get_or_create_module_positions,
    get_or_create_user_bot_state,
    set_fa_status,
    set_user_module_enabled,
    upsert_ibkr_account_mapping,
)

router = APIRouter(
    prefix="/admin/fa",
    tags=["Admin FA"],
)


def utc_now():
    return datetime.now(timezone.utc)


def get_user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def parse_fa_status(status: str) -> FAAuthorizationStatus:
    try:
        return FAAuthorizationStatus(status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid FA status: {status}",
        )


@router.get("/users")
def list_fa_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    users = db.query(User).order_by(User.created_at.desc()).all()

    result = []
    for user in users:
        authorization = (
            db.query(FAAuthorization)
            .filter(FAAuthorization.user_id == user.id)
            .first()
        )
        mapping = (
            db.query(IBKRAccountMapping)
            .filter(IBKRAccountMapping.user_id == user.id)
            .first()
        )
        state = (
            db.query(UserBotState)
            .filter(UserBotState.user_id == user.id)
            .first()
        )

        result.append(
            {
                "user_id": user.id,
                "email": user.email,
                "is_active": user.is_active,
                "trading_enabled": user.trading_enabled,
                "preferred_trading_provider": user.preferred_trading_provider.value
                if user.preferred_trading_provider
                else None,
                "fa_status": authorization.status.value if authorization else None,
                "ibkr_client_account_id": mapping.ibkr_client_account_id if mapping else None,
                "advisor_master_account_id": mapping.advisor_master_account_id if mapping else None,
                "mapping_active": mapping.is_active if mapping else False,
                "mapping_trading_enabled": mapping.trading_enabled if mapping else False,
                "bot_state_trading_enabled": state.trading_enabled if state else False,
            }
        )

    return result


@router.get("/users/{user_id}")
def get_fa_user_detail(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, user_id)

    authorization = (
        db.query(FAAuthorization)
        .filter(FAAuthorization.user_id == user.id)
        .first()
    )
    mapping = (
        db.query(IBKRAccountMapping)
        .filter(IBKRAccountMapping.user_id == user.id)
        .first()
    )
    state = (
        db.query(UserBotState)
        .filter(UserBotState.user_id == user.id)
        .first()
    )
    module_positions = (
        db.query(UserModulePosition)
        .filter(UserModulePosition.user_id == user.id)
        .order_by(UserModulePosition.module_name.asc())
        .all()
    )

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "trading_enabled": user.trading_enabled,
            "preferred_trading_provider": user.preferred_trading_provider.value
            if user.preferred_trading_provider
            else None,
        },
        "fa_authorization": FAAuthorizationResponse.model_validate(authorization).model_dump()
        if authorization
        else None,
        "ibkr_account_mapping": IBKRAccountMappingResponse.model_validate(mapping).model_dump()
        if mapping
        else None,
        "user_bot_state": {
            "trading_enabled": state.trading_enabled,
            "m1_enabled": state.m1_enabled,
            "m2_enabled": state.m2_enabled,
            "m3_enabled": state.m3_enabled,
            "m1_position": state.m1_position,
            "m2_position": state.m2_position,
            "m3_position": state.m3_position,
        }
        if state
        else None,
        "module_positions": [
            UserModulePositionResponse.model_validate(position).model_dump()
            for position in module_positions
        ],
    }


@router.post("/authorizations", response_model=FAAuthorizationResponse)
def create_fa_authorization(
    payload: FAAuthorizationCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, payload.user_id)

    existing = (
        db.query(FAAuthorization)
        .filter(FAAuthorization.user_id == user.id)
        .first()
    )
    if existing:
        return existing

    authorization = FAAuthorization(
        user_id=user.id,
        status=FAAuthorizationStatus.pending_authorization,
        advisor_master_account_id=payload.advisor_master_account_id,
        ibkr_client_account_id=payload.ibkr_client_account_id,
        authorization_reference=payload.authorization_reference,
        notes=payload.notes,
        requested_at=utc_now(),
    )
    db.add(authorization)

    get_or_create_user_bot_state(db, user)
    get_or_create_module_positions(db, user)

    db.commit()
    db.refresh(authorization)
    return authorization


@router.patch("/authorizations/{user_id}", response_model=FAAuthorizationResponse)
def update_fa_authorization(
    user_id: str,
    payload: FAAuthorizationUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, user_id)
    authorization = get_or_create_fa_authorization(db, user)

    if payload.status is not None:
        status = parse_fa_status(payload.status)
        authorization = set_fa_status(
            db=db,
            user=user,
            status=status,
            notes=payload.notes,
        )

    if payload.advisor_master_account_id is not None:
        authorization.advisor_master_account_id = payload.advisor_master_account_id

    if payload.ibkr_client_account_id is not None:
        authorization.ibkr_client_account_id = payload.ibkr_client_account_id

    if payload.authorization_reference is not None:
        authorization.authorization_reference = payload.authorization_reference

    if payload.notes is not None:
        authorization.notes = payload.notes

    db.commit()
    db.refresh(authorization)
    return authorization


@router.post("/authorizations/{user_id}/activate")
def activate_user_fa(
    user_id: str,
    payload: IBKRAccountMappingCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    if payload.user_id != user_id:
        raise HTTPException(
            status_code=400,
            detail="Payload user_id does not match URL user_id",
        )

    user = get_user_or_404(db, user_id)

    authorization, mapping = activate_fa_authorization(
        db=db,
        user=user,
        advisor_master_account_id=payload.advisor_master_account_id,
        ibkr_client_account_id=payload.ibkr_client_account_id,
        account_alias=payload.account_alias,
        base_currency=payload.base_currency,
    )

    mapping.is_active = payload.is_active
    mapping.trading_enabled = payload.trading_enabled

    db.commit()
    db.refresh(authorization)
    db.refresh(mapping)

    return {
        "message": "FA authorization activated. Trading remains disabled until explicitly enabled.",
        "fa_authorization": FAAuthorizationResponse.model_validate(authorization).model_dump(),
        "ibkr_account_mapping": IBKRAccountMappingResponse.model_validate(mapping).model_dump(),
    }


@router.post("/mappings", response_model=IBKRAccountMappingResponse)
def create_or_update_mapping(
    payload: IBKRAccountMappingCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, payload.user_id)

    mapping = upsert_ibkr_account_mapping(
        db=db,
        user=user,
        advisor_master_account_id=payload.advisor_master_account_id,
        ibkr_client_account_id=payload.ibkr_client_account_id,
        account_alias=payload.account_alias,
        base_currency=payload.base_currency,
        is_active=payload.is_active,
        trading_enabled=payload.trading_enabled,
    )

    db.commit()
    db.refresh(mapping)
    return mapping


@router.patch("/mappings/{user_id}", response_model=IBKRAccountMappingResponse)
def update_mapping(
    user_id: str,
    payload: IBKRAccountMappingUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, user_id)

    mapping = (
        db.query(IBKRAccountMapping)
        .filter(IBKRAccountMapping.user_id == user.id)
        .first()
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="IBKR account mapping not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(mapping, key, value)

    if payload.trading_enabled is False:
        disable_user_trading(db, user)

    db.commit()
    db.refresh(mapping)
    return mapping


@router.patch("/users/{user_id}/trading-controls")
def update_user_trading_controls(
    user_id: str,
    payload: UserTradingControlsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, user_id)
    state = get_or_create_user_bot_state(db, user)
    get_or_create_module_positions(db, user)

    if payload.preferred_trading_provider is not None:
        try:
            user.preferred_trading_provider = TradingProvider(payload.preferred_trading_provider)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trading provider: {payload.preferred_trading_provider}",
            )

    if payload.trading_enabled is not None:
        try:
            if payload.trading_enabled:
                enable_user_trading(db, user)
            else:
                disable_user_trading(db, user)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    if payload.m1_enabled is not None:
        set_user_module_enabled(db, user, "M1", payload.m1_enabled)

    if payload.m2_enabled is not None:
        set_user_module_enabled(db, user, "M2", payload.m2_enabled)

    if payload.m3_enabled is not None:
        set_user_module_enabled(db, user, "M3", payload.m3_enabled)

    db.commit()
    db.refresh(user)
    db.refresh(state)

    return {
        "message": "Trading controls updated",
        "user_id": user.id,
        "trading_enabled": user.trading_enabled,
        "preferred_trading_provider": user.preferred_trading_provider.value,
        "modules": {
            "M1": state.m1_enabled,
            "M2": state.m2_enabled,
            "M3": state.m3_enabled,
        },
    }


@router.post("/users/{user_id}/enable-trading")
def enable_trading(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, user_id)

    try:
        state = enable_user_trading(db, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()
    db.refresh(user)
    db.refresh(state)

    return {
        "message": "Trading enabled",
        "user_id": user.id,
        "trading_enabled": user.trading_enabled,
    }


@router.post("/users/{user_id}/disable-trading")
def disable_trading(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, user_id)
    disable_user_trading(db, user)

    db.commit()
    db.refresh(user)

    return {
        "message": "Trading disabled",
        "user_id": user.id,
        "trading_enabled": user.trading_enabled,
    }


@router.get("/users/{user_id}/module-positions")
def list_module_positions(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, user_id)
    get_or_create_module_positions(db, user)
    db.commit()

    positions = (
        db.query(UserModulePosition)
        .filter(UserModulePosition.user_id == user.id)
        .order_by(UserModulePosition.module_name.asc())
        .all()
    )

    return [
        UserModulePositionResponse.model_validate(position).model_dump()
        for position in positions
    ]


@router.post("/module-positions", response_model=UserModulePositionResponse)
def create_module_position(
    payload: UserModulePositionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    user = get_user_or_404(db, payload.user_id)

    existing = (
        db.query(UserModulePosition)
        .filter(
            UserModulePosition.user_id == user.id,
            UserModulePosition.module_name == payload.module_name.upper(),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Module position already exists for this user/module",
        )

    position = UserModulePosition(
        user_id=user.id,
        module_name=payload.module_name.upper(),
        metal=payload.metal.upper(),
        etf_symbol=payload.etf_symbol.upper(),
        quantity=payload.quantity,
        last_value_chf=payload.last_value_chf,
        is_enabled=payload.is_enabled,
    )

    db.add(position)
    db.commit()
    db.refresh(position)
    return position


@router.patch("/module-positions/{position_id}", response_model=UserModulePositionResponse)
def update_module_position(
    position_id: str,
    payload: UserModulePositionUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    position = (
        db.query(UserModulePosition)
        .filter(UserModulePosition.id == position_id)
        .first()
    )
    if not position:
        raise HTTPException(status_code=404, detail="Module position not found")

    update_data = payload.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if key in {"metal", "etf_symbol"} and isinstance(value, str):
            value = value.upper()
        setattr(position, key, value)

    db.commit()
    db.refresh(position)
    return position
