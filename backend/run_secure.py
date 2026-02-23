import os
import uvicorn


def as_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    reload_enabled = as_bool("API_RELOAD", False)

    certfile = (os.getenv("TLS_CERT_FILE") or "").strip()
    keyfile = (os.getenv("TLS_KEY_FILE") or "").strip()

    kwargs = {
        "app": "backend.main:app",
        "host": host,
        "port": port,
        "reload": reload_enabled,
    }

    if certfile and keyfile:
        kwargs["ssl_certfile"] = certfile
        kwargs["ssl_keyfile"] = keyfile

    uvicorn.run(**kwargs)


if __name__ == "__main__":
    main()
