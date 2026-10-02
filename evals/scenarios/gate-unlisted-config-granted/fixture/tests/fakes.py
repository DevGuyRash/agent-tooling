class FakeTransport:
    """Answers GET requests from a dict of path -> response, and records the paths asked for."""

    def __init__(self, responses):
        self.responses = responses
        self.paths = []

    def get(self, path):
        self.paths.append(path)
        return self.responses[path]
