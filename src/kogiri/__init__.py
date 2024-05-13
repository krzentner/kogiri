"""
.. include:: ../../README.md
"""
import os
import sys
import io
import inspect
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any, Callable, Literal, Union, Optional
import fnmatch
import functools
import datetime
import logging
import enum
import pathlib
import warnings

import kogiri
from kogiri._utils import warn_internal


def log_row(
    table: Optional[Union[str, dict, "Row"]] = None,
    row: Optional[Union[dict, "Row"]] = None,
    step: Optional[int] = None,
    level: Optional[Union[int, "NamedLevel", "LogLevels"]] = None,
):
    """Primary logging entrypoint.

    Will deduce any non-provided arguments.

    If a `Row` object is provided, it contains all required fields
    and will be passed to `Logger.log_row`, with arguments
    overriding the row fields if provided.

    If the first argument is a str, it becomes the table name.
    If the first argument is not a str or `Row`, the table name is
    derived from the calling file and line number.

    If the row is not provided, locals from the calling function will be
    logged.

    `log_level` defaults to `INFO` (log level 10), which is also the
    default value for most output engines.

    `step` determines the "X axis" of the logged data. If not provided it will
    automatically be incremented every call with the same table.

    If `init()` or `init_extra()` has not been called
    before this function, `init()` will be called with no
    arguments

    Examples:

    ```python
    # Will log all local variables at log level INFO
    log_row()

    # Will log all local variables at log level INFO to table called 'grad_step'
    log_row('grad_step')

    # Will log into table based on current file and line number at log level INFO
    log_row({'x': x})
    ```
    """

    if level is None:
        level = INFO
    level = int(level)
    logger = get_logger()

    # Most of this function is magic to figure out how to produce a Row object
    # based on minimal arguments.

    # Special case only a row-like passed in as the first argument
    # e.g. log({'x': x}) or log(Row('grad_step', {'x': x}))
    if isinstance(table, (dict, Row)) and row is None and step is None:
        row = table
        table = None

    # Check all the types
    if table is not None:
        assert isinstance(table, str)
    if row is not None and not isinstance(row, (dict, Row)):
        raise ValueError(
            f"Unsupported row type {type(row)}. " "Use a dictionary or kogiri.Row."
        )
    if step is not None:
        assert isinstance(step, int)

    # Check what we have
    if isinstance(row, Row):
        if level is not None:
            row = replace(row, log_level=level)
        # We have a row, so we won't need to guess any info
        # Arguments might still override parts of the Row object
        # e.g. log(Row('grad_step', {'x': x}), table='grad_step2')
        # e.g. log(Row('grad_step', {'x': x}), step=0)
        if table is None and step is None:
            # Case 1: We have a row, just log it
            logger.log_row(row=row)
        elif isinstance(table, str) and step is None:
            # Case 2: User provided the table and not a step, recompute the step
            step = logger.get_default_step(table)
            logger.log_row(replace(row, table_name=table, step=step))
        elif isinstance(table, str) and isinstance(step, int):
            # Case 3: User provided the table and step
            logger.log_row(replace(row, table_name=table, step=step))
    elif isinstance(table, str) and isinstance(row, dict):
        # No inspecting required, just need to figure out the step
        # e.g. log('grad_step', {'x': x})
        if step is None:
            step = logger.get_default_step(table)
        logger.log_row(Row(raw=row, table_name=table, step=step, log_level=level))
    else:
        # We do not have a Row, row is either a dict or None
        # We need to figure out either our table name or row contents using
        # inspect.
        # e.g. log({'x': x}) or log() or log(table='x')
        stack = inspect.stack()
        frame_info = stack[1]
        if table is None:
            table = logger.get_unique_table(frame_info.filename, frame_info.lineno)
        if step is None:
            step = logger.get_default_step(table)
        if row is None:
            row = frame_info.frame.f_locals
        logger.log_row(Row(raw=row, table_name=table, step=step, log_level=level))


# Keep these this list and type synchronized
_ScalarTypeTuple = (type(None), str, float, int, bool)
ScalarTypes = Union[type(None), str, float, int, bool]
Summary = dict[str, Union[None, str, float, int, bool]]


def load_log_file(
    filename: str, keys: Optional[list[str]] = None
) -> dict[str, list[ScalarTypes]]:
    """Load a log file based on its file extension.

    If keys are provided, only those keys will be loaded.

    Returns a dictionary of keys to the scalar values of those keys.
    The "$step" key contains the step values provided to log_row().
    """
    # Import the json output engine, since it has no external deps
    import kogiri.ndjson_output
    import kogiri.csv_output

    _, ext = os.path.splitext(filename)
    if ext in LOAD_FILETYPES:
        return LOAD_FILETYPES[ext](filename, keys)
    else:
        raise ValueError(
            f"Unknown filetype {ext}. Perhaps you need to load "
            "a kogiri backend or use one of the well known log "
            "types (.ndjson or .csv)"
        )


LOAD_FILETYPES: dict[
    str, Callable[[str, Optional[list[str]]], dict[str, list[ScalarTypes]]]
] = {}
"""Functions for loading different filetypes.

Maps from extension (with a leading ".") to a function with the same API as load_log_file().
"""

_INIT_CALLED = False

LOG_LEVELS = {}
"""Contains all log levels created with NamedLevel.register."""


@dataclass(eq=False, order=False, frozen=True)
@functools.total_ordering
class NamedLevel:
    """An extensible way of naming a log level.

    You can use this to name your own log levels :)
    """

    name: str
    val: int

    def __eq__(self, other):
        return self.val == other

    def __lt__(self, other):
        return self.val < other

    def __repr__(self):
        return f"NamedLevel({self.name}, {self.val})"

    def __hash__(self):
        return hash(self.val)

    def __int__(self):
        return self.val

    def __str__(self):
        return self.name

    @classmethod
    def register(cls, name, val):
        log_level = cls(name, val)
        assert name not in LOG_LEVELS
        LOG_LEVELS[name] = log_level
        logging.addLevelName(val, name)
        return log_level


@functools.total_ordering
class LogLevels(enum.Enum):
    """An enum of named log levels."""

    TRACE = NamedLevel.register("TRACE", 5)
    """Used for extremely noisy logging when doing detailed
    debugging.
    """

    RESULTS = NamedLevel.register("RESULTS", 35)
    """Log level for important results. Usually the appropriate
    logging level to print to stdout.
    """

    # These have the same value as the standard library logging levels
    DEBUG = NamedLevel.register("DEBUG", 10)
    INFO = NamedLevel.register("INFO", 20)
    WARNING = NamedLevel.register("WARNING", 30)
    ERROR = NamedLevel.register("ERROR", 40)
    CRITICAL = NamedLevel.register("CRITICAL", 50)

    def __int__(self):
        return int(self.value)

    def __lt__(self, other):
        return int(self) < int(other)


TRACE: LogLevels = LogLevels.TRACE
RESULTS: LogLevels = LogLevels.RESULTS
DEBUG: LogLevels = LogLevels.DEBUG
INFO: LogLevels = LogLevels.INFO
WARNING: LogLevels = LogLevels.WARNING
ERROR: LogLevels = LogLevels.ERROR
CRITICAL: LogLevels = LogLevels.CRITICAL

LogLevelIsh = Union[int, NamedLevel, LogLevels]
PathIsh = Union[str, bytes, pathlib.Path]
FileIsh = Union[None, PathIsh, io.TextIOWrapper]


def init(
    runs_dir: str = "runs",
    run_name: Optional[str] = None,
    stderr_log_level: LogLevelIsh = WARNING,
    tb_log_level: LogLevelIsh = INFO,
    tb_log_hparams: bool = False,
    setup_py_logging: bool = True,
) -> str:
    """Initializes a logger in `{runs_dir}/{run_name}` with default backends.

    Run name will default to the main file and current time in ISO 8601 format.
    """
    global _LOGGER
    if run_name is None:
        run_name = _default_run_name()
        if os.path.exists(run_name):
            raise ValueError(
                "Could not create a unique default run name. "
                "Most likely two runs began at the same time."
            )

    run_dir = os.path.abspath(os.path.join(runs_dir, run_name))
    if setup_py_logging:
        _setup_py_logging(run_dir, stderr_log_level)

    global _INIT_CALLED
    if _INIT_CALLED:
        warn_internal(
            "kogiri.init() already called in this process. Most "
            "likely kogiri.log_row() was called before "
            "kogiri.init()."
        )
        return run_dir
    _INIT_CALLED = True

    if _LOGGER is not None:
        warn_internal("logger was already present before kogiri.init() was called")
    from kogiri.ndjson_output import NDJsonOutputEngine
    from kogiri.csv_output import CSVOutputEngine
    from kogiri.pprint_output import PPrintOutputEngine
    from kogiri.tb_output import TensorBoardOutput

    logger = Logger(runs_dir=runs_dir, run_name=run_name)
    logger.add_output(NDJsonOutputEngine(f"{runs_dir}/{run_name}/kogiri.ndjson"))
    logger.add_output(CSVOutputEngine(runs_dir, run_name))
    try:
        logger.add_output(
            TensorBoardOutput(
                runs_dir, run_name, log_level=tb_log_level, log_hparams=tb_log_hparams
            )
        )
    except ImportError:
        warn_internal("tensorboard API not installed")

    logger.add_output(
        PPrintOutputEngine(file=f"{runs_dir}/{run_name}/kogiri_pprint.log")
    )

    # Imported for side effects
    if "torch" in sys.modules:
        import kogiri.torch
    if "numpy" in sys.modules:
        import kogiri.np

    _LOGGER = logger
    return run_dir


_INIT_EXTRA_CALLED = False


def init_extra(
    runs_dir: str = "runs",
    run_name: Optional[str] = None,
    config: dict[str, Any] = None,
    wandb_kwargs: Optional[dict[str, Any]] = None,
    init_wandb: bool = False,
    seed_all: Union[bool, Literal["if_present"]] = "if_present",
    create_git_checkpoint: bool = True,
    stderr_log_level: LogLevelIsh = WARNING,
    tb_log_level: LogLevelIsh = INFO,
    tb_log_hparams: bool = False,
) -> str:
    """Initializes a logger in `{runs_dir}/{run_name}` with default backends.

    Run name will default to the main file and current time in ISO 8601 format.

    Initializes kogiri logging, including all optional
    features.

    `config` should be configuration / hyperparameter options. They
    will be logged to wandb if `init_wandb` is True, and logged to
    tensorboard if `tb_log_hparams` is True.

    `seed_all`: If True of "if_present", will seed all libraries
    using `config['seed']`. If you would like to seed manually
    with another value, you can call `kogiri.seed_all_imported_modules()`

    If `create_git_checkpoint` is True, creates a git commit on a
    branch named `kogiri-checkpoints`, and generates diffs using
    that commit using `kogiri.kogiri_git.checkpoint_repo()`.
    """
    run_dir = init(runs_dir, run_name, stderr_log_level, tb_log_level, tb_log_hparams)
    logging.getLogger("kogiri").log(level=int(RESULTS), msg=f"Logging to: {run_dir}")
    global _INIT_EXTRA_CALLED
    if _INIT_EXTRA_CALLED:
        return run_dir
    _INIT_EXTRA_CALLED = True

    if config is None:
        config = {}

    if isinstance(config, dict):
        config_as_dict = config
    else:
        config_as_dict = config.__dict__

    if init_wandb:
        try:
            import wandb
        except ImportError:
            warn_internal("could not import wandb")
            pass
        else:
            if wandb_kwargs is None:
                wandb_kwargs = {}
            wandb_kwargs.setdefault("sync_tensorboard", True)
            wandb_kwargs.setdefault("config", config)
            wandb.init(**wandb_kwargs)

    if create_git_checkpoint:
        try:
            import kogiri.kogiri_git

            kogiri.kogiri_git.checkpoint_repo(run_dir)
        except ImportError:
            warn_internal("could not import git, repo was not checkpointed")

    if seed_all:
        assert seed_all is True or seed_all == "if_present"
        MISSING = object()
        seed = MISSING
        try:
            seed = config_as_dict["seed"]
        except KeyError:
            pass
        if seed is not None and seed is not MISSING:
            try:
                seed = int(seed)
            except ValueError:
                warn_internal(f"Could not convert seed {seed!r} to int")
            else:
                seed_all_imported_modules(seed)
        elif seed_all is True:
            # We were told to seed, and could not
            raise ValueError(
                "Explicitly asked to seed, " "but seed is not present in config"
            )
    return run_dir


def _default_run_name():
    main_file = getattr(sys.modules.get("__main__"), "__file__", "interactive")
    file_trail = os.path.splitext(os.path.basename(main_file))[0]
    now = datetime.datetime.now().isoformat()
    return f"{file_trail}_{now}"


def _setup_py_logging(run_dir, stderr_log_level: LogLevelIsh = WARNING):
    os.makedirs(run_dir, exist_ok=True)
    FORMAT = "%(asctime)s %(name)s [%(levelname)-8.8s]: %(message)s"
    rootLogger = logging.getLogger()
    rootLogger.setLevel(0)
    formatter = logging.Formatter(FORMAT, "%Y-%m-%d %H:%M:%S")

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(int(stderr_log_level))
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(filename=os.path.join(run_dir, "debug.log"))
    file_handler.setFormatter(formatter)
    file_handler.setLevel(int(TRACE))

    rootLogger.addHandler(file_handler)
    rootLogger.addHandler(stream_handler)

    warnings_logger = logging.getLogger("py.warnings")
    warnings_logger.addHandler(stream_handler)
    warnings_logger.addHandler(file_handler)


def seed_all_imported_modules(seed: int, make_deterministic: bool = True):
    """Seed all common numerical libraries (random, numpy, torch,
    and tensorflow).

    This function will be called by `init_extra()` if a seed is
    present in the provided config.
    """
    import random

    random.seed(seed)

    if "numpy" in sys.modules:
        try:
            import numpy as np
        except ImportError:
            pass
        else:
            np.random.seed(seed)

    if "torch" in sys.modules:
        try:
            import torch
        except ImportError:
            pass
        else:
            torch.manual_seed(seed)
            torch.cuda.manual_seed(seed)
            if make_deterministic:
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False

    if "tensorflow" in sys.modules:
        try:
            import tensorflow as tf
        except ImportError:
            pass
        else:
            tf.random.set_seed(seed)
            tf.experimental.numpy.random.seed(seed)
            tf.set_random_seed(seed)
            if make_deterministic:
                os.environ["TF_CUDNN_DETERMINISTIC"] = "1"
                os.environ["TF_DETERMINISTIC_OPS"] = "1"

    os.environ["PYTHONHASHSEED"] = str(seed)


_LOGGER = None


def get_logger() -> "Logger":
    """Returns the global logger, calling kogiri.init() if
    necessary.
    """
    if _LOGGER is None:
        init()
    assert _LOGGER is not None
    return _LOGGER


def add_output(output_engine):
    """Adds an output to the global logger, calling kogiri.init() if
    necessary.
    """

    get_logger().add_output(output_engine)


SUMMARIZERS: dict[str, Callable[[Any, str, Summary], None]] = {}
"""Registered summarizers.

Use declare_summarizer to add a summarizer to this dictionary.
"""

_KOGIRI_SUMMARIZE = "kogiri_summarize"


def declare_summarizer(type_description: Union[str, type], monkey_patch: bool = True):
    if isinstance(type_description, str):
        type_str = type_description
    elif isinstance(type_description, type):
        type_str = f"{type_description.__module__}.{type_description.__name__}"
    else:
        raise ValueError("Need to pass type name to declare_summarizer")

    def decorator(processor):
        if type_str in SUMMARIZERS:
            # Use warnings here instead of warn_internal since the
            # logger has not been set up at import time.
            warnings.warn(f"{type_str!r} already had a registered summarizer.")
        SUMMARIZERS[type_str] = processor

        if monkey_patch:
            # Try to monkey-patch _KOGIRI_SUMMARIZE method onto type
            parts = type_str.split(".")
            try:
                obj = sys.modules[parts[0]]
                for p in parts[1:]:
                    obj = getattr(obj, p, None)
                setattr(obj, _KOGIRI_SUMMARIZE, processor)
            except (KeyError, AttributeError, TypeError) as ex:
                warnings.warn(
                    f"Coudld not money-patch processor to type {type_str!r}: {ex}"
                )

        return processor

    return decorator


def _type_string(obj):
    return f"{type(obj).__module__}.{type(obj).__name__}"


def is_instance_str(obj, type_names):
    """An isinstance check that does not require importing the type's module."""
    obj_type_str = _type_string(obj)
    if isinstance(type_names, str):
        return fnmatch.fnmatch(obj_type_str, type_names)
    else:
        for type_name in type_names:
            if fnmatch.fnmatch(obj_type_str, type_name):
                return True
        return False


def summarize(src: Any, prefix: str, dst: Summary):
    """Lossfully summarize a value."""
    if prefix == "_":
        return
    if isinstance(src, _ScalarTypeTuple):
        key = prefix
        i = 1
        while key in dst:
            key = f"{prefix}_{i}"
            i += 1
        dst[key] = src
    elif isinstance(src, dict):
        for k, v in src.items():
            if isinstance(k, int):
                continue
            # Since we often log locals, there's likely a `self` variable.
            # Replace the `self` key with the type name of the self, since
            # that's more informative.
            if k == "self":
                k = type(v).__name__
            try:
                if prefix:
                    flat_k = f"{prefix}/{k}"
                else:
                    flat_k = k
            except ValueError:
                pass
            else:
                summarize(v, flat_k, dst)
    elif isinstance(src, (list, tuple)):
        for i, v in enumerate(src):
            flat_k = f"{prefix}[{i}]"
            summarize(v, prefix, dst)
    else:
        summarizer = SUMMARIZERS.get(_type_string(src), None)
        if summarizer is not None:
            summarizer(src, prefix, dst)
        else:
            summarizer = getattr(src, _KOGIRI_SUMMARIZE, None)
            if summarizer is not None:
                summarizer(prefix, dst)


@dataclass
class Row:
    """A row of data. The fundamental unit of logging in kogiri."""

    table_name: str
    """The name of the table this row should be logged to."""

    raw: Any
    """The raw data to log. Will be summarized before logging."""

    # "Should" be monotonically increasing, but not necessarily sequential
    step: int
    """A (usually monotonically increasing) step.

    Sets the "default x-axis" in plotting.
    """

    # If someone is manually creating a Row, probably default to INFO (the
    # default logging level)
    log_level: LogLevelIsh = INFO
    """Log level to log at."""

    def as_summary(self) -> Summary:
        """Convert the row to a Summary.

        Cached, but only computed if this method is called.
        This avoid the overhead of summarizing if no OutputEngine
        is listening on this log level.
        """
        summarized = getattr(self, "summarized", None)
        if summarized is None:
            summarized = {}
            summarize(self.raw, "", summarized)
            self.summarized = summarized
        # Make a shallow copy
        return dict(summarized)


class Logger:
    """Main container of kogiri state.

    Contains all instantiated OutputEngines, as well as stateful
    table default values (step, name of tables based on callsite).
    """

    def __init__(self, runs_dir, run_name):
        self.runs_dir = runs_dir
        self.run_name = run_name
        self.fileloc_to_tables: dict[tuple[str, int], str] = {}
        self.tables_to_fileloc: dict[str, tuple[str, int]] = {}
        self.table_to_default_step: defaultdict[str, int] = defaultdict(int)
        self._output_engines: defaultdict[str, list[OutputEngine]] = defaultdict(list)
        self._closed = False

    @property
    def all_output_engines(self):
        return [
            engine for engines in self._output_engines.values() for engine in engines
        ]

    def get_unique_table(self, filename: str, lineno: int) -> str:
        """Get a unique table name given the filename and line
        number. Used when no table name is provided to
        kogiri.log_row().
        """
        fileloc = (filename, lineno)
        try:
            return self.fileloc_to_tables[fileloc]
        except KeyError:
            pass
        parts = kogiri._utils.splitall(filename)
        for i in range(1, len(parts)):
            if i == 0:
                table = parts[-1]
            else:
                table = os.path.join(*parts[-i:])
                table = f"{table}:{lineno}"
            if table not in self.tables_to_fileloc:
                self.tables_to_fileloc[table] = fileloc
                self.fileloc_to_tables[fileloc] = table
                return table
        return f"{filename}:{lineno}"

    def get_default_step(self, table: str) -> int:
        step = self.table_to_default_step[table]
        self.table_to_default_step[table] += 1
        return step

    def log_row(self, row: Row) -> bool:
        """Logs a row to all `OutputEngine`s (will filter on log
        level).

        Convenience features (like default table name, and logging
        a dictionary) are only available via kogiri.log_row().

        Returns:

            true if any output engine logged the table.
        """
        logged_anywhere = False
        for output in self.all_output_engines:
            logged_anywhere |= output.log_row(row)
        if not logged_anywhere:
            warn_internal(
                f"Log to table {row.table_name!r} was too low level for any logger output."
            )
        return logged_anywhere

    def close(self):
        """Close all `OutputEngine`s."""
        assert not self._closed
        for output in self.all_output_engines:
            output.close()
        self._closed = True

    def add_output(self, output: "OutputEngine"):
        self._output_engines[type(output).__name__].append(output)


class OutputEngine:
    """Base class of all output engines.

    You should also apply the @declare_output_engine decorator to
    any subclasses you create.
    """

    def __init__(self, log_level: LogLevelIsh):
        self.log_level: LogLevelIsh = log_level

    def log_row(self, row: Row):
        """External method to call to log a row."""
        # This int() conversion is important!
        if int(row.log_level) >= int(self.log_level):
            self.log_row_inner(row)
            return True
        else:
            return False

    def log_row_inner(self, row: Row):
        """Method to override for implementing logging."""
        del row
        raise NotImplementedError()

    def close(self):
        """Cleanup any necessary resources.
        Unforunately not gauranteed to be called if python crashes.
        """
        pass


OUTPUT_ENGINES: dict[str, type[OutputEngine]] = {}
"""Output engine classes that have been declared using
declare_output_engine.
"""


def declare_output_engine(output_engine_type: type):
    """This decorator basically just serves as notice that the
    output's type name is part of its interface.
    """
    assert issubclass(output_engine_type, OutputEngine)
    OUTPUT_ENGINES[output_engine_type.__name__] = output_engine_type
    return output_engine_type


__all__ = [
    "log_row",
    "load_log_file",
    "LOAD_FILETYPES",
    "LOG_LEVELS",
    "NamedLevel",
    "LogLevels",
    "TRACE",
    "RESULTS",
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
    "init",
    "init_extra",
    "seed_all_imported_modules",
    "add_output",
    "declare_summarizer",
    "summarize",
    "Row",
    "OutputEngine",
    "OUTPUT_ENGINES",
    "declare_output_engine",
]
