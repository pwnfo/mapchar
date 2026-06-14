import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO, Any

from mapchar.compression import (
    CompressionFormat,
    compressed_file_writer,
    ensure_compression_extension,
)
from mapchar.logger import log


@contextmanager
def mapchar_open(
    file: str | None,
    *args: Any,
    compression: CompressionFormat | None = None,
    compresslevel: int | None = None,
    **kwargs: Any,
) -> Iterator[IO[Any] | None]:
    """
    Context manager for opening files with optional compression.

    Opens files for output with support for compression formats ("gzip", "bzip2", "lzma").
    If no file is specified, returns `sys.stdout`. Handles errors gracefully.
    Returns `None` only if an error occurs.
    """
    fp: Any = None

    try:
        if file is None:
            yield sys.stdout
            return

        if compression is not None:
            file = ensure_compression_extension(compression, file)

            with compressed_file_writer(
                file, compression, compresslevel=compresslevel
            ) as fp:
                yield fp
            return

        fp = open(file, *args, **kwargs)
        yield fp
    except FileNotFoundError:
        log.error(f"file {file!r} not found.")
        yield None
    except PermissionError:
        log.error(f"no permission for {file!r}.")
        yield None
    except IsADirectoryError:
        log.error(f"{file!r} is a directory.")
        yield None
    except FileExistsError:
        log.error(f"{file!r} already exists.")
        yield None
    except Exception:
        log.exception(f"unexpected error while opening {file!r}")
        yield None
    finally:
        if fp is not None:
            fp.close()
