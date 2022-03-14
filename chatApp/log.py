# This file is based on tornado.log, with minor modifications.
#
# The Tornado project can be viewed at:
#   https://pypi.org/project/tornado/

import logging
import logging.handlers
import sys
from typing import (Dict, Any, cast, Optional, Union)

basestring_type = str
unicode_type = str

_TO_UNICODE_TYPES = (unicode_type, type(None))


def to_unicode(value: Union[None, str, bytes]) -> Optional[str]:  # noqa: F811
    """Converts a string argument to a unicode string.
    If the argument is already a unicode string or None, it is returned
    unchanged.  Otherwise it must be a byte string and is decoded as utf8.
    """
    if isinstance(value, _TO_UNICODE_TYPES):
        return value
    if not isinstance(value, bytes):
        raise TypeError("Expected bytes, unicode, or None; got %r" %
                        type(value))
    return value.decode("utf-8")


_unicode = to_unicode

try:
    import colorama  # type: ignore
except ImportError:
    colorama = None

try:
    import curses
except ImportError:
    curses = None  # type: ignore


def _stderr_supports_color() -> bool:
    try:
        if hasattr(sys.stderr, "isatty") and sys.stderr.isatty():
            if curses:
                curses.setupterm()
                if curses.tigetnum("colors") > 0:
                    return True
            elif colorama:
                if sys.stderr is getattr(colorama.initialise, "wrapped_stderr",
                                         object()):
                    return True
    except Exception:
        # Very broad exception handling because it's always better to
        # fall back to non-colored logs than to break at startup.
        pass
    return False


def _safe_unicode(s: Any) -> str:
    try:
        return _unicode(s)
    except UnicodeDecodeError:
        return repr(s)


class LogFormatter(logging.Formatter):
    """Log formatter used in Tornado.
    Key features of this formatter are:
    * Color support when logging to a terminal that supports it.
    * Timestamps on every log line.
    * Robust against str/bytes encoding problems.
    This formatter is enabled automatically by
    `tornado.options.parse_command_line` or `tornado.options.parse_config_file`
    (unless ``--logging=none`` is used).
    Color support on Windows versions that do not support ANSI color codes is
    enabled by use of the colorama__ library. Applications that wish to use
    this must first initialize colorama with a call to ``colorama.init``.
    See the colorama documentation for details.
    __ https://pypi.python.org/pypi/colorama
    .. versionchanged:: 4.5
       Added support for ``colorama``. Changed the constructor
       signature to be compatible with `logging.config.dictConfig`.
    """

    DEFAULT_FORMAT = "%(color)s[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d]%(end_color)s %(message)s"  # noqa: E501
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    DEFAULT_COLORS = {
        logging.DEBUG: 4,  # Blue
        logging.INFO: 2,  # Green
        logging.WARNING: 3,  # Yellow
        logging.ERROR: 1,  # Red
        logging.CRITICAL: 5,  # Magenta
    }

    def __init__(
        self,
        fmt: str = DEFAULT_FORMAT,
        datefmt: str = DEFAULT_DATE_FORMAT,
        style: str = "%",
        color: bool = True,
        colors: Dict[int, int] = DEFAULT_COLORS,
    ) -> None:
        r"""
        :arg bool color: Enables color support.
        :arg str fmt: Log message format.
          It will be applied to the attributes dict of log records. The
          text between ``%(color)s`` and ``%(end_color)s`` will be colored
          depending on the level if color support is on.
        :arg dict colors: color mappings from logging level to terminal color
          code
        :arg str datefmt: Datetime format.
          Used for formatting ``(asctime)`` placeholder in ``prefix_fmt``.
        .. versionchanged:: 3.2
           Added ``fmt`` and ``datefmt`` arguments.
        """
        logging.Formatter.__init__(self, fmt=fmt, datefmt=datefmt, style=style)

        self._colors = {}  # type: Dict[int, str]
        if color and _stderr_supports_color():
            if curses is not None:
                fg_color = (curses.tigetstr("setaf") or curses.tigetstr("setf")
                            or b"")

                for levelno, code in colors.items():
                    # Convert the terminal control characters from
                    # bytes to unicode strings for easier use with the
                    # logging module.
                    self._colors[levelno] = unicode_type(
                        curses.tparm(fg_color, code), "ascii")
                # color_end control characters in unicode format
                self._normal = unicode_type(curses.tigetstr("sgr0"), "ascii")
            else:
                # If curses is not present (currently we'll only get here for
                # colorama on windows), assume hard-coded ANSI color codes.
                for levelno, code in colors.items():
                    self._colors[levelno] = "\033[2;3%dm" % code
                self._normal = "\033[0m"
        else:
            self._normal = ""

    def format(self, record: Any) -> str:
        """Customize the formatting of output message

        We use the _colors, _normal, datefmt, fmt, etc constructed
        during initialization here to produce the final output.
        """
        try:
            message = record.getMessage()
            assert isinstance(message, basestring_type)  # ensured by logging
            # Encoding notes: The logging module prefers to work with character
            # strings, but only enforces that log messages are instances of
            # basestring.  In python 2, non-ascii bytestrings will make
            # their way through the logging framework until they blow up with
            # an unhelpful decoding error (with this formatter it happens
            # when we attach the prefix, but there are other opportunities for
            # exceptions further along in the framework).
            #
            # If a byte string makes it this far, convert it to unicode to
            # ensure it will make it out to the logs.  Use repr() as a fallback
            # to ensure that all byte strings can be converted successfully,
            # but don't do it by default so we don't add extra quotes to ascii
            # bytestrings.  This is a bit of a hacky place to do this, but
            # it's worth it since the encoding errors that would otherwise
            # result are so useless (and tornado is fond of using utf8-encoded
            # byte strings wherever possible).
            record.message = _safe_unicode(message)
        except Exception as e:
            record.message = "Bad message (%r): %r" % (e, record.__dict__)

        record.asctime = self.formatTime(record, cast(str, self.datefmt))

        if record.levelno in self._colors:
            record.color = self._colors[record.levelno]
            record.end_color = self._normal
        else:
            record.color = record.end_color = ""

        # %(key)s in format string gets substituted here
        formatted = self._fmt % record.__dict__

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            # exc_text contains multiple lines.  We need to _safe_unicode
            # each line separately so that non-utf8 bytes don't cause
            # all the newlines to turn into '\n'.
            lines = [formatted.rstrip()]
            lines.extend(
                _safe_unicode(ln) for ln in record.exc_text.split("\n"))
            formatted = "\n".join(lines)
        return formatted.replace("\n", "\n    ")


def setUp(loggerName: str, logLevel: int):
    # construct a Logger directly to bypass getLogger's caching
    logger = logging.Logger(loggerName)
    logger.propagate = False
    handler = logging.StreamHandler()  # by default, goes to stderr

    handler.setFormatter(LogFormatter())
    logger.addHandler(handler)
    logger.setLevel(logLevel)

    return logger


logger = setUp('chatapp', logging.INFO)
