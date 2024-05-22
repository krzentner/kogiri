import sys
import enum
import json
import time
from typing import Optional
import datetime


import noko
from noko._utils import warn_internal
from noko import ScalarTypes, is_instance_str


@noko.declare_output_engine
class NDJsonOutputEngine(noko.OutputEngine):
    """OutputEngine that outputs all tables to one file as json
    objects separated by newlines.
    Uses the standard library json module.

    The first OutputEngine to be implemented :).
    """

    def __init__(
        self,
        file: noko.FileIsh = None,
        summarize: bool = True,
        log_level: noko.LogLevelIsh = noko.TRACE,
    ):
        """
        Args:

            file (FileIsh): File to log to.
            summarize (bool): If false, does not use noko
                summarization, and instead logs the raw row with a
                bespoke, lossy JSONEncoder.
            log_level (LogLevelIsh): log level to listen to.
        """
        super().__init__(log_level=log_level)
        self.fm = noko._utils.FileManager(file)
        self.summarize = summarize

    def log_row_inner(self, row):
        if self.summarize:
            msg = row.as_summary()
        else:
            msg = row.raw.copy()
        msg.update(
            {
                "$table": row.table_name,
                "$localtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                "$utc_timestamp": datetime.datetime.utcnow().timestamp(),
                "$step": row.step,
                "$level": row.log_level,
            }
        )
        json.dump(msg, fp=self.fm.file, cls=LogEncoder)
        self.fm.file.write("\n")
        self.fm.file.flush()

    def close(self):
        self.fm.close()


class LogEncoder(json.JSONEncoder):
    """Encoder to be used as cls in json.dump.

    Is used in NDJsonOutputEngine if summarize=False.

    Args:
        args (object): Passed to super class.
        kwargs (dict): Passed to super class.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._markers = {}

    # Modules whose contents cannot be meaningfully or safelly jsonified.
    BLOCKED_MODULES = {
        "tensorflow",
        "ray",
        "itertools",
        "weakref",
    }

    def default(self, o):
        """Perform JSON encoding.

        Args:
            o (object): Object to encode.

        Raises:
            TypeError: If `o` cannot be turned into JSON even using `repr(o)`.

        Returns:
            dict or str or float or bool: Object encoded in JSON.

        """
        # This circular reference checking code was copied from the standard
        # library json implementation, but it outputs a repr'd string instead
        # of ValueError on a circular reference.
        if isinstance(o, (int, bool, float, str)):
            return o
        else:
            markerid = id(o)
            if markerid in self._markers:
                return "circular " + repr(o)
            else:
                self._markers[markerid] = o
                try:
                    return self._default_inner(o)
                finally:
                    del self._markers[markerid]

    def _default_inner(self, o):
        """Perform JSON encoding.

        Args:
            o (object): Object to encode.

        Raises:
            TypeError: If `o` cannot be turned into JSON even using `repr(o)`.
            ValueError: If raised by calling repr on an object.

        Returns:
            dict or str or float or bool: Object encoded in JSON.

        """
        # pylint: disable=method-hidden
        # pylint: disable=too-many-branches
        # pylint: disable=too-many-return-statements
        # This circular reference checking code was copied from the standard
        # library json implementation, but it outputs a repr'd string instead
        # of ValueError on a circular reference.
        try:
            return json.JSONEncoder.default(self, o)
        except TypeError:
            if isinstance(o, dict):
                data = {}
                for k, v in o.items():
                    if isinstance(k, str):
                        data[k] = self.default(v)
                    else:
                        data[repr(k)] = self.default(v)
                return data
            elif isinstance(o, type(sys)):
                return {"$module": o.__name__}
            elif type(o).__module__.split(".")[0] in self.BLOCKED_MODULES:
                return repr(o)
            elif isinstance(o, type):
                return {"$typename": o.__module__ + "." + o.__name__}
            elif is_instance_str(o, "numpy.float*"):
                # For some reason these aren't natively considered
                # serializable.
                return float(o)
            elif is_instance_str(o, "numpy.*int*"):
                return int(o)
            elif is_instance_str(o, "numpy.*bool*"):
                return bool(o)
            elif isinstance(o, enum.Enum):
                return {
                    "$enum": o.__module__ + "." + o.__class__.__name__ + "." + o.name
                }
            elif is_instance_str(o, "numpy.*"):
                # Probably an array
                return repr(o)
            elif hasattr(o, "__dict__") or hasattr(o, "__slots__"):
                obj_dict = getattr(o, "__dict__", None)
                if obj_dict is not None:
                    data = {k: self.default(v) for (k, v) in obj_dict.items()}
                else:
                    data = {s: self.default(getattr(o, s)) for s in o.__slots__}
                t = type(o)
                data["$type"] = t.__module__ + "." + t.__name__
                return data
            elif callable(o) and hasattr(o, "__name__"):
                if getattr(o, "__module__", None) is not None:
                    return {"$function": o.__module__ + "." + o.__name__}
                else:
                    return repr(o)
            else:
                try:
                    # This case handles many built-in datatypes like deques
                    return [self.default(v) for v in list(o)]
                except TypeError:
                    pass
                try:
                    # This case handles most other weird objects.
                    return repr(o)
                except TypeError:
                    pass
                return {"$unknown": None}


def load_ndjson_file(
    filename: str, keys: Optional[list[str]] = None
) -> dict[str, list[ScalarTypes]]:
    data = {}
    if keys is None:
        key_set = None
    else:
        key_set = set(keys)
    table_to_keys = {}
    parsed_lines = []
    with open(filename) as f:
        for i, line in enumerate(f.readlines()):
            try:
                row = json.loads(line)
            except ValueError as e:
                warn_internal(f"Could not load line {i} of file {filename}")
            else:
                try:
                    table = row["$table"]
                except KeyError:
                    warn_internal(f"No $table in {line!r}")
                else:
                    parsed_lines.append(row)
                    table_to_keys.setdefault(table, set()).update(row.keys())
    if len(parsed_lines) == 0:
        raise ValueError(f"Could not load any rows from {filename}")
    data = {}
    for table, keys in table_to_keys.items():
        for key in keys:
            if key_set is not None and key not in key_set:
                continue
            data[f"{table}.{key}"] = [
                obj.get(key, None)
                for obj in parsed_lines
                if obj.get("$table", None) == table
            ]
    return data


noko.LOAD_FILETYPES[".ndjson"] = load_ndjson_file
