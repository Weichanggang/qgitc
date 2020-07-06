# -*- coding: utf-8 -*-

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QStyle,
    QMessageBox)

from .gitutils import Git
from .excepthandler import ExceptHandler
from .application import Application
from .mainwindow import MainWindow

import os
import sys
import argparse
import shutil
import subprocess


def setAppUserId(appId):
    if os.name != "nt":
        return

    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appId)
    except:
        pass


def unsetEnv(varnames):
    if hasattr(os, "unsetenv"):
        for var in varnames:
            os.unsetenv(var)
    else:
        for var in varnames:
            try:
                del os.environ[var]
            except KeyError:
                pass


def _setup_argument(prog):
    parser = argparse.ArgumentParser(
        usage=prog + " [-h] <command> [<args>]")
    subparsers = parser.add_subparsers(
        title="The <command> list",
        dest="cmd", metavar="")

    log_parser = subparsers.add_parser(
        "log",
        help="Show commit logs")
    log_parser.add_argument(
        "-c", "--compare-mode", action="store_true",
        help="Compare mode, show two branches for comparing")
    log_parser.add_argument(
        "file", metavar="<file>", nargs="?",
        help="The file to filter.")

    mergetool_parser = subparsers.add_parser(
        "mergetool",
        help="Run mergetool to resolve merge conflicts.")

    blame_parser = subparsers.add_parser(
        "blame",
        help="Show what revision and author last modified each line of a file.")
    blame_parser.add_argument(
        "--line-number", "-l",
        metavar="N", type=int,
        default=0,
        help="Goto the specify line number when opening a file.")
    blame_parser.add_argument(
        "--sha1", "-s",
        metavar="SHA-1",
        help="Blame parent commit with SHA-1.")
    blame_parser.add_argument(
        "file", metavar="<file>",
        help="The file to blame.")

    return parser.parse_args()


def _move_center(window):
    window.setGeometry(QStyle.alignedRect(
        Qt.LeftToRight, Qt.AlignCenter,
        window.size(),
        qApp.desktop().availableGeometry()))


def _do_log(app, args):
    merge_mode = args.cmd == "mergetool"
    if merge_mode and not Git.isMergeInProgress():
        QMessageBox.information(None, app.applicationName(),
                                app.translate("app", "Not in merge state, now quit!"))
        return 0

    window = app.getWindow(Application.LogWindow)
    if merge_mode:
        window.setMode(MainWindow.MergeMode)
    _move_center(window)

    if args.cmd == "log":
        # merge mode will also change to compare view
        if args.compare_mode:
            window.setMode(MainWindow.CompareMode)

        if args.file:
            window.setFilterFile(args.file)

    if window.restoreState():
        window.show()
    else:
        window.showMaximized()

    return app.exec_()


def _do_blame(app, args):
    window = app.getWindow(Application.BlameWindow)
    _move_center(window)
    window.showMaximized()

    window.blame(args.file, args.sha1, args.line_number)

    return app.exec_()


def _is_xfce4():
    keys = ["XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP"]
    for key in keys:
        if key in os.environ:
            v = os.environ[key]
            if v:
                return v == "XFCE"

    return False


def _update_scale_factor():
    if sys.platform != "linux":
        return

    # only xfce4 for the moment
    if not _is_xfce4():
        return

    xfconf_query = shutil.which("xfconf-query")
    if not xfconf_query:
        return

    def _query_conf(name):
        v = subprocess.check_output(
            [xfconf_query, "-c", "xsettings", "-p", name],
            universal_newlines=True)
        if v:
            v = v.rstrip('\n')
        return v

    if _query_conf("/Gdk/WindowScalingFactor") == "2" and \
            _query_conf("/Xft/DPI") == "96":
        os.environ["QT_SCALE_FACTOR"] = "2"


def main():
    unsetEnv(["QT_SCALE_FACTOR", "QT_AUTO_SCREEN_SCALE_FACTOR"])
    _update_scale_factor()

    args = _setup_argument(os.path.basename(sys.argv[0]))

    setAppUserId("appid.qgitc.xyz")
    app = Application(sys.argv)

    sys.excepthook = ExceptHandler

    if args.cmd == "blame":
        return _do_blame(app, args)
    else:
        return _do_log(app, args)

    return 0


if __name__ == "__main__":
    main()
