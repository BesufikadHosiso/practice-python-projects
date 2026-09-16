import os
import sys

# Vercel imports this module from api/, so the project root has to be on the
# path before `app` can be imported.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from asgiref.wsgi import WsgiToAsgi  # noqa: E402

from app.main import create_app  # noqa: E402

# @vercel/python serves WSGI; FastAPI is ASGI, so bridge the two.
# (No streaming or websockets are used, so the bridge is lossless here.)
app = WsgiToAsgi(create_app())
