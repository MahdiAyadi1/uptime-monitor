"""URL validation for monitor targets, including a public-address SSRF guard."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

AddressInfo = list[tuple]
Resolver = Callable[..., AddressInfo]


class URLValidationError(ValueError):
    """Raised when a monitor URL is malformed or points to a non-public address."""


def validate_monitor_url(url: str, *, resolver: Resolver = socket.getaddrinfo) -> None:
    """Validate URL syntax and ensure every resolved address is globally routable.

    DNS is checked at registration and again immediately before each probe. This does
    not eliminate DNS rebinding between validation and connection; a pinned-IP
    transport is a later hardening step.
    """
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        # Accessing .port also validates malformed and out-of-range port values.
        _ = parsed.port
    except ValueError as exc:
        raise URLValidationError("URL is malformed") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise URLValidationError("Only HTTP and HTTPS URLs are allowed")
    if not hostname:
        raise URLValidationError("URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise URLValidationError("URLs containing credentials are not allowed")
    if any(character.isspace() for character in url):
        raise URLValidationError("Whitespace is not allowed in URLs")

    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved_addresses = {
                ipaddress.ip_address(address_info[4][0])
                for address_info in resolver(hostname, parsed.port or 0, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError, IndexError, TypeError) as exc:
            raise URLValidationError("Hostname could not be resolved") from exc
        addresses = resolved_addresses
    else:
        addresses = {literal_address}

    if not addresses:
        raise URLValidationError("Hostname resolved to no IP addresses")
    if any(not address.is_global for address in addresses):
        raise URLValidationError("URL must resolve only to public IP addresses")
