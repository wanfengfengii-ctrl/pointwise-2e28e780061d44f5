from contextlib import closing

from tests.fixtures import ReplyDiscarded


def make_exchange(open_station_db, handler, *, drop_after_applied=False):
    """Open a station connection for each delivery and optionally lose the link."""
    disconnected = False

    def exchange(message):
        nonlocal disconnected
        if disconnected:
            raise ConnectionError("station link is unavailable")
        with closing(open_station_db()) as station_db:
            reply = handler(station_db, message)
        if drop_after_applied and reply["state"] == "applied":
            disconnected = True
            raise ReplyDiscarded("applied response was discarded")
        return reply

    return exchange
