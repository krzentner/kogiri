"""Output by using python's builtin pprint. Mostly suitable for debug logs."""
from pprint import pprint

import kogiri
from kogiri import OutputEngine, declare_output_engine


@declare_output_engine
class PPrintOutputEngine(OutputEngine):
    """OutputEngine that pprints all tables to one stream.

    Mostly used for high-priority logging to stdout.
    """

    def __init__(
        self,
        file: kogiri.FileIsh = None,
        flatten: bool = True,
        log_level=kogiri.RESULTS,
    ):
        super().__init__(log_level=log_level)
        self.fm = kogiri._utils.FileManager(file)
        self.flatten = flatten

    def log_row_inner(self, row):
        print(f"Table {row.table_name}:", file=self.fm.file)
        if self.flatten:
            msg = row.as_summary()
        else:
            msg = row.raw
        pprint(msg, stream=self.fm.file)
        self.fm.file.flush()

    def close(self):
        self.fm.close()
