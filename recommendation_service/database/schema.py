"""Version-one PostgreSQL schema. Initialization is explicit and non-destructive."""
from sqlalchemy import (MetaData, Table, Column, String, Integer, Boolean, DateTime,
    Double, ForeignKeyConstraint, CheckConstraint, UniqueConstraint, Index, inspect,
    text, false, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.schema import CreateSchema

SCHEMA = "recommendation"
metadata = MetaData(schema=SCHEMA)
DOMAINS_SQL = "'economy','energy','comfort','health','safety'"


class SchemaMismatch(ValueError):
    pass


releases = Table("releases", metadata,
    Column("release_id", String(64), primary_key=True),
    Column("target_month", String(7), nullable=False),
    Column("state", String(8), nullable=False),
    Column("is_active", Boolean, nullable=False, server_default=false()),
    Column("payload_hash", String(64), nullable=False),
    Column("dataset_metadata", JSONB, nullable=False),
    Column("declared_regions", Integer, nullable=False),
    Column("schema_version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("release_id ~ '^snapshot-[a-f0-9]{16}$'", name="release_id_format"),
    CheckConstraint("target_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'", name="release_month_format"),
    CheckConstraint("payload_hash ~ '^[a-f0-9]{64}$'", name="release_hash_format"),
    CheckConstraint("state IN ('draft','ready')", name="release_state"),
    CheckConstraint("NOT is_active OR state = 'ready'", name="active_release_ready"),
    CheckConstraint("declared_regions > 0", name="release_region_count"),
    CheckConstraint("schema_version = 1", name="schema_version_one"))
Index("one_active_release", releases.c.is_active, unique=True,
      postgresql_where=releases.c.is_active.is_(True))

regions = Table("regions", metadata,
    Column("release_id", String(64), nullable=False, primary_key=True),
    Column("region_code", String(6), nullable=False, primary_key=True),
    Column("region_name", String(100), nullable=False),
    Column("sigungu_code", String(5), nullable=False),
    ForeignKeyConstraint(["release_id"], ["recommendation.releases.release_id"], ondelete="RESTRICT", name="region_release_fk"),
    UniqueConstraint("release_id", "region_code", "sigungu_code", name="region_district_identity"),
    CheckConstraint("region_code ~ '^[0-9]{6}$'", name="region_code_format"),
    CheckConstraint("sigungu_code ~ '^[0-9]{5}$'", name="region_sigungu_format"),
    CheckConstraint("length(trim(region_name)) > 0", name="region_name_present"))
Index("regions_district", regions.c.release_id, regions.c.sigungu_code)

observations = Table("observations", metadata,
    Column("release_id", String(64), primary_key=True),
    Column("domain", String(16), primary_key=True),
    Column("score_level", String(8), primary_key=True),
    Column("score_code", String(6), primary_key=True),
    Column("score", Double),
    Column("evidence", JSONB, nullable=False),
    ForeignKeyConstraint(["release_id"], ["recommendation.releases.release_id"], ondelete="RESTRICT", name="observation_release_fk"),
    CheckConstraint(f"domain IN ({DOMAINS_SQL})", name="observation_domain"),
    CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="observation_score_range"),
    CheckConstraint("(score_level='dong' AND score_code ~ '^[0-9]{6}$') OR (score_level='sigungu' AND score_code ~ '^[0-9]{5}$')", name="observation_identity"))

assignments = Table("assignments", metadata,
    Column("release_id", String(64), primary_key=True),
    Column("region_code", String(6), primary_key=True),
    Column("domain", String(16), primary_key=True),
    Column("sigungu_code", String(5), nullable=False),
    Column("score_level", String(8), nullable=False),
    Column("score_code", String(6), nullable=False),
    ForeignKeyConstraint(["release_id","region_code","sigungu_code"],
        ["recommendation.regions.release_id","recommendation.regions.region_code","recommendation.regions.sigungu_code"],
        ondelete="RESTRICT", name="assignment_region_fk"),
    ForeignKeyConstraint(["release_id","domain","score_level","score_code"],
        ["recommendation.observations.release_id","recommendation.observations.domain","recommendation.observations.score_level","recommendation.observations.score_code"],
        ondelete="RESTRICT", name="assignment_observation_fk"),
    CheckConstraint("(score_level='dong' AND score_code=region_code) OR (score_level='sigungu' AND score_code=sigungu_code)", name="assignment_scope_identity"))


def _initialize(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        raise ValueError("PostgreSQL is required")
    connection.execute(CreateSchema(SCHEMA, if_not_exists=True))
    metadata.create_all(connection)
    inspector = inspect(connection)
    for table in metadata.sorted_tables:
        actual = {c["name"]: c for c in inspector.get_columns(table.name, schema=SCHEMA)}
        expected = {c.name: c for c in table.columns}
        if set(actual) != set(expected):
            raise SchemaMismatch("Existing recommendation schema columns differ; explicit migration required")
        for name, col in expected.items():
            if (str(actual[name]["type"].compile(dialect=connection.dialect)) != str(col.type.compile(dialect=connection.dialect))
                    or actual[name]["nullable"] != col.nullable):
                raise SchemaMismatch("Existing recommendation column types differ; explicit migration required")
        expected_pk = [c.name for c in table.primary_key.columns]
        if inspector.get_pk_constraint(table.name, schema=SCHEMA)["constrained_columns"] != expected_pk:
            raise SchemaMismatch("Existing recommendation primary key differs")
        checks = {c["name"] for c in inspector.get_check_constraints(table.name, schema=SCHEMA)}
        expected_checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
        if not expected_checks <= checks:
            raise SchemaMismatch("Existing recommendation checks differ")
        foreign_keys = {c["name"] for c in inspector.get_foreign_keys(table.name, schema=SCHEMA)}
        if not {c.name for c in table.foreign_key_constraints} <= foreign_keys:
            raise SchemaMismatch("Existing recommendation foreign keys differ")
    indexes = {i["name"]: i for i in inspector.get_indexes("releases", schema=SCHEMA)}
    if not indexes.get("one_active_release", {}).get("unique"):
        raise SchemaMismatch("Active release uniqueness constraint is missing")


def initialize_schema(engine: Engine | Connection) -> None:
    if isinstance(engine, Connection):
        _initialize(engine)
    else:
        with engine.begin() as connection:
            _initialize(connection)
