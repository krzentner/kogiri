import csv
import os

import kogiri
from kogiri.csv_output import CSVOutputEngine

LOG_PATH = "runs/kogiri_tests/debug.log"
if os.path.exists(LOG_PATH):
    os.remove(LOG_PATH)
kogiri._setup_py_logging("runs/kogiri_tests")


def _read_file(f_name):
    with open(f_name) as f:
        return [line.strip() for line in f.readlines()]


def test_write(tmp_path):
    run_name = "test_run"
    output = CSVOutputEngine(runs_dir=tmp_path, run_name=run_name)
    output.log_row_inner(
        kogiri.Row(
            table_name="test_table1",
            raw={"y": 0, "x": 1},
            step=10,
        )
    )
    output.log_row_inner(
        kogiri.Row(
            table_name="test_table1",
            raw={
                "x": 1,
                "y": "3",
            },
            step=20,
        )
    )
    with open(f"{tmp_path}/{run_name}/test_table1.csv") as f:
        content = f.read()
    lines = content.split("\n")
    assert lines[0] == "$level,$localtime,$step,$utc_timestamp,x,y"
    assert lines[1].endswith("1,0")
    assert lines[2].endswith("1,3")
    # There's one trailing newline:
    assert lines[3] == ""
    assert len(lines) == 4


def test_read(tmp_path):
    f_name = f"{tmp_path}/test.csv"
    with open(f_name, "w") as f:
        w = csv.DictWriter(f, ["a", "b"])
        w.writeheader()
        w.writerow({"a": 0, "b": "test1"})
        w.writerow({"a": 1, "b": "test2"})
        w.writerow({"a": None, "b": 3.5})
    data = kogiri.csv_output.load_csv_file(f_name)
    assert sorted(data.keys()) == ["a", "b"]
    assert data["a"] == [0, 1, None]
    assert data["b"] == ["test1", "test2", 3.5]


def test_write_inconsistent_keys(tmp_path):
    run_name = "test_run"
    output = CSVOutputEngine(runs_dir=tmp_path, run_name=run_name)
    output.log_row_inner(
        kogiri.Row(
            table_name="test_table1",
            raw={"y": 0, "x": 1},
            step=10,
        )
    )
    output.log_row_inner(
        kogiri.Row(
            table_name="test_table1",
            raw={"y": 0, "x": 2, "z": 10},
            step=20,
        )
    )
    assert any(
        line.endswith("kogiri [WARNING ]: Adding new key 'z' to table 'test_table1'")
        for line in _read_file(LOG_PATH)
    )
    output.log_row_inner(
        kogiri.Row(
            table_name="test_table1",
            raw={"x": 3, "z": 20},
            step=20,
        )
    )
    output.log_row_inner(
        kogiri.Row(
            table_name="test_table1",
            raw={"a": 1, "b": 2},
            step=20,
        )
    )
    assert any(
        line.endswith(
            "kogiri [WARNING ]: Adding 2 new keys ['a','b'] to table 'test_table1'"
        )
        for line in _read_file(LOG_PATH)
    )
    output.log_row_inner(
        kogiri.Row(
            table_name="test_table1",
            raw={"q1": 1, "q2": 2, "q3": 3, "q4": 4},
            step=20,
        )
    )
    assert any(
        line.endswith(
            "kogiri [WARNING ]: Adding 4 new keys ['q1','q2','q3',...] to table 'test_table1'"
        )
        for line in _read_file(LOG_PATH)
    )
    f_name = f"{tmp_path}/{run_name}/test_table1.csv"
    data = kogiri.csv_output.load_csv_file(f_name)
    assert data["x"] == [1, 2, 3, None, None]
    assert data["y"] == [0, 0, None, None, None]
    assert data["z"] == [None, 10, 20, None, None]
