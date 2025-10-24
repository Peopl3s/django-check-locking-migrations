#!/usr/bin/env python3
"""
Tests for Django Migration Lock Checker
"""

import pytest
import tempfile
import os
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add the parent directory to the path to import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from migration_lock_checker.check_migration_locks import (
    parse_arguments,
    load_config,
    read_migration_file,
    is_migration_file,
    parse_django_migration_operations,
    convert_model_to_table,
    extract_sql_from_runsql,
    analyze_raw_sql,
    check_migration_files,
    main
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def default_tables():
    """Default tables for testing"""
    return ['users', 'orders', 'payments']


def create_temp_file(temp_dir, filename, content):
    """Create a temporary file with given content"""
    filepath = os.path.join(temp_dir, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        f.write(content)
    return filepath


class TestMigrationLockChecker:
    """Test cases for Django Migration Lock Checker"""

    def test_convert_model_to_table(self):
        """Test model to table name conversion"""
        # Test without app name
        assert convert_model_to_table('User') == 'user'
        assert convert_model_to_table('UserProfile') == 'userprofile'
        
        # Test with app name
        assert convert_model_to_table('User', 'auth') == 'auth_user'
        assert convert_model_to_table('UserProfile', 'auth') == 'auth_userprofile'

    def test_is_migration_file(self):
        """Test migration file detection"""
        # Valid migration files
        assert is_migration_file('app/migrations/0001_initial.py') is True
        assert is_migration_file('app/migrations/1234_add_field.py') is True
        assert is_migration_file('/full/path/app/migrations/0002_auto_20231201.py') is True
        
        # Invalid migration files
        assert is_migration_file('app/models.py') is False
        assert is_migration_file('app/migrations/__init__.py') is False
        assert is_migration_file('app/migrations/test.py') is False
        assert is_migration_file('app/migrations/001_initial.txt') is False

    @pytest.mark.parametrize("sql_block,expected", [
        ('"SELECT * FROM users"', 'SELECT * FROM users'),
        ("'UPDATE users SET active = True'", 'UPDATE users SET active = True'),
        ('["SELECT * FROM users", "SELECT * FROM orders"]', 'SELECT * FROM users'),
    ])
    def test_extract_sql_from_runsql(self, sql_block, expected):
        """Test SQL extraction from RunSQL blocks"""
        result = extract_sql_from_runsql(sql_block)
        assert result == expected

    def test_analyze_raw_sql(self):
        """Test raw SQL analysis for table locks"""
        sql_text = "ALTER TABLE users ADD COLUMN email VARCHAR(255);"
        result = analyze_raw_sql(sql_text, ['users', 'orders'])
        
        assert len(result['locked_tables']) == 1
        assert 'users' in result['locked_tables']
        assert len(result['operations']) == 1
        assert result['operations'][0]['sql_operation'] == 'ALTER TABLE'

    def test_analyze_raw_sql_multiple_operations(self):
        """Test raw SQL analysis with multiple operations"""
        sql_text = """
        ALTER TABLE users ADD COLUMN email VARCHAR(255);
        CREATE INDEX idx_orders_status ON orders(status);
        DROP TABLE payments;
        """
        result = analyze_raw_sql(sql_text, ['users', 'orders', 'payments'])
        
        assert len(result['locked_tables']) == 3
        assert 'users' in result['locked_tables']
        assert 'orders' in result['locked_tables']
        assert 'payments' in result['locked_tables']
        assert len(result['operations']) == 3

    def test_parse_django_migration_operations_create_model(self):
        """Test parsing Django CreateModel operation"""
        content = '''
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=100)),
            ],
        )
        '''
        result = parse_django_migration_operations(content, ['auth_user'], 'auth')
        
        assert result['migration_type'] == 'schema_migration'
        assert len(result['operations']) == 1
        assert result['operations'][0]['django_operation'] == 'CreateModel'
        assert result['operations'][0]['table_name'] == 'auth_user'

    def test_parse_django_migration_operations_add_field(self):
        """Test parsing Django AddField operation"""
        content = '''
        migrations.AddField(
            model_name='User',
            name='email',
            field=models.EmailField(max_length=254),
        )
        '''
        result = parse_django_migration_operations(content, ['auth_user'], 'auth')
        
        assert len(result['operations']) == 1
        assert result['operations'][0]['django_operation'] == 'AddField'
        assert result['operations'][0]['table_name'] == 'auth_user'

    def test_parse_django_migration_operations_runsql(self):
        """Test parsing Django RunSQL operation"""
        content = '''
        migrations.RunSQL(
            "ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            reverse_sql="ALTER TABLE users DROP COLUMN email;"
        )
        '''
        result = parse_django_migration_operations(content, ['users'])
        
        assert result['migration_type'] == 'data_migration'
        assert len(result['operations']) == 1
        assert result['operations'][0]['sql_operation'] == 'ALTER TABLE'

    def test_parse_django_migration_operations_rename_field(self):
        """Test parsing Django RenameField operation"""
        content = '''
        migrations.RenameField(
            model_name='User',
            old_name='username',
            new_name='login_name',
        )
        '''
        result = parse_django_migration_operations(content, ['auth_user'], 'auth')
        
        assert len(result['operations']) == 1
        assert result['operations'][0]['django_operation'] == 'RenameField'
        assert result['operations'][0]['sql_operation'] == 'ALTER TABLE (RENAME COLUMN)'
        assert result['operations'][0]['table_name'] == 'auth_user'

    def test_parse_django_migration_operations_multiple_locks(self):
        """Test parsing migration with multiple table locks"""
        content = '''
        migrations.AddField(
            model_name='User',
            name='email',
            field=models.EmailField(max_length=254),
        )
        migrations.AddField(
            model_name='Order',
            name='status',
            field=models.CharField(max_length=50),
        )
        '''
        result = parse_django_migration_operations(content, ['myapp_user', 'myapp_order'], 'myapp')
        
        assert len(result['locked_tables']) == 2
        assert result['should_block_commit'] is True
        assert result['locked_count'] == 2

    def test_check_migration_files_no_migrations(self, default_tables):
        """Test checking when no migration files are provided"""
        result = check_migration_files([], default_tables, None, 2, False)
        assert result[0] is True  # Should pass
        assert len(result[1]) == 0  # No critical migrations

    def test_check_migration_files_with_critical_migration(self, temp_dir):
        """Test checking with critical migration that should be blocked"""
        # Create a migration file with multiple large table locks
        migration_content = '''
        migrations.AddField(
            model_name='User',
            name='email',
            field=models.EmailField(max_length=254),
        )
        migrations.AddField(
            model_name='Order',
            name='status',
            field=models.CharField(max_length=50),
        )
        '''
        
        migration_file = create_temp_file(temp_dir, 'myapp/migrations/0001_add_fields.py', migration_content)
        
        # Use the correct table names with app prefix
        tables_to_check = ['myapp_user', 'myapp_order', 'payments']
        result = check_migration_files([migration_file], tables_to_check, 'myapp', 2, False)
        
        assert result[0] is False  # Should fail
        assert len(result[1]) == 1  # One critical migration
        assert result[1][0]['locked_count'] == 2

    def test_check_migration_files_safe_migration(self, temp_dir):
        """Test checking with safe migration that should pass"""
        # Create a migration file with single table lock
        migration_content = '''
        migrations.AddField(
            model_name='User',
            name='email',
            field=models.EmailField(max_length=254),
        )
        '''
        
        migration_file = create_temp_file(temp_dir, 'myapp/migrations/0001_add_email.py', migration_content)
        
        # Use the correct table names with app prefix
        tables_to_check = ['myapp_user', 'orders', 'payments']
        result = check_migration_files([migration_file], tables_to_check, 'myapp', 2, False)
        
        assert result[0] is True  # Should pass
        assert len(result[1]) == 0  # No critical migrations

    def test_load_config_file_not_exists(self):
        """Test loading configuration when file doesn't exist"""
        result = load_config('/nonexistent/config.json')
        assert result == {}

    def test_load_config_valid_json(self, temp_dir):
        """Test loading valid JSON configuration"""
        config_content = '{"tables": ["users", "orders"], "min_tables": 3}'
        config_file = create_temp_file(temp_dir, 'config.json', config_content)
        
        result = load_config(config_file)
        assert result['tables'] == ['users', 'orders']
        assert result['min_tables'] == 3

    def test_load_config_invalid_json(self, temp_dir):
        """Test loading invalid JSON configuration"""
        config_content = '{"tables": ["users", "orders"'  # Invalid JSON
        config_file = create_temp_file(temp_dir, 'config.json', config_content)
        
        with patch('builtins.print') as mock_print:
            result = load_config(config_file)
            assert result == {}
            mock_print.assert_called()

    def test_read_migration_file_success(self, temp_dir):
        """Test successful migration file reading"""
        content = "Test migration content"
        migration_file = create_temp_file(temp_dir, '0001_test.py', content)
        
        result = read_migration_file(migration_file)
        assert result == content

    def test_read_migration_file_error(self):
        """Test reading migration file that doesn't exist"""
        with patch('builtins.print') as mock_print:
            result = read_migration_file('/nonexistent/file.py')
            assert result is None
            mock_print.assert_called()

    @patch('sys.argv', ['check-migration-locks', '--tables', 'users', 'orders'])
    def test_parse_arguments_default(self):
        """Test parsing arguments with default values"""
        args = parse_arguments()
        assert args.tables == ['users', 'orders']
        assert args.min_tables == 2
        assert args.verbose is False

    @patch('sys.argv', ['check-migration-locks', '--verbose', '--min-tables', '3'])
    def test_parse_arguments_with_options(self):
        """Test parsing arguments with options"""
        args = parse_arguments()
        assert args.min_tables == 3
        assert args.verbose is True

    @patch('migration_lock_checker.check_migration_locks.check_migration_files')
    @patch('migration_lock_checker.check_migration_locks.parse_arguments')
    def test_main_function_success(self, mock_parse_args, mock_check_files):
        """Test main function with successful execution"""
        # Mock arguments
        mock_args = MagicMock()
        mock_args.filenames = ['test.py']
        mock_args.tables = ['users']
        mock_args.app = None
        mock_args.min_tables = 2
        mock_args.verbose = False
        mock_args.strict = True
        mock_args.config = None
        mock_parse_args.return_value = mock_args
        
        # Mock successful check
        mock_check_files.return_value = (True, [])
        
        result = main()
        assert result == 0

    @patch('migration_lock_checker.check_migration_locks.check_migration_files')
    @patch('migration_lock_checker.check_migration_locks.parse_arguments')
    def test_main_function_with_critical_migrations(self, mock_parse_args, mock_check_files):
        """Test main function with critical migrations"""
        # Mock arguments
        mock_args = MagicMock()
        mock_args.filenames = ['test.py']
        mock_args.tables = ['users']
        mock_args.app = None
        mock_args.min_tables = 2
        mock_args.verbose = False
        mock_args.strict = True
        mock_args.config = None
        mock_parse_args.return_value = mock_args
        
        # Mock failed check with critical migrations
        mock_check_files.return_value = (False, [{'file': 'test.py'}])
        
        with patch('builtins.print'):
            result = main()
            assert result == 1

    @patch('migration_lock_checker.check_migration_locks.parse_arguments')
    def test_main_function_no_files(self, mock_parse_args):
        """Test main function with no files provided"""
        # Mock arguments with no files
        mock_args = MagicMock()
        mock_args.filenames = []
        mock_args.verbose = True
        mock_parse_args.return_value = mock_args
        
        with patch('builtins.print'):
            result = main()
            assert result == 0


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_migration_content(self):
        """Test parsing empty migration content"""
        result = parse_django_migration_operations('', ['users'])
        assert result['locked_count'] == 0
        assert result['should_block_commit'] is False

    def test_migration_with_runpython(self):
        """Test migration with RunPython operation"""
        content = '''
        migrations.RunPython(forward_func, reverse_func)
        '''
        result = parse_django_migration_operations(content, ['users'])
        assert result['migration_type'] == 'data_migration'

    def test_sql_without_table_locks(self):
        """Test SQL that doesn't lock monitored tables"""
        sql_text = "SELECT * FROM small_table;"
        result = analyze_raw_sql(sql_text, ['users', 'orders'])
        assert len(result['locked_tables']) == 0

    def test_update_without_where(self):
        """Test UPDATE without WHERE clause"""
        sql_text = "UPDATE users SET active = true;"
        result = analyze_raw_sql(sql_text, ['users'])
        assert len(result['locked_tables']) == 1
        assert result['operations'][0]['sql_operation'] == 'UPDATE without WHERE'

    def test_delete_without_where(self):
        """Test DELETE without WHERE clause"""
        sql_text = "DELETE FROM orders;"
        result = analyze_raw_sql(sql_text, ['orders'])
        assert len(result['locked_tables']) == 1
        assert result['operations'][0]['sql_operation'] == 'DELETE without WHERE'

    def test_rename_column_sql(self):
        """Test RENAME COLUMN SQL operation"""
        sql_text = "ALTER TABLE users RENAME COLUMN username TO login_name;"
        result = analyze_raw_sql(sql_text, ['users'])
        assert len(result['locked_tables']) == 1
        assert result['operations'][0]['sql_operation'] == 'RENAME COLUMN'
        assert 'users' in result['locked_tables']
