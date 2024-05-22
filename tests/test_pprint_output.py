import noko
from noko.pprint_output import PPrintOutputEngine


def test_write(tmp_path):
    filename = f"{tmp_path}/noko.log"
    output = PPrintOutputEngine(file=filename)
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
            raw={
                "x": 1,
                "y": "3",
            },
            step=20,
        )
    )
    with open(filename) as f:
        content = f.read()
    assert "test_table1" in content
    assert "x" in content
    assert "y" in content
