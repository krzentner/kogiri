import pytest
from glob import glob
from subprocess import run

EXAMPLES = glob("examples/*.py") + glob("examples/**/*.py")


@pytest.mark.parametrize("example_path", EXAMPLES)
def test_run_trainer(example_path):
    print("Running:", example_path)
    run(['python', example_path], check=True)
