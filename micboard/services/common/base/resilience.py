from __future__ import annotations

import httpx


def create_resilient_session(
    *,
    max_retries: int = 3,
    pool_connections: int = 10,
    pool_maxsize: int = 20,
    verify_ssl: bool = True,
    follow_redirects: bool = True,
) -> httpx.Client:
    """Create an HTTPX client with bounded connection retries and pooling.

    HTTP status retries belong in the calling service because only that layer
    knows whether a request is safe to replay and how to interpret Retry-After.
    """
    limits = httpx.Limits(
        max_connections=pool_maxsize,
        max_keepalive_connections=pool_connections,
    )
    transport = httpx.HTTPTransport(retries=max_retries)
    return httpx.Client(
        verify=verify_ssl,
        follow_redirects=follow_redirects,
        limits=limits,
        transport=transport,
    )
