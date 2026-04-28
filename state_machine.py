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
        if not isinstance(initial_state, State):
            raise TypeError(f"initial_state must be a State, got {type(initial_state).__name__}")
        self.current_state = initial_state
        self.previous_state = None
        self.state_handlers = {}
        logger.info("State machine initialized in state: %s", initial_state.name)
    
    def register_handler(self, state, handler):
        if not isinstance(state, State):
            raise TypeError(f"state must be a State, got {type(state).__name__}")
        if not callable(handler):
            raise TypeError(f"handler for {state.name} must be callable")
        self.state_handlers[state] = handler
        logger.debug("Registered handler for state: %s", state.name)
    
    def transition(self, new_state):
        if not isinstance(new_state, State):
            logger.error("Invalid transition target: %r", new_state)
            return False
        if new_state != self.current_state:
            logger.debug("State transition: %s -> %s", self.current_state.name, new_state.name)
            self.previous_state = self.current_state
            self.current_state = new_state
        return True
    
    def update(self):
        if self.current_state in self.state_handlers:
            handler = self.state_handlers[self.current_state]
            next_state = handler(self.current_state)
            
            if next_state is not None:
                if isinstance(next_state, State):
                    if not self.transition(next_state):
                        return False
                else:
                    logger.error(
                        "Handler for %s returned invalid state: %r",
                        self.current_state.name,
                        next_state,
                    )
                    return False
            
            return True
        else:
            logger.warning("No handler registered for state: %s", self.current_state.name)
            return False
    
    def get_state(self):
        return self.current_state
    
    def get_state_name(self):
        return self.current_state.name
