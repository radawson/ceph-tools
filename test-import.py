#!/usr/bin/env python3
"""
Debug script to test osd_core import and show actual error
"""

import sys
import traceback

print("Python version:", sys.version)
print("Python path:", sys.path)
print()

try:
    print("Attempting to import osd_core...")
    import osd_core
    print("✓ Import successful!")
    print("Available in module:", dir(osd_core))
except ImportError as e:
    print("✗ ImportError:", e)
    traceback.print_exc()
except SyntaxError as e:
    print("✗ SyntaxError in osd_core.py:", e)
    traceback.print_exc()
except Exception as e:
    print("✗ Unexpected error:", e)
    traceback.print_exc()