#!/usr/bin/env python3
"""Simple HTTP server that prints messages to the Rongta RP326 thermal printer."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PRINTER_DEVICE = "/dev/usb/lp0"
PORT = 8765


def print_message(message: str):
    esc_init = b"\x1b\x40"
    feed_and_cut = b"\x1b\x64\x05\x1d\x56\x00"
    data = esc_init + message.encode("utf-8") + b"\n" + feed_and_cut
    with open(PRINTER_DEVICE, "wb") as printer:
        printer.write(data)


class PrintHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/print":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
            message = payload.get("message", "").strip()
            if not message:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing message")
                return
            print_message(message)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        pass  # suppress access logs


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), PrintHandler)
    print(f"Printer server listening on port {PORT}")
    server.serve_forever()
