from .base import BaseConnector

_REGISTRY: dict[str, type[BaseConnector]] = {}


def register(cls: type[BaseConnector]) -> type[BaseConnector]:
    if not cls.key:
        raise ValueError("connector needs a key")
    _REGISTRY[cls.key] = cls
    return cls


def get_connector_class(key: str) -> type[BaseConnector]:
    # import for side-effect registration
    from . import dpsa_circular, json_feed, fixture  # noqa: F401
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(f"unknown connector '{key}'") from None
