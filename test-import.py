#!/usr/bin/env python3
"""
Debug script to test osd_core import and show actual error
"""

import sys
import traceback
import importlib

VERSION = "1.0.3"

print("Python version:", sys.version)
print("Python path:", sys.path)
print()

module_name = sys.argv[1]

try:
    print(f"[{VERSION}] Attempting to import {module_name}...")
    module = importlib.import_module(module_name)
    print("✓ Import successful!")
    print(f"Available in module:", dir(module))
except ImportError as e:
    print(f"[{VERSION}] ✗ ImportError in {module_name}.py:", e)
    traceback.print_exc()
except SyntaxError as e:
    print(f"[{VERSION}] ✗ SyntaxError in {module_name}.py:", e)
    traceback.print_exc()
except Exception as e:
    print(f"[{VERSION}] ✗ Unexpected error {e}")
    traceback.print_exc()