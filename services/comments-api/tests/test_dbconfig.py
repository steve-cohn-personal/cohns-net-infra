import json
from unittest.mock import MagicMock, patch

import app.db as db
from app.config import Settings


def test_url_falls_back_to_database_url_without_secret():
    s = Settings(database_url="sqlite+aiosqlite:///./x.db", db_secret_arn=None)
    assert s.build_database_url() == "sqlite+aiosqlite:///./x.db"


def test_url_carries_no_credentials_when_a_secret_is_configured():
    """With a secret configured the URL holds dialect/host/port/database only.

    app/db.py supplies the username and password per connection, so there is
    nothing in the URL to go stale when the secret rotates — and building the URL
    touches Secrets Manager not at all.
    """
    s = Settings(
        db_secret_arn="arn:aws:secretsmanager:us-west-2:123456789012:secret:rds!cluster-abc",
        db_host="comments-dev.cluster-xyz.us-west-2.rds.amazonaws.com",
        db_port=5432,
        db_name="commentsdb",
    )

    with patch("boto3.client") as boto_client:
        url = s.build_database_url()

    boto_client.assert_not_called()
    assert url == (
        "postgresql+asyncpg://"
        "comments-dev.cluster-xyz.us-west-2.rds.amazonaws.com:5432/commentsdb"
    )


def test_credentials_read_from_secrets_manager():
    """The RDS-managed master secret is just {username, password}.

    They now reach asyncpg as connection parameters rather than embedded in a URL,
    so awkward characters need no percent-encoding and cannot be mangled by it.
    """
    s = Settings(
        db_secret_arn="arn:aws:secretsmanager:us-west-2:123456789012:secret:rds!cluster-abc",
        aws_region="us-west-2",
    )
    fake = {"username": "dbadmin", "password": "p@ss/w+rd"}
    client = MagicMock()
    client.get_secret_value.return_value = {"SecretString": json.dumps(fake)}

    with patch("boto3.client", return_value=client) as boto_client:
        credentials = s.fetch_db_credentials()

    boto_client.assert_called_once_with("secretsmanager", region_name="us-west-2")
    client.get_secret_value.assert_called_once_with(SecretId=s.db_secret_arn)
    assert credentials == ("dbadmin", "p@ss/w+rd")


async def test_credentials_are_cached_and_refetched_on_refresh():
    """The cache is what makes a rotation survivable: reused for every connection
    until one is refused, then re-read exactly once.

    Settings is a pydantic model, which refuses attribute assignment for anything
    that is not a field — so patch the method on the class, not the instance.
    """
    calls = []

    def fake_fetch(_self):
        calls.append(None)
        return ("dbadmin", f"pw{len(calls)}")

    with (
        patch.object(db, "_credentials", None),
        patch.object(Settings, "fetch_db_credentials", fake_fetch),
    ):
        assert await db._get_credentials(refresh=False) == ("dbadmin", "pw1")
        assert await db._get_credentials(refresh=False) == ("dbadmin", "pw1")
        assert len(calls) == 1

        assert await db._get_credentials(refresh=True) == ("dbadmin", "pw2")
        assert len(calls) == 2
