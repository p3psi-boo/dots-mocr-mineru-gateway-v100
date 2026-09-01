from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "dotocrm_api.app:app",
        host=os.getenv("DOTOCRM_API_HOST", "::"),
        port=int(os.getenv("DOTOCRM_API_PORT", "8010")),
        workers=int(os.getenv("DOTOCRM_API_WORKERS", "1")),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("DOTOCRM_FORWARDED_ALLOW_IPS", "::1"),
    )


if __name__ == "__main__":
    main()
