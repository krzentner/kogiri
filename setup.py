# This setup.py exists purely to allow editable installs
from setuptools import setup
from setuptools import find_packages

setup(
    name="noko",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
)
