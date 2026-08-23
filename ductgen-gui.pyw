"""Double-clickable entry point. .pyw so Windows opens it without a console."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ductgen.gui import main

main()
