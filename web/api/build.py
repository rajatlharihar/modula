import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import BaseHTTPRequestHandler

from modula.httpio import read_json, send
from modula import web


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            send(self, 200, web.build_response(read_json(self)))
        except Exception as error:  # keep the page usable, show the message
            send(self, 500, {"error": f"Something went wrong: {error}"})
