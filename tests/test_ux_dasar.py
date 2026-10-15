"""Uji helper penanda tenggat SPK.

Fungsinya kecil tapi memengaruhi urgensi: kalau salah, SPK telat bisa
terlihat aman atau sebaliknya. Karena itu batasannya diuji langsung.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.getcwd())


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    return app
