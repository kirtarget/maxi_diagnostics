from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_http_acme_bootstrap_has_no_plaintext_application_proxy():
    config = (ROOT / "deploy/nginx/maxi.kirtarget.ru.http.conf").read_text(encoding="utf-8")

    assert "location ^~ /.well-known/acme-challenge/" in config
    assert "root /var/www/certbot;" in config
    assert "try_files $uri =404;" in config
    assert "return 301 https://maxi.kirtarget.ru$request_uri;" in config
    assert "proxy_pass" not in config
