"""Explicit database initialization, import and activation; credentials stay in the environment."""
import argparse
import json
import os
import sys
from sqlalchemy.exc import SQLAlchemyError
from .connection import create_db_engine
from .schema import initialize_schema, SchemaMismatch
from .repository import SnapshotRepository, RepositoryUnavailable, ReleaseConflict, ReleaseNotFound
from ..services.ai_recommendation.snapshot_service import load_snapshot_dataset


def main(argv=None):
    parser=argparse.ArgumentParser(description="Manage immutable recommendation PostgreSQL releases")
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("init");commands.add_parser("status")
    activate=commands.add_parser("activate");activate.add_argument("release_id")
    load=commands.add_parser("import")
    load.add_argument("--modeling-dir",required=True)
    load.add_argument("--target-month",required=True)
    load.add_argument("--domains",nargs="+",required=True)
    load.add_argument("--allow-provisional",action="store_true")
    load.add_argument("--allow-context-scores",action="store_true")
    load.add_argument("--activate",action="store_true")
    args=parser.parse_args(argv)
    engine=None
    try:
        engine=create_db_engine(os.environ.get("RECOMMENDATION_DATABASE_URL", ""))
        repository=SnapshotRepository(engine)
        if args.command=="init":
            initialize_schema(engine);result={"schema":"recommendation","initialized":True}
        elif args.command=="status":result=repository.get_status()
        elif args.command=="activate":
            repository.activate_release(args.release_id);result={"active_release":args.release_id}
        else:
            data=load_snapshot_dataset(args.modeling_dir,target_month=args.target_month,domains=args.domains,
                allow_provisional=args.allow_provisional,allow_context_scores=args.allow_context_scores)
            key=repository.import_dataset(data,activate=args.activate)
            result={"release_id":key,"regions":len(data.regions),"domains":data.available_domains,"activated":args.activate}
        print(json.dumps(result,ensure_ascii=False));return 0
    except (RepositoryUnavailable,ReleaseConflict,ReleaseNotFound,SchemaMismatch,ValueError,OSError,SQLAlchemyError):
        # No raw DB exception, URL, source path or credential in console output.
        print(json.dumps({"error":"database_command_failed","command":args.command}),file=sys.stderr)
        return 1
    finally:
        if engine is not None:engine.dispose()


if __name__=="__main__":
    raise SystemExit(main())
