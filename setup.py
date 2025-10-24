from setuptools import setup, find_packages

setup(
    name="django-migration-lock-checker",
    version="0.1.0",
    description="Pre-commit hook to check Django migrations for multiple large table locks",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[],
    extras_require={
        'test': [
            'pytest>=6.0',
            'pytest-cov>=2.0',
        ],
        'dev': [
            'pytest>=6.0',
            'pytest-cov>=2.0',
            'black>=21.0',
            'flake8>=3.8',
        ],
    },
    entry_points={
        'console_scripts': [
            'check-migration-locks=migration_lock_checker.check_migration_locks:main',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Django",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
    ],
    python_requires=">=3.6",
)
