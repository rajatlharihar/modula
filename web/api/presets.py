import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import BaseHTTPRequestHandler

from modula.httpio import send
from modula import web


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        send(self, 200, {"presets": web.presets(), **web.catalogue()})
