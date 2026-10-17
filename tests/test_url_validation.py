"""Tests for monitor URL validation and SSRF protections."""

import socket

import pytest

from monitor.url_validation import URLValidationError, validate_monitor_url


def _address_info(address: str) -> list[tuple]:
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 80))]


def test_accepts_public_ipv4_literal() -> None:
    validate_monitor_url("https://8.8.8.8/health")


def test_rejects_non_http_scheme() -> None:
    with pytest.raises(URLValidationError, match="HTTP and HTTPS"):
        validate_monitor_url("file:///etc/passwd")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://user:password@example.com/",
    ],
)
def test_rejects_private_or_credentialed_targets(url: str) -> None:
    with pytest.raises(URLValidationError):
        validate_monitor_url(url)


def test_rejects_dns_name_if_any_answer_is_private() -> None:
    def resolve(host: str, port: int, *, type: int) -> list[tuple]:
        return _address_info("8.8.8.8") + _address_info("192.168.1.10")

    with pytest.raises(URLValidationError, match="public IP"):
        validate_monitor_url("https://mixed.example/", resolver=resolve)


def test_accepts_dns_name_when_all_answers_are_public() -> None:
    def resolve(host: str, port: int, *, type: int) -> list[tuple]:
        return _address_info("8.8.8.8") + _address_info("1.1.1.1")

    validate_monitor_url("https://public.example/", resolver=resolve)


def test_rejects_unresolvable_host() -> None:
    def resolve(host: str, port: int, *, type: int) -> list[tuple]:
        raise socket.gaierror("not found")

    with pytest.raises(URLValidationError, match="could not be resolved"):
        validate_monitor_url("https://missing.example/", resolver=resolve)
