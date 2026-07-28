import json
from unittest.mock import MagicMock, patch

from app.config import Settings


def test_url_falls_back_to_database_url_without_secret():
    s = Settings(database_url="sqlite+aiosqlite:///./x.db", db_secret_arn=None)
    assert s.build_database_url() == "sqlite+aiosqlite:///./x.db"


def test_url_built_from_secret_manager():
    s = Settings(
        db_secret_arn="arn:aws:secretsmanager:us-west-2:123456789012:secret:rds!cluster-abc",
        db_host="comments-dev.cluster-xyz.us-west-2.rds.amazonaws.com",
        db_port=5432,
        db_name="commentsdb",
    )
    # The RDS-managed master secret is just {username, password}. Include awkward
    # characters to prove they're URL-encoded, not passed raw.
    fake = {"username": "dbadmin", "password": "p@ss/w+rd"}
    client = MagicMock()
    client.get_secret_value.return_value = {"SecretString": json.dumps(fake)}

    with patch("boto3.client", return_value=client) as boto_client:
        url = s.build_database_url()

    boto_client.assert_called_once_with("secretsmanager", region_name="us-west-2")
    client.get_secret_value.assert_called_once_with(SecretId=s.db_secret_arn)
    assert url == (
        "postgresql+asyncpg://dbadmin:p%40ss%2Fw%2Brd@"
        "comments-dev.cluster-xyz.us-west-2.rds.amazonaws.com:5432/commentsdb"
    )
