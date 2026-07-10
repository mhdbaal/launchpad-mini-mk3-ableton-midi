from __future__ import absolute_import, print_function, unicode_literals


class EventBus(object):
    """Minimal synchronous pubsub.

    Components emit semantic events via `emit(name, **payload)`. Subscribers
    are callables `(name, payload_dict) -> None`. A buggy subscriber must
    never break the rest — exceptions are swallowed and logged.

    Passing `event_bus=None` to components disables emission entirely; the
    helper `_emit` on each component is a no-op in that case, so the script
    runs identically with or without the bus.
    """

    def __init__(self, logger=None):
        self._subscribers = []
        self._logger = logger

    def subscribe(self, callback):
        """Register a subscriber. Returns a no-arg callable that unsubscribes."""
        self._subscribers.append(callback)

        def unsubscribe():
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def emit(self, event_name, **payload):
        for cb in self._subscribers:
            try:
                cb(event_name, payload)
            except Exception as exc:
                if self._logger is not None:
                    try:
                        self._logger("[EventBus] subscriber raised on {}: {}".format(
                            event_name, exc))
                    except Exception:
                        pass
