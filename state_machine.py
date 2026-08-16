import logging
from collections.abc import Callable
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
    def __init__(self, initial_state: State, handlers: dict[State, Callable[[], State]]) -> None:
        if not isinstance(initial_state, State):
            raise TypeError(f"initial_state must be a State, got {type(initial_state).__name__}")
        missing_states = set(State) - handlers.keys()
        if missing_states:
            missing = ", ".join(sorted(state.name for state in missing_states))
            raise ValueError(f"Missing state handlers: {missing}")
        if any(not isinstance(state, State) or not callable(handler) for state, handler in handlers.items()):
            raise TypeError("handlers must map State values to callables")
        self.current_state: State = initial_state
        self.state_handlers = dict(handlers)
        logger.info("State machine initialized in state: %s", initial_state.name)

    def transition(self, new_state: State) -> State:
        if not isinstance(new_state, State):
            raise TypeError(f"new_state must be a State, got {type(new_state).__name__}")
        if new_state != self.current_state:
            logger.debug("State transition: %s -> %s", self.current_state.name, new_state.name)
            self.current_state = new_state
        return self.current_state

    def update(self) -> State:
        current_state = self.current_state
        handler = self.state_handlers[current_state]
        next_state = handler()
        if not isinstance(next_state, State):
            raise RuntimeError(
                f"Handler for {current_state.name} returned invalid state: {next_state!r}"
            )
        return self.transition(next_state)
