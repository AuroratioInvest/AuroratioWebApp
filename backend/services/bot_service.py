import sys, os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(BASE_DIR)

from sqlalchemy.orm import Session
from models import BotState
from datetime import datetime, timezone
from state import load_state

STATE_FILE = os.path.join(BASE_DIR, "state.json")


def get_or_create_bot_state(db: Session) -> BotState:
    """
    Load bot state from database.
    If no row exists yet, seed it from state.json (or defaults).
    """
    bot_state = db.query(BotState).filter(BotState.id == 1).first()
    
    if bot_state is None:
        # Load from state.json - call without arguments
        try:
            state = load_state()  # ← Changed: no arguments
            
            bot_state = BotState(
                id               = 1,
                m1_position      = state["module1"]["position"],
                m1_silver_days   = state["module1"]["silver_days"],
                m2_position      = state["module2"]["position"],
                m2_platinum_days = state["module2"]["platinum_days"],
                m3_position      = state["module3"]["position"],
                m3_palladium_days = state["module3"]["palladium_days"],
            )
        except (FileNotFoundError, KeyError) as e:
            # state.json missing or wrong format - use defaults
            print(f"⚠️  Could not load state.json ({e}), using defaults")
            bot_state = BotState(
                id               = 1,
                m1_position      = "GOLD",
                m1_silver_days   = 0,
                m2_position      = "GOLD",
                m2_platinum_days = 0,
                m3_position      = "GOLD",
                m3_palladium_days = 0,
            )
        
        db.add(bot_state)
        db.commit()
        db.refresh(bot_state)
    
    return bot_state


def sync_bot_state_from_file(db: Session) -> BotState:
    """
    Force re-sync database bot_state from state.json.
    Called after the daily cycle runs to keep database in sync.
    """
    try:
        state = load_state()  # ← Changed: no arguments
    except FileNotFoundError:
        print(f"⚠️  state.json not found, skipping sync")
        return get_or_create_bot_state(db)
    
    bot_state = db.query(BotState).filter(BotState.id == 1).first()

    if bot_state is None:
        return get_or_create_bot_state(db)

    bot_state.m1_position       = state["module1"]["position"]
    bot_state.m1_silver_days    = state["module1"]["silver_days"]
    bot_state.m2_position       = state["module2"]["position"]
    bot_state.m2_platinum_days  = state["module2"]["platinum_days"]
    bot_state.m3_position       = state["module3"]["position"]
    bot_state.m3_palladium_days = state["module3"]["palladium_days"]
    bot_state.last_updated      = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bot_state)
    return bot_state