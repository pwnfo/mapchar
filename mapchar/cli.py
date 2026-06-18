import re
import sys
import termios
import tty
from argparse import Namespace
from logging import ERROR
from typing import Any

from mapchar import __description__, __version__
from mapchar.args import create_parser
from mapchar.compression import (
    COMPRESSION_LEVEL_RANGES,
)
from mapchar.exceptions import InvalidSyntaxError
from mapchar.file_parser import process_expr_file
from mapchar.generator import ExprError, MapcharGenerator
from mapchar.logger import log
from mapchar.runner import GenerateOptions, generate
from mapchar.utils.formatters import format_size, parse_size


def pause(prompt: str = " \u203a Press Enter to start") -> bool:
    """Pause execution and wait for user input in terminal."""

    # ignores if interactive prompt is not supported
    if not sys.stdin.isatty():
        return True

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        sys.stderr.write(prompt)
        sys.stderr.flush()

        tty.setraw(fd)

        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                break
            elif ch == "\x03":
                raise KeyboardInterrupt

        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

        return True

    except KeyboardInterrupt:
        sys.stderr.write("\r\n")
        sys.stderr.flush()
        return False

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def format_expression(expression: str, files: list[str]) -> tuple[str, list[str]]:
    """Returns the expression with the list of files for word generation."""
    files_out: list[str] = []

    for file_path in files:
        # replaces inline inclusions (starting with "//")
        # example: mapchar '/d^' '//[2-5]/d' -> '/d[2-5]/d'
        if file_path.startswith("//"):
            inline = file_path.replace("//", "", 1)

            expression = re.sub(
                r"(?<!\\)\^",
                lambda m: inline,  # noqa: B023
                expression,
                count=1,
            )
        else:
            files_out.append(file_path)

    return expression, files_out


def print_stats(
    generator: MapcharGenerator,
    nodes: list[list[Any]],
    tokens: list[list[Any]],
    args: Namespace,
) -> int:
    """Displays detailed pattern statistics."""
    delim_len = len(args.delimiter.encode("utf-8"))

    try:
        s_bytes, s_words = generator.stats(
            nodes, delimiter_len=delim_len, start_token=args.start, end_token=args.end
        )
        u_bytes, u_words = generator.stats(nodes, delimiter_len=delim_len)
    except ExprError as e:
        log.error(e)
        return 1

    total_tokens = sum(len(t) for t in tokens)
    total_nodes = sum(len(n) for n in nodes)
    avg_len = u_bytes / u_words if u_words > 0 else 0

    log.info("Pattern Statistics")

    stats_list = [
        ("Expressions", len(nodes)),
        ("Total Tokens", total_tokens),
        ("Total Nodes", total_nodes),
        ("Delimiter", f"{args.delimiter!r} ({delim_len} bytes)"),
        ("Average Length", f"{avg_len - delim_len:.2f} chars"),
    ]

    for label, value in stats_list:
        log.info(f"  {label:.<20} {value}")

    if args.start or args.end:
        log.info("\nRange Filtering")
        ps_words = (s_words / u_words) * 100 if u_words > 0 else 0
        pu_words = 100 - ps_words
        range_list = [
            ("Start Word", args.start or "<None>"),
            ("End Word", args.end or "<None>"),
            ("Filtered Words", f"{s_words:,} ({ps_words:.2f}%)"),
            ("Ignored Words", f"{u_words - s_words:,} ({pu_words:.2f}%)"),
        ]
        for label, value in range_list:
            log.info(f"  {label:.<20} {value}")

    log.info("\nFinal Result")
    try:
        log.info(f"  Entries to generate: {s_words}")
        log.info(
            f"  Estimated size:      {format_size(s_bytes, d=2)} ({s_bytes} bytes)"
        )
    except (OverflowError, ValueError):
        log.info("  <OverflowError>")
        return 1

    return 0


def print_info(s_words: int, s_bytes: int, compressor: None | str = None) -> None:
    """Displays generation statistics and information before execution."""
    estimated_size = format_size(s_bytes, d=2)

    log.info(
        f"Entries to generate: {s_words:,} "
        + (
            f"({estimated_size}"
            if compressor is None
            else f"({estimated_size} uncompressed, {compressor}"
        )
        + ")."
    )


def main() -> int:
    """Main entry point for the Mapchar CLI. Returns the exit status code."""
    parser = create_parser()
    args = parser.parse_args()

    sys.setrecursionlimit(4000)

    if args.pattern is None and args.expr_file is None:
        parser.print_help(sys.stderr)
        return 1

    if args.expr_file is not None and args.pattern is not None:
        log.error(
            "specify only one of the following: pattern or expression file (-f/--file)."
        )
        return 1

    if not (1 <= args.workers <= 64):
        log.error(
            f"invalid number of workers ({args.workers}). choose a value between 1 and 64."
        )
        return 1

    compresslevel = args.compresslevel
    if args.compress is not None:
        if compresslevel is not None:
            min_level, max_level = COMPRESSION_LEVEL_RANGES[args.compress]

            if not (min_level <= compresslevel <= max_level):
                log.error(f"{args.compress}: level must be {min_level}-{max_level}.")
                return 1

    elif compresslevel is not None:
        log.error("compression level (-l/--compresslevel) requires -z/--compress.")
        return 1

    if args.quiet:
        log.setLevel(ERROR)

    buffer_size = args.buffer

    if isinstance(buffer_size, str):
        try:
            buffer_size = parse_size(buffer_size)
            if buffer_size < 1:
                raise ValueError("unbuffered mode is not supported.")
        except ValueError as e:
            log.error(f"invalid buffer size: {e}")
            return 1

    if args.compress and args.output is None:
        log.error("compression requires -o/--output to specify an output file.")
        return 1

    try:
        flush_limit = parse_size(args.flush)
    except ValueError as e:
        log.error(f"invalid flush size: {e}")
        return 1

    gen_options = GenerateOptions(
        filename=args.output,
        buffering=buffer_size,
        quiet_mode=args.quiet,
        delimiter=args.delimiter,
        wrange=(args.start, args.end),
        threads=args.workers,
        compression=args.compress,
        flush_limit=flush_limit,
        compresslevel=compresslevel,
    )

    generator = MapcharGenerator()

    nodes: list[list[Any]] = []
    tokens_list: list[list[Any]] = []

    if args.expr_file is not None:
        try:
            for d in process_expr_file(args.expr_file):
                if d is None:
                    return 1

                expression, expr_files = d

                try:
                    t = generator.tokenize(expression)
                    n = generator.parse(t, files=(expr_files or None))
                    tokens_list.extend(t)
                    nodes.extend(n)
                except ExprError as e:
                    log.error(e)
                    return 1

        except InvalidSyntaxError as e:
            log.error(e)
            return 1

        if not nodes:
            return 0
    else:
        expression, proc_files = format_expression(args.pattern, args.files)

        try:
            tokens_list = generator.tokenize(expression)
            nodes = generator.parse(tokens_list, files=(proc_files or None))
        except ExprError as e:
            log.error(e)
            return 1

    if args.stats:
        return print_stats(generator, nodes, tokens_list, args)

    log.info(f"Mapchar v{__version__} [by Pwnfo]\n{__description__}\n")

    try:
        s_bytes, s_words = generator.stats(
            nodes,
            delimiter_len=len(args.delimiter.encode("utf-8")),
            start_token=args.start,
            end_token=args.end,
        )
    except ExprError as e:
        log.error(e)
        return 1

    print_info(s_words, s_bytes, compressor=args.compress)

    if not (args.quiet or args.non_interactive) and not pause():
        return 0

    try:
        return generate(generator, nodes, (s_bytes, s_words), gen_options)
    except KeyboardInterrupt:
        log.error("Unexpected keyboard interruption!")
    finally:
        if not args.quiet:
            sys.stdout.write("\033[?25h")  # fix cursor bug

    return 1
