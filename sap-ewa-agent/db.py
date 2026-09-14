# Database layer intentionally left minimal
# for the first collector test.

class Database:
    def __init__(self, *args, **kwargs):
        pass

    def enabled(self):
        return False
