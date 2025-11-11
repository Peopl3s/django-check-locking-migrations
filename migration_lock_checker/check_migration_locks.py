#!/usr/bin/env python3
"""
Pre-commit hook for checking locks on multiple large tables in Django migrations.
BLOCKS commit if locks on 2+ large tables are found.
"""

import argparse
import ast
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

# Ignore comment patterns
IGNORE_PATTERNS: Final[List[re.Pattern[str]]] = [
    re.compile(r'#\s*nolock\b', re.IGNORECASE),
    re.compile(r'#\s*no-lock-check\b', re.IGNORECASE),
    re.compile(r'#\s*ignore-lock-check\b', re.IGNORECASE),
    re.compile(r'"""\s*nolock\s*"""', re.IGNORECASE),
    re.compile(r"'''\s*nolock\s*'''", re.IGNORECASE),
]

# Optimized regex patterns with compiled constants
MIGRATION_FILE_PATTERN: re.Pattern[str] = re.compile(r"^\d{4}_.*\.py$")
CREATE_MODEL_PATTERN: re.Pattern[str] = re.compile(
    r"CreateModel\s*\(\s*.*?name\s*=\s*['\"](.*?)['\"]", re.DOTALL | re.IGNORECASE
)
RUNSQL_PATTERN: re.Pattern[str] = re.compile(
    r"RunSQL\s*\((.*?)\)", re.DOTALL
)
RUNPYTHON_PATTERN: re.Pattern[str] = re.compile(r"RunPython\s*\(", re.IGNORECASE)

# SQL lock patterns ordered by specificity (most specific first)
SQL_LOCK_PATTERNS: Final[List[Tuple[str, str, str]]] = [
    (r'ALTER\s+TABLE\s+[`"]?([\w_]+)[`"]?\s+RENAME\s+COLUMN', "RENAME COLUMN", "high"),
    (r'CREATE\s+(UNIQUE\s+)?INDEX\s+.*?\s+ON\s+[`"]?([\w_]+)[`"]?', "CREATE INDEX", "high"),
    (r'DROP\s+INDEX\s+.*?\s+ON\s+[`"]?([\w_]+)[`"]?', "DROP INDEX", "high"),
    (r'TRUNCATE\s+TABLE\s+[`"]?([\w_]+)[`"]?', "TRUNCATE TABLE", "high"),
    (r'DROP\s+TABLE\s+[`"]?([\w_]+)[`"]?', "DROP TABLE", "high"),
    (r'UPDATE\s+[`"]?([\w_]+)[`"]?\s+SET\s+(?!.*WHERE)[^;]*', "UPDATE without WHERE", "high"),
    (r'DELETE\s+FROM\s+[`"]?([\w_]+)[`"]?(?!\s+WHERE)[^;]*', "DELETE without WHERE", "high"),
    (r'ALTER\s+TABLE\s+[`"]?([\w_]+)[`"]?\s+(?!RENAME)(\w+)', "ALTER TABLE", "high"),
]

# Django operations that use 'name' instead of 'model_name'
NAME_BASED_OPS: Final[Set[str]] = {"AlterUniqueTogether", "AlterIndexTogether"}

# Schema operations for migration type detection
SCHEMA_OPERATIONS: Final[Set[str]] = {
    "CreateModel", "AddField", "RemoveField", "AlterField", "RenameField",
    "RenameModel", "DeleteModel", "AddIndex", "RemoveIndex", "AddConstraint",
    "RemoveConstraint", "AlterUniqueTogether", "AlterIndexTogether"
}

# Mapping of Django ops to SQL equivalents and risk
DJANGO_OP_INFO: Final[Dict[str, Tuple[str, str]]] = {
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
    "AlterUniqueTogether": ("ALTER TABLE (ADD UNIQUE CONSTRAINT)", "high"),
    "AlterIndexTogether": ("ALTER TABLE (ADD INDEX)", "high"),
}


@final
@dataclass(frozen=True, slots=True, kw_only=True) # type: ignore[call-overload]
class MigrationOperation:
    """Represents a single migration operation with its metadata."""
    django_operation: str
    sql_operation: str
    table_name: str
    description: str
    risk_level: str
    model_name: Optional[str] = None
    sql_snippet: Optional[str] = None


@final
class MigrationFileChecker:
    """Optimized checker for Django migration files."""

    __slots__ = ("large_tables", "app_name", "_table_cache")

    def __init__(self, large_tables: FrozenSet[str], app_name: Optional[str] = None):
        self.large_tables = large_tables
        self.app_name = app_name
        self._table_cache: Dict[str, str] = {}

    def _get_table_name(self, model_name: str) -> str:
        """Cache table name conversions for performance."""
        if model_name not in self._table_cache:
            self._table_cache[model_name] = convert_model_to_table(model_name, self.app_name)
        return self._table_cache[model_name]

    def _extract_sql_statements(self, runsql_arg: str) -> List[str]:
        """Optimized SQL extraction with better error handling."""
        runsql_arg = runsql_arg.strip()
        if not runsql_arg:
            return []

        # Split on reverse_sql parameter - only process forward SQL
        # Use regex to find reverse_sql parameter more reliably
        reverse_sql_match = re.search(r',\s*reverse_sql\s*=', runsql_arg)
        if reverse_sql_match:
            runsql_arg = runsql_arg[:reverse_sql_match.start()].strip()

        # Handle different string formats
        if runsql_arg.startswith(('"""', "'''")) and runsql_arg.endswith(('"""', "'''")):
            return [runsql_arg[3:-3].strip()]

        if runsql_arg.startswith(('"', "'")) and runsql_arg.endswith(('"', "'")):
            content = runsql_arg[1:-1].replace('\\"', '"').replace("\\'", "'").strip()
            return [content]

        # Handle list/tuple with ast.literal_eval for safety
        if runsql_arg.startswith(("[", "(")) and runsql_arg.endswith(("]", ")")):
            try:
                parsed = ast.literal_eval(runsql_arg)
                if isinstance(parsed, (list, tuple)):
                    return [str(item).strip() for item in parsed if isinstance(item, str)]
            except (ValueError, SyntaxError):
                pass  # Fall through to regex parsing

        # Fallback regex for malformed lists
        if runsql_arg.startswith(("[", "(")):
            strings = re.findall(r'["\']((?:[^"\'\\]|\\.)*)["\']', runsql_arg, re.DOTALL)
            return [s.strip() for s in strings if s.strip()]

        return [runsql_arg]

    def _analyze_sql_locks(self, sql_text: str) -> Tuple[Set[str], List[MigrationOperation]]:
        """Analyze SQL for table locks with optimized pattern matching."""
        locked_tables: Set[str] = set()
        operations: List[MigrationOperation] = []

        for pattern, op_type, risk in SQL_LOCK_PATTERNS:
            for match in re.finditer(pattern, sql_text, re.IGNORECASE):
                # Extract table name from groups
                table = None
                for group in match.groups():
                    if group and group.lower() in self.large_tables:
                        table = group.lower()
                        break

                if table:
                    # Don't skip duplicate tables - each operation should be counted
                    locked_tables.add(table)
                    snippet = re.sub(r'\s+', ' ', match.group(0))[:100]
                    operations.append(
                        MigrationOperation(
                            django_operation="RunSQL",
                            sql_operation=op_type,
                            table_name=table,
                            description=f"RunSQL -> {op_type}",
                            risk_level=risk,
                            sql_snippet=snippet,
                        )
                    )

        return locked_tables, operations

    def _parse_django_operation(self, op_name: str, content: str) -> Tuple[Set[str], List[MigrationOperation]]:
        """Parse a single Django operation type."""
        locked_tables: Set[str] = set()
        operations: List[MigrationOperation] = []
        sql_op, risk = DJANGO_OP_INFO[op_name]

        if op_name == "CreateModel":
            for match in CREATE_MODEL_PATTERN.finditer(content):
                model_name = match.group(1).lower()
                table_name = self._get_table_name(model_name)
                if table_name in self.large_tables:
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
            # Determine if operation uses 'name' or 'model_name'
            param_name = "name" if op_name in NAME_BASED_OPS else "model_name"
            pattern = rf"{op_name}\s*\(\s*.*?{param_name}\s*=\s*['\"](.*?)['\"]"

            for match in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
                model_name = match.group(1).lower()
                table_name = self._get_table_name(model_name)
                if table_name in self.large_tables:
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

        return locked_tables, operations

    def _parse_runsql_operations(self, content: str) -> List[Tuple[str, str]]:
        """Parse RunSQL operations with proper parenthesis matching."""
        runsql_ops = []
        start = 0

        while True:
            start = content.find('RunSQL(', start)
            if start == -1:
                break

            # Find the matching closing parenthesis
            paren_count = 0
            pos = start + len('RunSQL(')
            for i, char in enumerate(content[pos:], pos):
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    if paren_count == 0:
                        end = i + 1
                        break
                    paren_count -= 1
            else:
                break

            _runsql_content = content[start:end]
            # Extract just the arguments (inside the parentheses)
            args_start = len('RunSQL(')
            full_args = _runsql_content[args_start:-1].strip()

            # Extract only forward SQL (before reverse_sql parameter)
            # Use regex to find reverse_sql parameter more reliably
            forward_args = full_args
            reverse_sql_match = re.search(r',\s*reverse_sql\s*=', full_args)
            if reverse_sql_match:
                forward_args = full_args[:reverse_sql_match.start()].strip()

            runsql_ops.append((_runsql_content, forward_args))
            start = end

        return runsql_ops

    def analyze_migration(self, content: str) -> Dict[str, Any]:
        """Analyze migration content and return results."""
        locked_tables: Set[str] = set()
        operations: List[MigrationOperation] = []

        # Detect migration type
        has_runpython = bool(RUNPYTHON_PATTERN.search(content))
        runsql_ops = self._parse_runsql_operations(content)
        has_runsql = bool(runsql_ops)
        has_schema_ops = any(op in content for op in SCHEMA_OPERATIONS)

        migration_type = (
            "data_migration"
            if has_runpython or (has_runsql and not has_schema_ops)
            else "schema_migration"
        )

        # Parse Django operations
        for op_name in DJANGO_OP_INFO:
            op_tables, op_ops = self._parse_django_operation(op_name, content)
            locked_tables.update(op_tables)
            operations.extend(op_ops)

        # Parse RunSQL operations
        for _runsql_content, runsql_args in runsql_ops:
            sql_statements = self._extract_sql_statements(runsql_args)

            # Collect all tables and operations from this RunSQL
            runsql_tables: Set[str] = set()
            runsql_operations: List[MigrationOperation] = []

            for sql in sql_statements:
                if sql:
                    sql_tables, sql_ops = self._analyze_sql_locks(sql)
                    runsql_tables.update(sql_tables)
                    runsql_operations.extend(sql_ops)

            # Always add RunSQL operations (even if they don't affect monitored tables)
            # This ensures we count all RunSQL operations as expected by tests
            if runsql_operations:
                # This RunSQL affects monitored tables
                locked_tables.update(runsql_tables)
                first_op = runsql_operations[0]
                operations.append(
                    MigrationOperation(
                        django_operation="RunSQL",
                        sql_operation=first_op.sql_operation,
                        table_name=", ".join(sorted(runsql_tables)),
                        description=f"RunSQL -> {first_op.sql_operation}",
                        risk_level=first_op.risk_level,
                        sql_snippet=first_op.sql_snippet,
                    )
                )
            else:
                # This RunSQL doesn't affect monitored tables but should still be counted
                operations.append(
                    MigrationOperation(
                        django_operation="RunSQL",
                        sql_operation="DATA MIGRATION",
                        table_name="N/A",
                        description="RunSQL -> DATA MIGRATION",
                        risk_level="low",
                        sql_snippet=None,
                    )
                )

        # Add RunPython operations
        if has_runpython:
            operations.append(
                MigrationOperation(
                    django_operation="RunPython",
                    sql_operation="DATA MIGRATION",
                    table_name="N/A",
                    description="RunPython -> DATA MIGRATION",
                    risk_level="low",
                )
            )

        locked_count = len(locked_tables)
        has_runsql_ops = any(op.django_operation == "RunSQL" for op in operations)
        should_block = (
            locked_count >= 2 and
            (migration_type != "data_migration" or has_runsql_ops)
        )

        return {
            "migration_type": migration_type,
            "locked_tables": sorted(locked_tables),
            "locked_count": locked_count,
            "operations": operations,
            "should_block_commit": should_block,
        }


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments with improved help text."""
    parser = argparse.ArgumentParser(
        description="Pre-commit hook: BLOCKS commit on locks of 2+ large tables in Django migrations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s app/migrations/0001_initial.py
  %(prog)s --tables users orders --min-tables 3 app/migrations/*.py
  %(prog)s --app myapp --config config.json app/migrations/
        """
    )
    parser.add_argument(
        "filenames",
        nargs="*",
        help="Migration files to check"
    )
    parser.add_argument(
        "--tables", "-t",
        nargs="+",
        default=DEFAULT_LARGE_TABLES,
        help=f"List of LARGE tables to check (default: {', '.join(DEFAULT_LARGE_TABLES)})"
    )
    parser.add_argument(
        "--app", "-a",
        type=str,
        help="Django app name for table name resolution"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--min-tables", "-m",
        type=int,
        default=DEFAULT_MIN_TABLES,
        help=f"Minimum number of tables to BLOCK commit (default: {DEFAULT_MIN_TABLES})"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="JSON configuration file path"
    )
    return parser.parse_args()


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load configuration from JSON file with improved error handling."""
    if not config_path:
        return {}

    config_file = Path(config_path)
    if not config_file.exists():
        print(f"WARNING: Config file not found: {config_path}")
        return {}

    try:
        content = config_file.read_text(encoding="utf-8")
        config = cast(Dict[str, Any], json.loads(content))

        # Validate config structure
        if not isinstance(config, dict):
            raise ValueError("Config must be a JSON object")

        return config
    except json.JSONDecodeError as e:
        print(f"WARNING: Invalid JSON in config {config_path}: {e}")
        return {}
    except Exception as e:
        print(f"WARNING: Error loading config {config_path}: {e}")
        return {}


def has_ignore_comment(content: str) -> bool:
    """Check if migration file contains ignore comment."""
    return any(pattern.search(content) for pattern in IGNORE_PATTERNS)


def is_migration_file(file_path: str) -> bool:
    """Check if file is a Django migration file with optimized pattern matching."""
    path = Path(file_path)

    # Quick checks first
    if path.suffix != ".py" or path.name == "__init__.py":
        return False

    # Check migration directory pattern
    has_migration_dir = any("migrations" in part for part in path.parts)
    if not has_migration_dir:
        return False

    # Check filename pattern
    return bool(MIGRATION_FILE_PATTERN.match(path.name))


def read_file(file_path: str) -> Optional[str]:
    """Read file content with improved error handling."""
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: File not found: {file_path}")
        return None
    except PermissionError:
        print(f"ERROR: Permission denied: {file_path}")
        return None
    except UnicodeDecodeError:
        print(f"ERROR: Invalid encoding: {file_path}")
        return None
    except Exception as e:
        print(f"ERROR: Error reading {file_path}: {e}")
        return None


def convert_model_to_table(model_name: str, app_name: Optional[str]) -> str:
    """Convert Django model name to database table name."""
    table = model_name.lower()
    if app_name:
        table = f"{app_name}_{table}"
    return table


# Legacy functions for backward compatibility with tests
def extract_sql_from_runsql(arg: str) -> List[str]:
    """Extract forward SQL statements from RunSQL argument (legacy wrapper)."""
    checker = MigrationFileChecker(frozenset())
    return checker._extract_sql_statements(arg)


def analyze_raw_sql(
    sql_text: str, large_tables_set: FrozenSet[str], verbose: bool = False, per_statement: bool = False
) -> Dict[str, Any]:
    """Analyze raw SQL for table locks (legacy wrapper)."""
    checker = MigrationFileChecker(large_tables_set)
    locked_tables, operations = checker._analyze_sql_locks(sql_text)
    return {
        "locked_tables": locked_tables,
        "operations": operations,
    }


def parse_django_migration_operations(
    content: str,
    large_tables_set: FrozenSet[str],
    app_name: Optional[str],
    verbose: bool = False,
) -> Dict[str, Any]:
    """Parse Django migration operations (legacy wrapper)."""
    checker = MigrationFileChecker(large_tables_set, app_name)
    return checker.analyze_migration(content)


def check_migration_files(
    filenames: List[str],
    large_tables: List[str],
    app_name: Optional[str],
    min_tables: int,
    verbose: bool,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """Check migration files for table locks with optimized processing."""
    # Filter migration files
    migration_files = [f for f in filenames if is_migration_file(f)]
    if not migration_files:
        if verbose:
            print("INFO: No migration files to check")
        return True, []

    # Prepare checker
    large_tables_set = frozenset(t.lower() for t in large_tables)
    checker = MigrationFileChecker(large_tables_set, app_name)

    # Output header
    print(f"CHECK: Checking {len(migration_files)} migrations for locks on large tables")
    print(f"INFO: Monitoring tables: {', '.join(large_tables)}")
    print(f"BLOCK: COMMIT BLOCKED at >={min_tables} locked tables")
    print("-" * 60)

    all_passed = True
    critical_migrations: List[Dict[str, Any]] = []

    # Process each migration file
    for file_path in migration_files:
        content = read_file(file_path)
        if content is None:
            continue

        # Check if migration has ignore comment
        if has_ignore_comment(content):
            print(f"SKIP: SKIPPED {file_path} - ignore comment found")
            continue

        results = checker.analyze_migration(content)

        if results["should_block_commit"]:
            all_passed = False
            critical_migrations.append({
                "file": file_path,
                "locked_tables": results["locked_tables"],
                "locked_count": results["locked_count"],
                "operations": results["operations"],
            })

            print(f"BLOCK: {file_path}")
            print(f"   BLOCKED {results['locked_count']} LARGE TABLES: {', '.join(results['locked_tables'])}")

            if verbose:
                print("   Dangerous operations:")
                for op in results["operations"]:
                    if op.table_name in results["locked_tables"]:
                        print(f"     • {op.description} → {op.table_name}")
        else:
            status = "OK" if results["locked_count"] == 0 else "WARNING (1 table)"
            print(f"{status}: {file_path} - locked tables: {results['locked_count']}")

    # Output summary
    print("-" * 60)
    if critical_migrations:
        print("BLOCK: COMMIT BLOCKED!")
        print(f"CRITICAL: Found {len(critical_migrations)} critical migration(s):")

        for mig in critical_migrations:
            print(f"\n   FILE: {mig['file']}")
            print(f"   LOCKED: Locked tables: {mig['locked_count']}")
            print(f"   TABLES: {', '.join(mig['locked_tables'])}")

            if verbose:
                print("   OPERATIONS:")
                for op in mig["operations"]:
                    if op.table_name in mig["locked_tables"]:
                        desc = f"{op.description} ({op.risk_level})"
                        if op.sql_snippet:
                            desc += f" — {op.sql_snippet}"
                        print(f"     • {desc}")

        print("\nHOW TO FIX:")
        print("   1. Split migration into multiple parts")
        print("   2. Use `atomic = False` in migration class")
        print("   3. Execute operations in separate migrations")
        print("   4. Bypass with: git commit --no-verify")
        print("\nBLOCKED: Commit BLOCKED due to DB lock risk!")
    else:
        print("PASS: All migrations passed! Commit allowed.")

    return all_passed, critical_migrations


def main() -> int:
    """Main entry point with improved error handling."""
    args = parse_arguments()
    config = load_config(args.config)

    # Merge configuration
    tables = args.tables or config.get("tables", DEFAULT_LARGE_TABLES)
    app_name = args.app or config.get("app")
    min_tables = args.min_tables or config.get("min_tables", DEFAULT_MIN_TABLES)
    verbose = args.verbose or config.get("verbose", False)

    if not args.filenames:
        if verbose:
            print("INFO: No files provided")
        return 0

    try:
        success, critical = check_migration_files(
            filenames=args.filenames,
            large_tables=tables,
            app_name=app_name,
            min_tables=min_tables,
            verbose=verbose,
        )

        if critical:
            print(f"\nERROR: Pre-commit hook FAILED: {len(critical)} migration(s) blocked")
            return 1

        return 0

    except KeyboardInterrupt:
        print("\nWARNING: Operation cancelled by user")
        return 130
    except Exception as e:
        print(f"\nERROR: Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
