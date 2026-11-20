import os
import sys

# The application uses imports relative to the linsticky/ directory
# (e.g. "from content import codec"), mirror that for the tests.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "linsticky"))
