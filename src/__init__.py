"""Top-level package for the CLP_TCC3 application.

This file intentionally keeps the package lightweight so that imports like
``import src.manager`` work reliably across different environments (Windows,
Linux, namespace packages, etc.).
"""

__all__ = [
    "app",
    "consumers",
    "jobs",
    "models",
    "repository",
    "runtime",
    "services",
    "simulations",
    "utils",
]
