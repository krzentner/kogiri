"""Enhances kogiri.summarize to handle common torch types."""
from kogiri import summarize, declare_summarizer
from kogiri._utils import warn_internal

try:
    import torch
except ImportError as ex:
    warn_internal("kogiri.torch imported, but torch could not be imported")
    warn_internal(ex)


@declare_summarizer("torch.Tensor")
def summarize_tensor(tensor, key, dst):
    if tensor.flatten().shape == (1,):
        dst[key] = tensor.flatten().item()
    else:
        dst[f"{key}.mean"] = tensor.float().mean().item()
        try:
            dst[f"{key}.min"] = tensor.min().item()
            dst[f"{key}.max"] = tensor.max().item()
        except RuntimeError:
            pass
        try:
            dst[f"{key}.std"] = tensor.float().std().item()
        except RuntimeError:
            pass


@declare_summarizer("torch.nn.Module")
def summarize_module(module, key, dst):
    for name, param in module.named_parameters():
        summarize(param, f"{key}.{name}", dst)
        if param.grad is not None:
            summarize(param.grad, f"{key}.{name}.grad", dst)


@declare_summarizer("torch.optim.Optimizer")
def summarize_optimizer(optimizer, key, dst):
    state = optimizer.state_dict()
    for param_group in state["param_groups"]:
        # These are just some lists that clutter up the plotting
        del param_group["params"]
    summarize(state, key, dst)
