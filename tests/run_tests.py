#!/usr/bin/env python3
"""
Test runner for Django Migration Lock Checker using pytest
"""

import os
import subprocess
import sys


def run_tests():
    """Run all tests using pytest"""
    # Add the parent directory to the path
    parent_dir = os.path.join(os.path.dirname(__file__), "..")

    # Run pytest with the tests directory
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                os.path.dirname(__file__),
                "-v",
                "--tb=short",
            ],
            cwd=parent_dir,
        )

        return result.returncode
    except subprocess.CalledProcessError as e:
        return e.returncode
    except FileNotFoundError:
        print("pytest not found. Please install pytest:")
        print("pip install pytest")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
