import enum


class StateMachine(dict):
    """
    Minimal state machine as a dictionary mapping state to a handler.
    Handler should be callable that takes state and returns another state:
        self.state = handler(self.state)
    Initialize the StateMachine like a dictionary (pass a dictionary as second
    argument, or use kwargs as in dict(a=..., b=...)).
    """
    def __init__(self, initial, *args, **kwargs):
        if not isinstance(initial, enum.Enum):
            raise ValueError('Use subclasses of Enum for states')
        self._states_type = type(initial)
        self.state = initial
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        if not isinstance(key, self._states_type):
            raise KeyError('Key should be a subclass of %s: %s'
                           % (self._states_type, key))
        super().__setitem__(key, value)

    def next(self):
        self.state = self[self.state](self.state)
        return self.state
