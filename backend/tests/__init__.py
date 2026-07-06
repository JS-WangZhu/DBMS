from importlib.metadata import version

import werkzeug


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = version("werkzeug")
