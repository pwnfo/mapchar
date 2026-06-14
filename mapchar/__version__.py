from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mapchar")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
