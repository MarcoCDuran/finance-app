import sys
import os
path = os.path.expanduser('~/finance-app/backend')
if path not in sys.path:
    sys.path.insert(0, path)

from main import app as application
