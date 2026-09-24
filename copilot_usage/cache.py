"""Parsed sources keyed by path, reused until the file's mtime or size changes."""
import os

entries = {}


def file_stamp(path):
    try:
        stat = os.stat(path)
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def version():
    return str(hash(tuple(sorted((path, stamp) for path, (stamp, _) in entries.items()))))
