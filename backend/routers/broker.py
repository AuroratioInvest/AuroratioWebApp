from datetime import datetime, timezone, timedelta
import logging
import os
import traceback
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from snaptrade_client import SnapTrade
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_active_user
from models import BrokerConnection, ConnectionStatus, Position, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

snaptrade = SnapTrade(
    consumer_key=os.getenv("SNAPTRADE_CONSUMER_KEY"),
    client_id=os.getenv("SNAPTRADE_CLIENT_ID"),
)

_pending_credentials: dict[str, dict[str, str]] = {}


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _is_connected(connection: BrokerConnection) -> bool:
    return bool(connection.is_active) or connection.status == ConnectionStatus.active


def _connection_payload(connection: BrokerConnection):
    raw_status = _status_value(connection.status)
    connected = _is_connected(connection)

    time_waiting = None
    connected_at = _ensure_aware(connection.connected_at)

    if not connected and connected_at:
        time_waiting = int((_utc_now() - connected_at).total_seconds())

    return {
        "id": connection.id,
        "broker_name": connection.broker_name or "Unknown",
        "account_name": connection.snaptrade_account_id,
        "account_id": connection.snaptrade_account_id,
        "is_active": connected,
        "status": raw_status,
        "connected_at": connection.connected_at.isoformat()
        if connection.connected_at
        else None,
        "time_waiting": time_waiting,
        "can_display_portfolio": connection.can_display_portfolio,
        "can_execute_trades": connection.can_execute_trades,
        "role": "display_only",
    }


def _generate_snaptrade_user_id(current_user: User) -> str:
    return f"auroratio-{current_user.id}-{uuid.uuid4().hex}"


def _find_connection_by_snaptrade_user(
    db: Session,
    snaptrade_user_id: str | None,
    event_type: str,
):
    if not snaptrade_user_id:
        logger.warning("Ignoring SnapTrade webhook %s because userId is missing", event_type)
        return None

    connection = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.snaptrade_user_id == snaptrade_user_id)
        .first()
    )

    if not connection:
        logger.warning(
            "Ignoring SnapTrade webhook %s for unknown SnapTrade user: %s",
            event_type,
            snaptrade_user_id,
        )
        return None

    return connection


def _cleanup_stale_connections(
    db: Session,
    user_id: str,
    max_age_minutes: int = 15,
) -> int:
    cutoff = _utc_now() - timedelta(minutes=max_age_minutes)

    stale_connections = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.user_id == user_id,
            BrokerConnection.status == ConnectionStatus.pending,
            BrokerConnection.connected_at < cutoff,
        )
        .all()
    )

    for connection in stale_connections:
        db.query(Position).filter(
            Position.broker_connection_id == connection.id
        ).delete(synchronize_session=False)

        _pending_credentials.pop(user_id, None)
        db.delete(connection)

    if stale_connections:
        db.commit()

    return len(stale_connections)


def _should_ignore_downgrade(connection: BrokerConnection, event_type: str) -> bool:
    if not _is_connected(connection):
        return False

    return event_type in {"CONNECTION_ATTEMPTED"}


def _extract_broker_name_from_webhook(payload: dict) -> str | None:
    brokerage = (
        payload.get("brokerage")
        or payload.get("brokerageAuthorization", {}).get("brokerage")
    )

    if isinstance(brokerage, dict):
        return brokerage.get("name")

    return None


@router.post("/connect")
def connect_broker(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """
    SnapTrade connection is display/read-only in the FA architecture.

    IBKR FA execution is handled separately through:
    - FA authorization
    - IBKR client sub-account mapping
    - virtual module ledger
    """
    try:
        _cleanup_stale_connections(db, current_user.id)

        old_inactive_connections = (
            db.query(BrokerConnection)
            .filter(
                BrokerConnection.user_id == current_user.id,
                BrokerConnection.status.in_(
                    [
                        ConnectionStatus.failed,
                        ConnectionStatus.disconnected,
                    ]
                ),
            )
            .all()
        )

        for old_connection in old_inactive_connections:
            db.query(Position).filter(
                Position.broker_connection_id == old_connection.id
            ).delete(synchronize_session=False)
            db.delete(old_connection)

        if old_inactive_connections:
            db.commit()

        existing_connection = (
            db.query(BrokerConnection)
            .filter(BrokerConnection.user_id == current_user.id)
            .order_by(BrokerConnection.connected_at.desc())
            .first()
        )

        if existing_connection and _is_connected(existing_connection):
            raise HTTPException(status_code=400, detail="Broker already connected")

        if current_user.id in _pending_credentials:
            creds = _pending_credentials[current_user.id]
            snaptrade_user_id = creds["snaptrade_user_id"]
            snaptrade_user_secret = creds["snaptrade_user_secret"]

        elif (
            existing_connection
            and existing_connection.snaptrade_user_id
            and existing_connection.snaptrade_user_secret
        ):
            snaptrade_user_id = existing_connection.snaptrade_user_id
            snaptrade_user_secret = existing_connection.snaptrade_user_secret

        else:
            try:
                generated_user_id = _generate_snaptrade_user_id(current_user)

                response = snaptrade.authentication.register_snap_trade_user(
                    body={"userId": generated_user_id}
                )

                snaptrade_user_id = response.body["userId"]
                snaptrade_user_secret = response.body["userSecret"]

            except Exception as exc:
                logger.exception("Could not register SnapTrade user")
                raise HTTPException(
                    status_code=500,
                    detail=f"Could not create SnapTrade connection: {str(exc)}",
                )

        _pending_credentials[current_user.id] = {
            "snaptrade_user_id": snaptrade_user_id,
            "snaptrade_user_secret": snaptrade_user_secret,
        }

        if existing_connection:
            existing_connection.snaptrade_user_id = snaptrade_user_id
            existing_connection.snaptrade_user_secret = snaptrade_user_secret
            existing_connection.status = ConnectionStatus.pending
            existing_connection.is_active = False
            existing_connection.broker_name = "Pending"
            existing_connection.snaptrade_account_id = None
            existing_connection.connected_at = _utc_now()
            existing_connection.can_display_portfolio = True
            existing_connection.can_execute_trades = False
            connection = existing_connection
        else:
            connection = BrokerConnection(
                user_id=current_user.id,
                broker_name="Pending",
                snaptrade_user_id=snaptrade_user_id,
                snaptrade_user_secret=snaptrade_user_secret,
                status=ConnectionStatus.pending,
                is_active=False,
                connected_at=_utc_now(),
                can_display_portfolio=True,
                can_execute_trades=False,
            )
            db.add(connection)

        db.commit()
        db.refresh(connection)

        connection_type = os.getenv("SNAPTRADE_CONNECTION_TYPE", "read")

        try:
            login = snaptrade.authentication.login_snap_trade_user(
                query_params={
                    "userId": snaptrade_user_id,
                    "userSecret": snaptrade_user_secret,
                },
                body={
                    "immediateRedirect": True,
                    "customRedirect": f"{_frontend_url()}/onboarding?connected=true",
                    "connectionType": connection_type,
                },
            )

            redirect_url = login.body.get("redirectURI")

            if not redirect_url:
                raise HTTPException(
                    status_code=500,
                    detail="SnapTrade did not return a redirect URL",
                )

            return {
                "redirect_url": redirect_url,
                "role": "display_only",
                "execution_provider": "ibkr_fa",
            }

        except HTTPException:
            raise

        except Exception as exc:
            logger.exception("SnapTrade login failed")
            raise HTTPException(
                status_code=500,
                detail=f"SnapTrade login failed: {str(exc)}",
            )

    except HTTPException:
        raise

    except Exception:
        logger.error("Error in connect_broker")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to start broker connection")


@router.get("/connections")
def get_connections(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    connections = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.user_id == current_user.id)
        .order_by(BrokerConnection.connected_at.desc())
        .all()
    )

    return [_connection_payload(connection) for connection in connections]


@router.delete("/disconnect")
def disconnect_broker(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.user_id == current_user.id)
        .order_by(BrokerConnection.connected_at.desc())
        .first()
    )

    if not connection:
        raise HTTPException(status_code=404, detail="No connection found")

    try:
        db.query(Position).filter(
            Position.user_id == current_user.id,
            Position.broker_connection_id == connection.id,
        ).delete(synchronize_session=False)

        if connection.snaptrade_user_id:
            try:
                snaptrade.authentication.delete_snap_trade_user(
                    user_id=connection.snaptrade_user_id
                )
            except Exception as exc:
                logger.warning("SnapTrade delete warning: %s", exc)

        _pending_credentials.pop(current_user.id, None)

        db.delete(connection)
        db.commit()

        return {"status": "disconnected"}

    except Exception as exc:
        db.rollback()
        logger.exception("Error disconnecting broker")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to disconnect broker: {str(exc)}",
        )


@router.post("/webhook/snaptrade")
async def snaptrade_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    event_type = payload.get("eventType")
    snaptrade_user_id = payload.get("userId")

    expected_secret = os.getenv("SNAPTRADE_WEBHOOK_SECRET")

    if expected_secret:
        received_secret = payload.get("webhookSecret")
        if received_secret != expected_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    if event_type in {"TEST_WEBHOOK", "USER_REGISTERED"}:
        return {"status": "ok"}

    connection = _find_connection_by_snaptrade_user(db, snaptrade_user_id, event_type)

    if not connection:
        return {"status": "ignored"}

    if event_type == "USER_DELETED":
        db.query(Position).filter(
            Position.broker_connection_id == connection.id
        ).delete(synchronize_session=False)

        db.delete(connection)
        db.commit()
        return {"status": "ok"}

    if _should_ignore_downgrade(connection, event_type):
        return {"status": "ignored"}

    if event_type == "CONNECTION_ATTEMPTED":
        result = payload.get("connectionAttemptedResult")
        if result == "SUCCESS":
            connection.status = ConnectionStatus.connecting
        else:
            connection.status = ConnectionStatus.failed
            connection.is_active = False
        db.commit()
        return {"status": "ok"}

    if event_type == "NEW_ACCOUNT_AVAILABLE":
        account_id = payload.get("accountId")

        if account_id:
            connection.snaptrade_account_id = account_id

        connection.status = ConnectionStatus.syncing
        connection.is_active = True
        connection.can_display_portfolio = True
        connection.can_execute_trades = False

        broker_name = _extract_broker_name_from_webhook(payload)
        if broker_name:
            connection.broker_name = broker_name
        elif not connection.broker_name or connection.broker_name in ("Pending", "Unknown"):
            connection.broker_name = "Unknown"

        db.commit()
        return {"status": "ok"}

    if event_type in {"CONNECTION_ADDED", "CONNECTION_CREATED", "ACCOUNT_HOLDINGS_UPDATED"}:
        account_id = payload.get("accountId")

        if account_id:
            connection.snaptrade_account_id = account_id

        broker_name = _extract_broker_name_from_webhook(payload)
        if broker_name:
            connection.broker_name = broker_name
        elif not connection.broker_name or connection.broker_name in ("Pending", "Unknown"):
            connection.broker_name = "Unknown"

        connection.status = ConnectionStatus.active
        connection.is_active = True
        connection.can_display_portfolio = True
        connection.can_execute_trades = False

        db.commit()
        return {"status": "ok"}

    logger.info("Unhandled SnapTrade webhook event: %s", event_type)
    return {"status": "ok"}