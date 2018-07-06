# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import QMessageBox, qApp

import traceback


def ExceptHandler(etype, value, tb):
    msg = traceback.format_exception(etype, value, tb)
    QMessageBox.warning(None, "Exception occurred!",
                        "".join(msg), QMessageBox.Ok)
