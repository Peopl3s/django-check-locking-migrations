#!/usr/bin/env python3
"""
Pre-commit hook для проверки блокировок нескольких больших таблиц в Django миграциях
"""

import re
import sys
import argparse
import json
from pathlib import Path

# Конфигурация по умолчанию для pre-commit
DEFAULT_LARGE_TABLES = ['users', 'orders', 'payments', 'audit_logs', 'logs']
DEFAULT_MIN_TABLES = 2

def parse_arguments():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(
        description='Pre-commit hook: проверка блокировок НЕСКОЛЬКИХ больших таблиц в Django миграциях'
    )
    parser.add_argument(
        'filenames',
        nargs='*',
        help='Файлы миграций для проверки'
    )
    parser.add_argument(
        '--tables', '-t',
        nargs='+',
        default=DEFAULT_LARGE_TABLES,
        help=f'Список БОЛЬШИХ таблиц для проверки (по умолчанию: {DEFAULT_LARGE_TABLES})'
    )
    parser.add_argument(
        '--app', '-a',
        type=str,
        help='Имя Django приложения (для определения полных имен таблиц)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Подробный вывод'
    )
    parser.add_argument(
        '--min-tables', '-m',
        type=int,
        default=DEFAULT_MIN_TABLES,
        help=f'Минимальное количество таблиц для беспокойства (по умолчанию: {DEFAULT_MIN_TABLES})'
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        help='JSON файл с конфигурацией'
    )
    
    return parser.parse_args()

def load_config(config_path):
    """Загрузка конфигурации из JSON файла"""
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Ошибка загрузки конфигурации {config_path}: {e}")
    return {}

def read_migration_file(file_path):
    """Чтение файла миграции"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"❌ Ошибка при чтении файла {file_path}: {e}")
        return None

def is_migration_file(file_path):
    """Проверяет, является ли файл миграцией Django"""
    path = Path(file_path)
    return (path.suffix == '.py' and 
            'migrations' in path.parts and 
            path.name != '__init__.py' and
            re.match(r'^\d{4}_.*\.py$', path.name))

def parse_django_migration_operations(content, tables, app_name=None, verbose=False):
    """
    Анализирует операции Django миграции и определяет потенциальные блокировки
    """
    results = {
        'locked_tables': set(),
        'operations': [],
        'multiple_locks': False,
        'critical_risk': False,
        'migration_type': 'unknown',
        'locked_count': 0
    }
    
    if not content:
        return results
    
    # Паттерны для определения типа миграции
    if 'RunPython' in content or 'RunSQL' in content:
        results['migration_type'] = 'data_migration'
    else:
        results['migration_type'] = 'schema_migration'
    
    # Словарь соответствия операций Django и потенциальных блокировок
    django_operations = {
        'CreateModel': 'CREATE TABLE',
        'DeleteModel': 'DROP TABLE', 
        'RenameModel': 'RENAME TABLE',
        'AlterModelTable': 'ALTER TABLE',
        'AddField': 'ALTER TABLE (ADD COLUMN)',
        'RemoveField': 'ALTER TABLE (DROP COLUMN)',
        'AlterField': 'ALTER TABLE (ALTER COLUMN)',
        'RenameField': 'ALTER TABLE (RENAME COLUMN)',
        'AddIndex': 'CREATE INDEX',
        'RemoveIndex': 'DROP INDEX',
        'AddConstraint': 'ALTER TABLE (ADD CONSTRAINT)',
        'RemoveConstraint': 'ALTER TABLE (DROP CONSTRAINT)',
    }
    
    # Поиск операций миграции
    for op_name, sql_op in django_operations.items():
        pattern = rf"{op_name}\(.*?name=['\"](.*?)['\"]"
        matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            model_name = match.group(1).lower()
            table_name = convert_model_to_table(model_name, app_name)
            
            # Проверяем, есть ли эта таблица в списке больших таблиц
            if table_name in [t.lower() for t in tables]:
                results['locked_tables'].add(table_name)
                results['operations'].append({
                    'django_operation': op_name,
                    'sql_operation': sql_op,
                    'model_name': model_name,
                    'table_name': table_name,
                    'description': f"{op_name} -> {sql_op}",
                    'risk_level': 'high' if sql_op in ['ALTER TABLE', 'DROP TABLE', 'CREATE INDEX'] else 'medium'
                })
    
    # Анализ RunSQL операций
    sql_blocks = re.findall(r'RunSQL\s*\(.*?sql\s*=\s*(.*?)\).*?\)', content, re.DOTALL)
    for sql_block in sql_blocks:
        sql_text = extract_sql_from_runsql(sql_block)
        if sql_text:
            sql_results = analyze_raw_sql(sql_text, tables, verbose)
            results['locked_tables'].update(sql_results['locked_tables'])
            results['operations'].extend(sql_results['operations'])
    
    results['locked_tables'] = list(results['locked_tables'])
    results['locked_count'] = len(results['locked_tables'])
    results['multiple_locks'] = results['locked_count'] >= 2
    results['critical_risk'] = results['locked_count'] >= 3
    
    return results

def convert_model_to_table(model_name, app_name=None):
    """Конвертирует имя модели Django в имя таблицы в БД"""
    table_name = model_name.lower()
    if app_name:
        table_name = f"{app_name}_{table_name}"
    return table_name

def extract_sql_from_runsql(sql_block):
    """Извлекает SQL текст из блока RunSQL"""
    if isinstance(sql_block, str):
        sql_block = ' '.join(sql_block.split())
        if sql_block.startswith(('"', "'")):
            sql_text = sql_block[1:-1].replace('\\"', '"').replace("\\'", "'")
            return sql_text
        elif sql_block.startswith('['):
            try:
                import ast
                sql_list = ast.literal_eval(sql_block)
                if isinstance(sql_list, list) and len(sql_list) > 0:
                    return sql_list[0]
            except:
                pass
    return sql_block

def analyze_raw_sql(sql_text, tables, verbose=False):
    """Анализирует сырой SQL на предмет блокировок таблиц"""
    results = {
        'locked_tables': set(),
        'operations': []
    }
    
    tables_lower = [table.lower() for table in tables]
    
    lock_patterns = [
        (r'ALTER\s+TABLE\s+[`"]?([\w_]+)[`"]?\s+', 'ALTER TABLE', 'high'),
        (r'CREATE\s+(UNIQUE\s+)?INDEX\s+.*?\s+ON\s+[`"]?([\w_]+)[`"]?', 'CREATE INDEX', 'high'),
        (r'DROP\s+INDEX\s+.*?\s+ON\s+[`"]?([\w_]+)[`"]?', 'DROP INDEX', 'high'),
        (r'TRUNCATE\s+TABLE\s+[`"]?([\w_]+)[`"]?', 'TRUNCATE TABLE', 'high'),
        (r'DROP\s+TABLE\s+[`"]?([\w_]+)[`"]?', 'DROP TABLE', 'high'),
        (r'UPDATE\s+[`"]?([\w_]+)[`"]?\s+SET\s+(?!.*WHERE)', 'UPDATE без WHERE', 'high'),
        (r'DELETE\s+FROM\s+[`"]?([\w_]+)[`"]?\s+(?!WHERE)', 'DELETE без WHERE', 'high'),
    ]
    
    for pattern, operation_type, risk_level in lock_patterns:
        matches = re.finditer(pattern, sql_text, re.IGNORECASE)
        for match in matches:
            for group in match.groups():
                if group and group.lower() in tables_lower:
                    results['locked_tables'].add(group)
                    results['operations'].append({
                        'django_operation': 'RunSQL',
                        'sql_operation': operation_type,
                        'table_name': group,
                        'sql_snippet': match.group(0)[:100],
                        'description': f"RunSQL -> {operation_type}",
                        'risk_level': risk_level
                    })
                    break
    
    results['locked_tables'] = list(results['locked_tables'])
    return results

def check_migration_files(filenames, tables, app_name, min_tables, verbose):
    """Проверяет список файлов миграций"""
    migration_files = [f for f in filenames if is_migration_file(f)]
    
    if not migration_files:
        if verbose:
            print("📝 Файлы миграций не найдены для проверки")
        return True
    
    all_passed = True
    critical_migrations = []
    
    print(f"🔍 Pre-commit: проверка {len(migration_files)} миграций на блокировки больших таблиц")
    print(f"📊 Мониторим таблицы: {', '.join(tables)}")
    print("-" * 60)
    
    for migration_file in migration_files:
        content = read_migration_file(migration_file)
        if content is None:
            continue
            
        results = parse_django_migration_operations(content, tables, app_name, verbose)
        
        if results['locked_count'] >= min_tables:
            all_passed = False
            critical_migrations.append({
                'file': migration_file,
                'locked_tables': results['locked_tables'],
                'locked_count': results['locked_count']
            })
            
            print(f"❌ {migration_file}")
            print(f"   🚨 Заблокировано {results['locked_count']} больших таблиц: {', '.join(results['locked_tables'])}")
            
            if verbose and results['operations']:
                print("   📋 Операции:")
                for op in results['operations']:
                    print(f"     • {op['description']} -> {op['table_name']}")
        else:
            status = "✅ OK" if results['locked_count'] == 0 else "⚠️  Предупреждение"
            print(f"{status} {migration_file} - заблокировано таблиц: {results['locked_count']}")
    
    # Вывод итогов
    print("-" * 60)
    if critical_migrations:
        print(f"🚨 КРИТИЧЕСКИЕ МИГРАЦИИ ({len(critical_migrations)}):")
        for mig in critical_migrations:
            print(f"   • {mig['file']} - {mig['locked_count']} таблиц: {', '.join(mig['locked_tables'])}")
        
        print(f"\n💡 РЕКОМЕНДАЦИИ:")
        print("   - Разбейте миграции на несколько частей")
        print("   - Используйте `Atomic = False` в критических миграциях") 
        print("   - Для обхода pre-commit используйте: git commit --no-verify")
        print("   - Но лучше исправьте миграции! 😊")
    else:
        print("✅ Все миграции прошли проверку!")
    
    return all_passed

def main():
    """Основная функция"""
    args = parse_arguments()
    
    # Загрузка конфигурации
    config = load_config(args.config) if args.config else {}
    
    # Объединение конфигураций (аргументы имеют приоритет)
    tables = args.tables
    app_name = args.app or config.get('app')
    min_tables = args.min_tables
    verbose = args.verbose
    
    if not args.filenames:
        if verbose:
            print("📝 No files provided for checking")
        return 0
    
    # Проверка миграций
    success = check_migration_files(args.filenames, tables, app_name, min_tables, verbose)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
