# -*- coding: utf-8 -*-

import cProfile
import pstats
import io
import os
from typing import List
import chardet


html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
}


class Commit():

    def __init__(self):

        self.sha1 = ""
        self.comments = ""
        self.author = ""
        self.authorDate = ""
        self.committer = ""
        self.committerDate = ""
        self.parents: List[str] = []
        self.children: List[str] = None
        self.repoDir: str = None
        self.subCommits: List[Commit] = []

    def __str__(self):
        return "Commit: {0}\n"  \
               "Author: {1} {2}\n"  \
               "Committer: {3} {4}\n\n"    \
               "{5}".format(self.sha1,
                            self.author, self.authorDate,
                            self.committer, self.committerDate,
                            self.comments)

    @classmethod
    def fromRawString(cls, string):
        commit = cls()

        parts = string.split("\x01")
        if len(parts) != 7:
            return commit

        commit.sha1 = parts[0]
        commit.comments = parts[1].strip("\n")
        commit.author = parts[2]
        commit.authorDate = parts[3]
        commit.committer = parts[4]
        commit.committerDate = parts[5]
        commit.parents = [x for x in parts[6].split(" ") if x]

        return commit


class MyProfile():

    def __init__(self):
        self.pr = cProfile.Profile()
        self.pr.enable()

    def __del__(self):
        self.pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(self.pr, stream=s).sort_stats("cumulative")
        ps.print_stats()
        print(s.getvalue())


class FindField():

    AddOrDel = 0
    Changes = 1
    Comments = 2
    # for highlight only
    All = 0xff

    @staticmethod
    def isDiff(field):
        return field == FindField.AddOrDel or \
            field == FindField.Changes


class FindParameter():

    def __init__(self, range, pattern, field, flag):
        self.range = range
        self.pattern = pattern
        self.field = field
        self.flag = flag

    def __eq__(self, other):
        if not other:
            return False

        if self.field != other.field:
            return False
        if self.flag != other.flag:
            return False
        if self.pattern != other.pattern:
            return False
        # ignore range compare
        return True


# refer to find type combobox
FIND_EXTACT = 0
FIND_IGNORECASE = 1
FIND_REGEXP = 2

FIND_NOTFOUND = -1
FIND_CANCELED = -2


def htmlEscape(text):
    return "".join(html_escape_table.get(c, c) for c in text)


def _fix_data(data, encoding):
    if data[0] == 0x00 and encoding == "utf-16le":
        data = data[1:]
    elif data[-1] == 0x00 and encoding == "utf-16be":
        data = data[:-1]

    return data


def decodeFileData(data, preferEncoding="utf-8"):
    if not data:
        return data.decode("utf-8"), "utf-8"

    try:
        data = _fix_data(data, preferEncoding)
        return data.decode(preferEncoding), preferEncoding
    except UnicodeDecodeError:
        pass

    encodings = ["utf-8", "gb18030", "utf16"]
    if preferEncoding in encodings:
        encodings.remove(preferEncoding)

    # try the prefer encodings first
    for e in encodings:
        try:
            data = _fix_data(data, e)
            return data.decode(e), e
        except UnicodeDecodeError:
            pass

    # try the buggy chardet
    encoding = chardet.detect(data)["encoding"]
    if encoding and encoding not in encodings:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            pass

    # the last chance
    print(b"Warning: can't decode '%s'" % data)
    return data.decode(preferEncoding, "replace"), None


def appDirPath():
    # qApp.applicationDirPath not works as expected
    path = os.path.realpath(__file__)
    return os.path.dirname(path)


def dataDirPath():
    return appDirPath() + "/data"


def isXfce4():
    keys = ["XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP"]
    for key in keys:
        if key in os.environ:
            v = os.environ[key]
            if v:
                return v == "XFCE"

    return False


def attachConsole():
    if os.name != "nt":
        return

    import ctypes
    import psutil
    import sys

    STD_OUTPUT_HANDLE = -11
    std_out_handle = ctypes.windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    if std_out_handle > 0:
        return

    try:
        # first parent must be qgitc itself
        p = psutil.Process(os.getppid()).parent()
        if ctypes.windll.kernel32.AttachConsole(p.pid):
            conout = open('CONOUT$', 'w')
            sys.stdout = conout
            sys.stderr = conout
            sys.stdin = open("CONIN$", "r")
    except:
        pass
