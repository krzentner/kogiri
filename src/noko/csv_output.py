import datetime
import os
from typing import Optional, Union
import csv
import time

import noko
from noko import ScalarTypes
from noko._utils import FileManager, warn_internal


@noko.declare_output_engine
class CSVOutputEngine(noko.OutputEngine):
    """OutputEngine using the standard library csv module.

    Can handle inconsistent rows by rewriting the CSV file.
    """

    def __init__(
        self,
        runs_dir: noko.FileIsh,
        run_name: str,
        log_level=noko.TRACE,
    ):
        super().__init__(log_level=log_level)
        self.runs_dir = os.path.abspath(runs_dir)
        self.run_name = run_name
        self.writers = {}

    def log_row_inner(self, row: noko.Row):
        msg = row.as_summary()
        msg.update(
            {
                "$localtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                "$utc_timestamp": datetime.datetime.utcnow().timestamp(),
                "$step": row.step,
                "$level": row.log_level,
            }
        )
        if row.table_name in self.writers:
            f, writer = self.writers[row.table_name]
        else:
            f_name = os.path.join(self.runs_dir, self.run_name, f"{row.table_name}.csv")
            f = FileManager(f_name)
            f.should_close = True
            writer = csv.DictWriter(f.file, fieldnames=sorted(msg.keys()))
            writer.writeheader()
            self.writers[row.table_name] = (f, writer)
        f, writer, msg = _handle_inconsistent_rows(row.table_name, f, writer, msg)
        self.writers[row.table_name] = (f, writer)
        writer.writerow(msg)
        f.file.flush()

    def close(self):
        for f, writers in self.writers.values():
            f.close()


def _handle_inconsistent_rows(
    table_name: str,
    f: FileManager,
    writer: csv.DictWriter,
    msg: dict[str, ScalarTypes],
) -> tuple[FileManager, csv.DictWriter, dict[str, ScalarTypes]]:
    # Fill missing keys with None
    for k in writer.fieldnames:
        if k not in msg:
            msg[k] = None
    msg = dict(sorted(msg.items()))
    # Check for new keys
    new_keys = []
    for k in msg.keys():
        if k not in writer.fieldnames:
            new_keys.append(k)
    if len(new_keys) > 0:
        if len(new_keys) == 1:
            warn_internal(f"Adding new key {new_keys[0]!r} to table {table_name!r}")
        elif len(new_keys) <= 3:
            new_keys_msg = ",".join([repr(k) for k in new_keys])
            warn_internal(
                f"Adding {len(new_keys)} new keys [{new_keys_msg}] to table {table_name!r}"
            )
        else:
            new_keys_msg = ",".join([repr(k) for k in new_keys[:3]])
            warn_internal(
                f"Adding {len(new_keys)} new keys [{new_keys_msg},...] to table {table_name!r}"
            )
        temp_f_name = f"{f.filename}.tmp"
        with open(temp_f_name, "w") as out_f, open(f.filename) as in_f:
            w = csv.DictWriter(out_f, sorted(msg.keys()))
            w.writeheader()
            for r in csv.DictReader(in_f):
                for k in msg.keys():
                    r.setdefault(k, None)
                w.writerow(r)
        f_name = f.filename
        f.close()
        os.replace(temp_f_name, f_name)
        f = FileManager(f_name)
        writer = csv.DictWriter(f.file, sorted(msg.keys()))
    return f, writer, msg


def _try_convert(s: str) -> Union[str, float]:
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        pass
    return s


def load_csv_file(
    filename: str, keys: Optional[list[str]] = None
) -> dict[str, list[ScalarTypes]]:
    with open(filename) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if keys is None:
        keys = list(rows[0].keys())
    return {k: [_try_convert(row[k]) for row in rows] for k in keys}


noko.LOAD_FILETYPES[".csv"] = load_csv_file
