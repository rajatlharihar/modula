import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import BaseHTTPRequestHandler

from modula.httpio import read_json, send
from modula import web


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            payload = read_json(self)
            data = web.sku_bytes(payload)
            send(self, 200, data,
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                 {"Content-Disposition": 'attachment; filename="Modula-SKU.xlsx"'})
        except Exception as error:
            send(self, 500, {"error": f"Something went wrong: {error}"})
