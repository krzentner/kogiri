import noko
from noko import Logger, log_row


def test_log_pprint(tmp_path):
    from noko.pprint_output import PPrintOutputEngine
    import io

    hi = "HI ^_^"
    f = io.StringIO()
    logger = Logger(runs_dir=tmp_path, run_name="test_log_pprint")
    noko._LOGGER = logger
    logger.add_output(PPrintOutputEngine(f, log_level=noko.INFO))
    log_row(level=noko.INFO)
    content1 = f.getvalue()
    assert hi in content1
    log_row(level=noko.INFO)
    content2 = f.getvalue()
    assert hi in content2
    assert content2.startswith(content1)
    assert len(content2) > len(content1)
    print(content2)


def test_log_json(tmp_path):
    from noko.ndjson_output import NDJsonOutputEngine
    import io

    hi = "HI ^_^"
    f = io.StringIO()
    logger = Logger(runs_dir=tmp_path, run_name="test_log_json")
    noko._LOGGER = logger
    logger.add_output(NDJsonOutputEngine(f))
    log_row()
    content1 = f.getvalue()
    assert hi in content1
    log_row()
    content2 = f.getvalue()
    assert hi in content2
    assert content2.startswith(content1)
    assert len(content2) > len(content1)
    print(content2)
