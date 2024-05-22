import noko
from noko.ndjson_output import NDJsonOutputEngine

noko._setup_py_logging("runs/noko_tests")


def test_round_trip(tmp_path):
    f_name = f"{tmp_path}/test.ndjson"
    output = NDJsonOutputEngine(f_name)
    output.log_row_inner(
        noko.Row(
            table_name="test_table1",
            raw={"y": 0, "x": 1},
            step=10,
        )
    )
    output.log_row_inner(
        noko.Row(
            table_name="test_table1",
            raw={"y": 0, "x": 2, "z": 10},
            step=20,
        )
    )
    output.log_row_inner(
        noko.Row(
            table_name="test_table1",
            raw={"x": 3, "z": 20},
            step=30,
        )
    )
    output.log_row_inner(
        noko.Row(
            table_name="test_table1",
            raw={"a": 1, "b": 2},
            step=40,
        )
    )
    output.log_row_inner(
        noko.Row(
            table_name="test_table1",
            raw={"q1": 1, "q2": 2, "q3": 3, "q4": 4},
            step=50,
        )
    )
    output.log_row_inner(
        noko.Row(
            table_name="test_table2",
            raw={"x": 1, "y": 2},
            step=11,
        )
    )
    data = noko.ndjson_output.load_ndjson_file(f_name)
    assert data["test_table1.x"] == [1, 2, 3, None, None]
    assert data["test_table1.y"] == [0, 0, None, None, None]
    assert data["test_table1.z"] == [None, 10, 20, None, None]
    assert data["test_table1.q1"] == [None, None, None, None, 1]
    assert data["test_table1.q2"] == [None, None, None, None, 2]
    assert data["test_table1.q3"] == [None, None, None, None, 3]
    assert data["test_table1.q4"] == [None, None, None, None, 4]
    assert data["test_table1.a"] == [None, None, None, 1, None]
    assert data["test_table1.b"] == [None, None, None, 2, None]
    assert data["test_table1.$step"] == [10, 20, 30, 40, 50]
    assert data["test_table2.$step"] == [11]
    assert data["test_table2.x"] == [1]
    assert data["test_table2.y"] == [2]
