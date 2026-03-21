import socket
import threading


_WARNED_KEYS: set[str] = set()
_WARN_LOCK = threading.Lock()


def warn_once(key: str, message: str) -> None:
    with _WARN_LOCK:
        if key in _WARNED_KEYS:
            return
        _WARNED_KEYS.add(key)
    print(message)


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    chain: list[BaseException] = []

    while stack:
        current = stack.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        chain.append(current)

        for attr in ("__cause__", "__context__", "reason"):
            nested = getattr(current, attr, None)
            if isinstance(nested, BaseException):
                stack.append(nested)

    return chain


def is_name_resolution_error(exc: BaseException) -> bool:
    for current in _iter_exception_chain(exc):
        if isinstance(current, socket.gaierror):
            return True

        text = str(current).lower()
        if any(
            token in text
            for token in (
                "failed to resolve",
                "name resolution",
                "nameresolutionerror",
                "getaddrinfo failed",
            )
        ):
            return True
    return False


def summarize_request_exception(source: str, exc: BaseException) -> str:
    if is_name_resolution_error(exc):
        return f"[{source}] DNS resolution failed; skipping this source for the current run."
    return f"[{source}] request failed: {exc}"
