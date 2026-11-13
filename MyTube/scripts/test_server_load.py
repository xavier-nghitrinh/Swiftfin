import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import backend.main
    print("SUCCESS: backend.main loaded cleanly!")
    print("App Title:", backend.main.app.title)
except Exception as e:
    import traceback
    print("ERROR loading backend.main:")
    traceback.print_exc()
