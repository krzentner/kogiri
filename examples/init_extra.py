import kogiri

run_dir = kogiri.init_extra()
print("Logging experiment results to", run_dir)
kogiri.log_row("test_table", {"x": 0.0})
