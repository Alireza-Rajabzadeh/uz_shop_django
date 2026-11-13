class NotificationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class NotificationInProgress(Exception):
    pass
