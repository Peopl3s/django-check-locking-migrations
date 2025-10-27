#!/usr/bin/env python3
"""
Pre-commit hook for checking locks on multiple large tables in Django migrations.
BLOCKS commit if locks on 2+ large tables are found.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Dict,
    Final,
    FrozenSet,
    List,
    Optional,
    Set,
    Tuple,
    cast,
    final,
)

# Default configuration
DEFAULT_LARGE_TABLES: Final[list[str]] = ["users", "orders", "payments", "audit_logs", "logs"]
DEFAULT_MIN_TABLES: Final[int] = 2

# Regex patterns as constants
CREATE_MODEL_PATTERN: re.Pattern[str] = re.compile(
    r"CreateModel\s*\(\s*.*?name\s*=\s*['\"](.*?)['\"]", re.DOTALL | re.IGNORECASE
)
MODEL_OP_PATTERN: re.Pattern[str] = re.compile(
    r"(\w+)\s*\(\s*.*?model_name\s*=\s*['\"](.*?)['\"]", re.DOTALL | re.IGNORECASE
)
RUNSQL_PATTERN: re.Pattern[str] = re.compile(r"RunSQL\s*\((.*?)\)", re.DOTALL)

# Mapping of Django ops to SQL equivalents and risk
DJANGO_OP_INFO = {
    "CreateModel": ("CREATE TABLE", "high"),
    "DeleteModel": ("DROP TABLE", "high"),
    "RenameModel": ("RENAME TABLE", "high"),
    "AlterModelTable": ("ALTER TABLE", "high"),
    "AddField": ("ALTER TABLE (ADD COLUMN)", "high"),
    "RemoveField": ("ALTER TABLE (DROP COLUMN)", "high"),
    "AlterField": ("ALTER TABLE (ALTER COLUMN)", "high"),
    "RenameField": ("ALTER TABLE (RENAME COLUMN)", "high"),
    "AddIndex": ("CREATE INDEX", "high"),
    "RemoveIndex": ("DROP INDEX", "high"),
    "AddConstraint": ("ALTER TABLE (ADD CONSTRAINT)", "medium"),
    "RemoveConstraint": ("ALTER TABLE (DROP CONSTRAINT)", "medium"),
}


@final
@dataclass(frozen=True, slots=True, kw_only=True) # type: ignore[call-overload]
class MigrationOperation:
    django_operation: str
    sql_operation: str
    table_name: str
    description: str
    risk_level: str
    model_name: Optional[str] = None
    sql_snippet: Optional[str] = None


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-commit hook: BLOCKS commit on locks of 2+ large tables in Django migrations"
    )
    parser.add_argument("filenames", nargs="*", help="Migration files to check")
    parser.add_argument(
        "--tables",
        "-t",
        nargs="+",
        default=DEFAULT_LARGE_TABLES,
        help=f"List of LARGE tables to check (default: {DEFAULT_LARGE_TABLES})",
    )
    parser.add_argument("--app", "-a", type=str, help="Django app name")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--min-tables",
        "-m",
        type=int,
        default=DEFAULT_MIN_TABLES,
        help=f"Minimum number of tables to BLOCK commit (default: {DEFAULT_MIN_TABLES})",
    )
    parser.add_argument("--config", "-c", type=str, help="JSON configuration file")
    return parser.parse_args()


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    if not config_path:
        return {}
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"⚠️  Config file not found: {config_path}")
        return {}
    try:
        return cast(Dict[str, Any], json.loads(config_file.read_text(encoding="utf-8")))
    except Exception as e:
        print(f"⚠️  Error loading config {config_path}: {e}")
        return {}


def is_migration_file(file_path: str) -> bool:
    path = Path(file_path)
    return (
        path.suffix == ".py"
        and "migrations" in path.parts
        and path.name != "__init__.py"
        and bool(re.match(r"^\d{4}_.*\.py$", path.name))
    )


def read_file(file_path: str) -> Optional[str]:
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        print(f"❌ Error reading {file_path}: {e}")
        return None


def convert_model_to_table(model_name: str, app_name: Optional[str]) -> str:
    table = model_name.lower()
    if app_name:
        table = f"{app_name}_{table}"
    return table


def extract_sql_from_runsql(arg: str) -> List[str]:
    """Extract forward SQL statements from RunSQL argument (supports str, list, tuple)."""
    arg = arg.strip()
    if not arg:
        return []

    # Handle triple-quoted strings
    if (arg.startswith('"""') and arg.endswith('"""')) or (
        arg.startswith("'''") and arg.endswith("'''")
    ):
        return [arg[3:-3].strip()]
    if (arg.startswith('"') and arg.endswith('"')) or (
        arg.startswith("'") and arg.endswith("'")
    ):
        return [arg[1:-1].replace('\\"', '"').replace("\\'", "'").strip()]

    # Handle list/tuple
    if arg.startswith(("[", "(")) and arg.endswith(("]", ")")):
        try:
            import ast

            parsed = ast.literal_eval(arg)
            if isinstance(parsed, (list, tuple)):
                return [str(item).strip() for item in parsed if isinstance(item, str)]
        except Exception:
            pass

    # Fallback: treat as single SQL
    return [arg]


def analyze_runsql_operations(
    runsql_args: str,
    large_tables_set: FrozenSet[str],
    app_name: Optional[str],
    verbose: bool = False,
) -> Tuple[Set[str], List[MigrationOperation]]:
    locked_tables: Set[str] = set()
    operations: List[MigrationOperation] = []

    sql_statements = extract_sql_from_runsql(runsql_args)

    for sql in sql_statements:
        if not sql:
            continue
        sql_results = analyze_raw_sql(sql, large_tables_set, verbose)
        locked_tables.update(sql_results["locked_tables"])
        operations.extend(sql_results["operations"])

    return locked_tables, operations


def analyze_raw_sql(
    sql_text: str, large_tables_set: FrozenSet[str], verbose: bool = False
) -> Dict[str, Any]:
    results: Dict[str, Any] = {"locked_tables": set(), "operations": []}

    lock_patterns = [
        (
            r'ALTER\s+TABLE\s+[`"]?([\w_]+)[`"]?\s+RENAME\s+COLUMN',
            "RENAME COLUMN",
            "high",
        ),
        (r'ALTER\s+TABLE\s+[`"]?([\w_]+)[`"]?\s+', "ALTER TABLE", "high"),
        (
            r'CREATE\s+(UNIQUE\s+)?INDEX\s+.*?\s+ON\s+[`"]?([\w_]+)[`"]?',
            "CREATE INDEX",
            "high",
        ),
        (r'DROP\s+INDEX\s+.*?\s+ON\s+[`"]?([\w_]+)[`"]?', "DROP INDEX", "high"),
        (r'TRUNCATE\s+TABLE\s+[`"]?([\w_]+)[`"]?', "TRUNCATE TABLE", "high"),
        (r'DROP\s+TABLE\s+[`"]?([\w_]+)[`"]?', "DROP TABLE", "high"),
        (r'UPDATE\s+[`"]?([\w_]+)[`"]?\s+SET\s+[^;]*', "UPDATE without WHERE", "high"),
        (r'DELETE\s+FROM\s+[`"]?([\w_]+)[`"]?[^;]*', "DELETE without WHERE", "high"),
    ]

    for pattern, op_type, risk in lock_patterns:
        for match in re.finditer(pattern, sql_text, re.IGNORECASE):
            table = None
            # Extract table name from first or second group
            for group in match.groups():
                if group and group.lower() in large_tables_set:
                    table = group.lower()
                    break
            if table:
                results["locked_tables"].add(table)
                snippet = match.group(0).replace("\n", " ")[:100]
                results["operations"].append(
                    MigrationOperation(
                        django_operation="RunSQL",
                        sql_operation=op_type,
                        table_name=table,
                        description=f"RunSQL -> {op_type}",
                        risk_level=risk,
                        sql_snippet=snippet,
                    )
                )
    return results


def parse_django_migration_operations(
    content: str,
    large_tables_set: FrozenSet[str],
    app_name: Optional[str],
    verbose: bool = False,
) -> Dict[str, Any]:
    locked_tables: Set[str] = set()
    operations: List[MigrationOperation] = []

    # Detect migration type
    migration_type = (
        "data_migration"
        if ("RunPython" in content or "RunSQL" in content)
        else "schema_migration"
    )

    # Handle standard Django operations
    for op_name, (sql_op, risk) in DJANGO_OP_INFO.items():
        if op_name == "CreateModel":
            for match in CREATE_MODEL_PATTERN.finditer(content):
                model_name = match.group(1).lower()
                table_name = convert_model_to_table(model_name, app_name)
                if table_name in large_tables_set:
                    locked_tables.add(table_name)
                    operations.append(
                        MigrationOperation(
                            django_operation=op_name,
                            sql_operation=sql_op,
                            table_name=table_name,
                            model_name=model_name,
                            description=f"{op_name} -> {sql_op}",
                            risk_level=risk,
                        )
                    )
        else:
            pattern = rf"{op_name}\s*\(\s*.*?model_name\s*=\s*['\"](.*?)['\"]"
            for match in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
                model_name = match.group(1).lower()
                table_name = convert_model_to_table(model_name, app_name)
                if table_name in large_tables_set:
                    locked_tables.add(table_name)
                    operations.append(
                        MigrationOperation(
                            django_operation=op_name,
                            sql_operation=sql_op,
                            table_name=table_name,
                            model_name=model_name,
                            description=f"{op_name} -> {sql_op}",
                            risk_level=risk,
                        )
                    )

    # Handle RunSQL
    for match in RUNSQL_PATTERN.finditer(content):
        runsql_args = match.group(1)
        sql_locked, sql_ops = analyze_runsql_operations(
            runsql_args, large_tables_set, app_name, verbose
        )
        locked_tables.update(sql_locked)
        operations.extend(sql_ops)

    locked_count = len(locked_tables)
    should_block = locked_count >= 2

    return {
        "migration_type": migration_type,
        "locked_tables": sorted(locked_tables),
        "locked_count": locked_count,
        "operations": operations,
        "should_block_commit": should_block,
    }


def check_migration_files(
    filenames: List[str],
    large_tables: List[str],
    app_name: Optional[str],
    min_tables: int,
    verbose: bool,
) -> Tuple[bool, List[Dict[str, Any]]]:
    migration_files = [f for f in filenames if is_migration_file(f)]
    if not migration_files:
        if verbose:
            print("📝 No migration files to check")
        return True, []

    large_tables_set = frozenset(t.lower() for t in large_tables)

    print(f"🔍 Checking {len(migration_files)} migrations for locks on large tables")
    print(f"📊 Monitoring tables: {', '.join(large_tables)}")
    print(f"🚫 COMMIT BLOCKED at ≥{min_tables} locked tables")
    print("-" * 60)

    all_passed = True
    critical_migrations = []

    for file_path in migration_files:
        content = read_file(file_path)
        if content is None:
            continue

        results = parse_django_migration_operations(
            content, large_tables_set, app_name, verbose
        )
        if results["should_block_commit"]:
            all_passed = False
            critical_migrations.append(
                {
                    "file": file_path,
                    "locked_tables": results["locked_tables"],
                    "locked_count": results["locked_count"],
                    "operations": results["operations"],
                }
            )

            print(f"❌ {file_path}")
            print(
                f"   🚨 BLOCKED {results['locked_count']} LARGE TABLES: {', '.join(results['locked_tables'])}"
            )
            if verbose:
                print("   📋 Dangerous operations:")
                for op in results["operations"]:
                    if op.table_name in results["locked_tables"]:
                        print(f"     • {op.description} → {op.table_name}")
        else:
            status = "✅ OK" if results["locked_count"] == 0 else "⚠️  Warning (1 table)"
            print(f"{status} {file_path} - locked tables: {results['locked_count']}")

    print("-" * 60)
    if critical_migrations:
        print("🚫 COMMIT BLOCKED!")
        print(f"🚨 Found {len(critical_migrations)} critical migration(s):")
        for mig in critical_migrations:
            print(f"\n   📁 {mig['file']}")
            print(f"   📊 Locked tables: {mig['locked_count']}")
            print(f"   🗂️  Tables: {', '.join(mig['locked_tables'])}")
            if verbose:
                print("   ⚠️  Operations:")
                for op in mig["operations"]:
                    if op.table_name in mig["locked_tables"]:
                        desc = f"{op.description} ({op.risk_level})"
                        if op.sql_snippet:
                            desc += f" — {op.sql_snippet}"
                        print(f"     • {desc}")
        print("\n💡 HOW TO FIX:")
        print("   1. Split migration into multiple parts")
        print("   2. Use `atomic = False` in migration class")
        print("   3. Execute operations in separate migrations")
        print("   4. Bypass with: git commit --no-verify")
        print("\n🔒 Commit BLOCKED due to DB lock risk!")
    else:
        print("✅ All migrations passed! Commit allowed.")

    return all_passed, critical_migrations


def main() -> int:
    args = parse_arguments()
    config = load_config(args.config)

    # Merge config: CLI args override config file
    tables = args.tables
    app_name = args.app or config.get("app")
    min_tables = args.min_tables
    verbose = args.verbose

    if not args.filenames:
        if verbose:
            print("📝 No files provided")
        return 0

    success, critical = check_migration_files(
        filenames=args.filenames,
        large_tables=tables,
        app_name=app_name,
        min_tables=min_tables,
        verbose=verbose,
    )

    if critical:
        print(f"\n❌ Pre-commit hook FAILED: {len(critical)} migration(s) blocked")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
