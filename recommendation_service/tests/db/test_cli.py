import pytest
from sqlalchemy.exc import OperationalError
from recommendation_service.database import cli


def test_init_failure_does_not_leak_sql_or_credentials(monkeypatch,capsys):
    monkeypatch.setenv("RECOMMENDATION_DATABASE_URL","postgresql+psycopg://user:DO_NOT_LEAK@localhost/db")
    def fail(engine):
        raise OperationalError("DO_NOT_LEAK SQL",{},Exception("DO_NOT_LEAK"))
    monkeypatch.setattr(cli,"initialize_schema",fail)
    assert cli.main(["init"])==1
    output=capsys.readouterr()
    assert "DO_NOT_LEAK" not in output.err+output.out
    assert "database_command_failed" in output.err
