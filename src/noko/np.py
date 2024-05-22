"""Enhances noko.summarize to handle numpy arrays."""
from noko import declare_summarizer
from noko._utils import warn_internal

try:
    import numpy as np
except ImportError as ex:
    warn_internal("noko.np imported, but numpy could not be imported")
    warn_internal(ex)


@declare_summarizer("numpy.ndarray", monkey_patch=False)
def summarize_array(array, key, dst):
    if array.flatten().shape == (1,):
        dst[key] = array.flatten()[0]
    else:
        dst[f"{key}.mean"] = array.astype("float").mean()
        try:
            dst[f"{key}.min"] = array.min()
            dst[f"{key}.max"] = array.max()
        except RuntimeError:
            pass
        try:
            dst[f"{key}.std"] = array.astype("float").std()
        except RuntimeError:
            pass
