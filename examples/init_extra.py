import noko

run_dir = noko.init_extra()
print("Logging experiment results to", run_dir)
noko.log_row("test_table", {"x": 0.0})
