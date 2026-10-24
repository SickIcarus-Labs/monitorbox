import os

def version():
    try:
        with open(os.path.join(os.path.dirname(__file__), "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "0.0.0-dev"
