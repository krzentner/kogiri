import datetime
import re
import os
from typing import Optional

import pyarrow as pa
import pyarrow.fs
import pyarrow.csv
import pyarrow.parquet

import noko

ALL_FILETYPES = [".csv", ".parquet"]
DEFAULT_FILETYPES = [".csv", ".parquet"]


@noko.declare_output_engine
class ArrowOutputEngine(noko.OutputEngine):
    """OutputEngine using pyarrow to write to parquet (and
    optinally csv) files.
    Probably the fastest output engine, although a significant
    portion of noko runtime is spent in summarization.

    Does not currently support tables changing keys during
    logging.
    """

    def __init__(
        self,
        runs_dir: noko.FileIsh,
        run_name: str,
        filetypes=DEFAULT_FILETYPES,
        log_level=noko.TRACE,
    ):
        # The arrow backend is relatively efficient, so default to TRACE level.

        super().__init__(log_level=log_level)

        # Convert non-uri paths to absolute paths
        if not re.match(r"^[a-z0-9]+://", runs_dir):
            runs_dir = os.path.abspath(runs_dir)

        self.base_uri = runs_dir

        self.fs, self.base_path = pa.fs.FileSystem.from_uri(runs_dir)
        self.fs.create_dir(self.base_path)
        self.filetypes = filetypes
        self.run_name = run_name

        self.writers = {}

    def log_row_inner(self, row):
        msg = row.as_summary()
        msg["$step"] = row.step
        msg["$utc_timestamp"] = datetime.datetime.utcnow().timestamp()
        msg["$level"] = int(row.log_level)
        msg = dict(sorted(msg.items()))

        record = pa.RecordBatch.from_pylist([msg])

        schema = record.schema

        if row.table_name not in self.writers:
            self.writers[row.table_name] = {
                ext: self._create_writer(row.table_name, ext, schema)
                for ext in self.filetypes
            }

        writers = self.writers[row.table_name]
        for writer in writers.values():
            try:
                writer.write(record)
            except ValueError:
                # Probably a schema mis-match
                error_msgs = [f"While logging table {row.table_name}:"]
                for i in range(min(len(writer.schema), len(record.schema))):
                    if writer.schema[i] != record.schema[i]:
                        error_msgs.append(
                            f"Schema mismatch at index {i}: "
                            f"{writer.schema[i]} vs {record.schema[i]}"
                        )
                if len(error_msgs) > 3:
                    error_msgs = error_msgs[:3]
                    error_msgs.append("...")
                raise ValueError("\n".join(error_msgs))
                # raise ValueError(error_msgs[0])
                # prior_data = pa.parquet.read_table(writer.filename)

    def close(self):
        for writers in self.writers.values():
            for writer in writers.values():
                writer.close()

    def _create_writer(self, table: str, ext: str, schema: pa.Schema):
        path = f"{self.base_path}/{self.run_name}/{table}{ext}"
        # print("creating writer", path)
        stream = self.fs.open_output_stream(path)
        if ext == ".csv":
            return pa.csv.CSVWriter(stream, schema)
        elif ext == ".parquet":
            return pa.parquet.ParquetWriter(stream, schema)


def load_parquet_file(
    filename: str, keys: Optional[list[str]]
) -> dict[str, list[noko.ScalarTypes]]:
    table = pa.parquet.read_table(filename, columns=keys)
    return table.to_pydict()


noko.LOAD_FILETYPES[".parquet"] = load_parquet_file


def load_csv_file(
    filename: str, keys: Optional[list[str]]
) -> dict[str, list[noko.ScalarTypes]]:
    table = pa.csv.read_csv(
        filename, read_options=pa.csv.ReadOptions(column_names=keys)
    )
    return table.to_pydict()


noko.LOAD_FILETYPES[".csv"] = load_csv_file
