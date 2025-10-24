#!/usr/bin/env python3
"""
Pre-commit hook for checking locks on multiple large tables in Django migrations
BLOCKS commit if locks on 2+ large tables are found
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Default configuration for pre-commit
DEFAULT_LARGE_TABLES = ["users", "orders", "payments", "audit_logs", "logs"]
DEFAULT_MIN_TABLES = 2


def parse_arguments():
    """Parse command line arguments"""
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
    parser.add_argument(
        "--app",
        "-a",
        type=str,
        help="Django app name (for determining full table names)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--min-tables",
        "-m",
        type=int,
        default=DEFAULT_MIN_TABLES,
        help=f"Minimum number of tables to BLOCK commit (default: {DEFAULT_MIN_TABLES})",
    )
    parser.add_argument("--config", "-c", type=str, help="JSON configuration file")
    parser.add_argument(
        "--strict",
        "-s",
        action="store_true",
        default=True,
        help="Strict mode - BLOCK commit when problems are detected (enabled by default)",
    )

    return parser.parse_args()


def load_config(config_path):
    """Load configuration from JSON file"""
    if config_path and Path(config_path).exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Error loading configuration {config_path}: {e}")
    return {}


def read_migration_file(file_path):
    """Read migration file"""
    try:
        with open(file_path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"❌ Error reading file {file_path}: {e}")
        return None


def is_migration_file(file_path):
    """Check if file is a Django migration"""
    path = Path(file_path)
    return (
        path.suffix == ".py"
        and "migrations" in path.parts
        and path.name != "__init__.py"
        and bool(re.match(r"^\d{4}_.*\.py$", path.name))
    )


def parse_django_migration_operations(content, tables, app_name=None, verbose=False):
    """
    Analyze Django migration operations and determine potential locks
    """
    results = {
        "locked_tables": set(),
        "operations": [],
        "multiple_locks": False,
        "critical_risk": False,
        "migration_type": "unknown",
        "locked_count": 0,
        "should_block_commit": False,  # ⚠️ New field for commit blocking
    }

    if not content:
        return results

    # Patterns for determining migration type
    if "RunPython" in content or "RunSQL" in content:
        results["migration_type"] = "data_migration"
    else:
        results["migration_type"] = "schema_migration"

    # Dictionary mapping Django operations to potential locks
    django_operations = {
        "CreateModel": "CREATE TABLE",
        "DeleteModel": "DROP TABLE",
        "RenameModel": "RENAME TABLE",
        "AlterModelTable": "ALTER TABLE",
        "AddField": "ALTER TABLE (ADD COLUMN)",
        "RemoveField": "ALTER TABLE (DROP COLUMN)",
        "AlterField": "ALTER TABLE (ALTER COLUMN)",
        "RenameField": "ALTER TABLE (RENAME COLUMN)",
        "AddIndex": "CREATE INDEX",
        "RemoveIndex": "DROP INDEX",
        "AddConstraint": "ALTER TABLE (ADD CONSTRAINT)",
        "RemoveConstraint": "ALTER TABLE (DROP CONSTRAINT)",
    }

    # Search for migration operations
    for op_name, sql_op in django_operations.items():
        # Pattern for CreateModel operations with name parameter
        if op_name == "CreateModel":
            pattern = rf"{op_name}\s*\(\s*.*?name\s*=\s*['\"](.*?)['\"]"
            matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)

            for match in matches:
                model_name = match.group(1).lower()
                table_name = convert_model_to_table(model_name, app_name)

                # Check if this table is in the list of large tables
                if table_name in [t.lower() for t in tables]:
                    results["locked_tables"].add(table_name)
                    results["operations"].append(
                        {
                            "django_operation": op_name,
                            "sql_operation": sql_op,
                            "model_name": model_name,
                            "table_name": table_name,
                            "description": f"{op_name} -> {sql_op}",
                            "risk_level": "high"
                            if sql_op in ["ALTER TABLE", "DROP TABLE", "CREATE INDEX"]
                            else "medium",
                        }
                    )

        # Pattern for operations with model_name parameter
        else:
            pattern = rf"{op_name}\s*\(\s*.*?model_name\s*=\s*['\"](.*?)['\"]"
            matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)

            for match in matches:
                model_name = match.group(1).lower()
                table_name = convert_model_to_table(model_name, app_name)

                # Check if this table is in the list of large tables
                if table_name in [t.lower() for t in tables]:
                    results["locked_tables"].add(table_name)
                    results["operations"].append(
                        {
                            "django_operation": op_name,
                            "sql_operation": sql_op,
                            "model_name": model_name,
                            "table_name": table_name,
                            "description": f"{op_name} -> {sql_op}",
                            "risk_level": "high"
                            if sql_op in ["ALTER TABLE", "DROP TABLE", "CREATE INDEX"]
                            else "medium",
                        }
                    )

    # Analyze RunSQL operations
    # Pattern 1: RunSQL with sql parameter
    sql_blocks = re.findall(r"RunSQL\s*\(.*?sql\s*=\s*(.*?)\).*?\)", content, re.DOTALL)

    # Pattern 2: RunSQL with SQL as first parameter (no sql= keyword)
    if not sql_blocks:
        sql_blocks = re.findall(r"RunSQL\s*\(\s*(.*?)\s*(?:,|)\)", content, re.DOTALL)

    for sql_block in sql_blocks:
        sql_text = extract_sql_from_runsql(sql_block)
        if sql_text:
            sql_results = analyze_raw_sql(sql_text, tables, verbose)
            results["locked_tables"].update(sql_results["locked_tables"])
            results["operations"].extend(sql_results["operations"])

    results["locked_tables"] = list(results["locked_tables"])
    results["locked_count"] = len(results["locked_tables"])
    results["multiple_locks"] = results["locked_count"] >= 2
    results["critical_risk"] = results["locked_count"] >= 3

    # ⚠️ MAIN RULE: Block commit if 2+ large tables
    results["should_block_commit"] = results["locked_count"] >= 2

    return results


def convert_model_to_table(model_name, app_name=None):
    """Convert Django model name to database table name"""
    table_name = model_name.lower()
    if app_name:
        table_name = f"{app_name}_{table_name}"
    return table_name


def extract_sql_from_runsql(sql_block):
    """Extract SQL text from RunSQL block"""
    if isinstance(sql_block, str):
        sql_block = " ".join(sql_block.split())
        if sql_block.startswith(('"', "'")):
            sql_text = sql_block[1:-1].replace('\\"', '"').replace("\\'", "'")
            return sql_text
        elif sql_block.startswith("["):
            try:
                import ast

                sql_list = ast.literal_eval(sql_block)
                if isinstance(sql_list, list) and len(sql_list) > 0:
                    return sql_list[0]
            except Exception:
                pass
    return sql_block


def analyze_raw_sql(sql_text, tables, verbose=False):
    """Analyze raw SQL for table locks"""
    results = {"locked_tables": set(), "operations": []}

    tables_lower = [table.lower() for table in tables]

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

    for pattern, operation_type, risk_level in lock_patterns:
        matches = re.finditer(pattern, sql_text, re.IGNORECASE)
        for match in matches:
            for group in match.groups():
                if group and group.lower() in tables_lower:
                    results["locked_tables"].add(group)
                    results["operations"].append(
                        {
                            "django_operation": "RunSQL",
                            "sql_operation": operation_type,
                            "table_name": group,
                            "sql_snippet": match.group(0)[:100],
                            "description": f"RunSQL -> {operation_type}",
                            "risk_level": risk_level,
                        }
                    )
                    break

    results["locked_tables"] = list(results["locked_tables"])
    return results


def check_migration_files(
    filenames, tables, app_name, min_tables, verbose, strict=True
):
    """Check list of migration files"""
    migration_files = [f for f in filenames if is_migration_file(f)]

    if not migration_files:
        if verbose:
            print("📝 No migration files found for checking")
        return True, []  # ✅ Skip if no migrations

    all_passed = True
    critical_migrations = []

    print(
        f"🔍 Pre-commit: checking {len(migration_files)} migrations for large table locks"
    )
    print(f"📊 Monitoring tables: {', '.join(tables)}")
    print(f"🚫 COMMIT BLOCKED at: {min_tables}+ locked tables")
    print("-" * 60)

    for migration_file in migration_files:
        content = read_migration_file(migration_file)
        if content is None:
            continue

        results = parse_django_migration_operations(content, tables, app_name, verbose)

        # ⚠️ MAIN CHECK: block if 2+ tables
        if results["should_block_commit"]:
            all_passed = False
            critical_migrations.append(
                {
                    "file": migration_file,
                    "locked_tables": results["locked_tables"],
                    "locked_count": results["locked_count"],
                    "operations": results["operations"],
                }
            )

            print(f"❌ {migration_file}")
            print(
                f"   🚨 BLOCKED {results['locked_count']} LARGE TABLES: {', '.join(results['locked_tables'])}"
            )

            if verbose and results["operations"]:
                print("   📋 Dangerous operations:")
                for op in results["operations"]:
                    if op["table_name"] in results["locked_tables"]:
                        print(f"     • {op['description']} -> {op['table_name']}")
        else:
            status = "✅ OK" if results["locked_count"] == 0 else "⚠️  Warning (1 table)"
            print(
                f"{status} {migration_file} - locked tables: {results['locked_count']}"
            )

    # Output results
    print("-" * 60)
    if critical_migrations:
        print("🚫 COMMIT BLOCKED!")
        print(f"🚨 Critical migrations found ({len(critical_migrations)}):")

        for mig in critical_migrations:
            print(f"\n   📁 {mig['file']}")
            print(f"   📊 Locked tables: {mig['locked_count']}")
            print(f"   🗂️  Tables: {', '.join(mig['locked_tables'])}")

            if verbose:
                print("   ⚠️  Dangerous operations:")
                for op in mig["operations"]:
                    if op["table_name"] in mig["locked_tables"]:
                        print(f"     • {op['description']}")

        print("\n💡 HOW TO FIX:")
        print("   1. Split migration into multiple parts")
        print("   2. Use `Atomic = False` in migration class")
        print("   3. Execute operations sequentially in different migrations")
        print("   4. For urgent fixes use: git commit --no-verify")
        print("\n🔒 Commit BLOCKED due to DB lock risk!")

    else:
        print("✅ All migrations passed check! Commit allowed.")

    return all_passed, critical_migrations


def main():
    """Main function"""
    args = parse_arguments()

    # Load configuration
    config = load_config(args.config) if args.config else {}

    # Merge configurations (arguments have priority)
    tables = args.tables
    app_name = args.app or config.get("app")
    min_tables = args.min_tables
    verbose = args.verbose
    strict = args.strict

    if not args.filenames:
        if verbose:
            print("📝 No files provided for checking")
        return 0

    # Check migrations
    success, critical_migrations = check_migration_files(
        args.filenames, tables, app_name, min_tables, verbose, strict
    )

    # ⚠️ RETURN ERROR IF CRITICAL MIGRATIONS FOUND
    if critical_migrations:
        print(
            f"\n❌ Pre-commit hook FAILED: locks found in {len(critical_migrations)} migrations"
        )
        return 1  # ⚠️ BLOCK COMMIT

    return 0  # ✅ ALLOW COMMIT


if __name__ == "__main__":
    sys.exit(main())
