import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)


class State(Enum):
    FIND_RED_ICONS = auto()
    CLICK_RED_ICON = auto()
    CHECK_UNLOCK = auto()
    SEARCH_UPGRADE_STATION = auto()
    HOLD_UPGRADE_STATION = auto()
    OPEN_BOXES = auto()
    UPGRADE_STATS = auto()
    SCROLL = auto()
    CHECK_NEW_LEVEL = auto()
    TRANSITION_LEVEL = auto()
    WAIT_FOR_UNLOCK = auto()


class StateMachine:
    def __init__(self, initial_state=State.FIND_RED_ICONS):
        self.current_state = initial_state
        self.previous_state = None
        self.state_handlers = {}
        logger.info("State machine initialized in state: %s", initial_state.name)

    def register_handler(self, state, handler):
        self.state_handlers[state] = handler

    def transition(self, new_state):
        if new_state != self.current_state:
            logger.info(
                "State transition: %s -> %s",
                self.current_state.name,
                new_state.name,
            )
            self.previous_state = self.current_state
            self.current_state = new_state

    def update(self):
        handler = self.state_handlers.get(self.current_state)
        if handler is None:
            logger.warning("No handler registered for state: %s", self.current_state.name)
            return False

        next_state = handler(self.current_state)
        if isinstance(next_state, State):
            self.transition(next_state)
        return True

    def get_state(self):
        return self.current_state

    def get_state_name(self):
        return self.current_state.name
