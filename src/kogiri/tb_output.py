import logging

from kogiri import OutputEngine, declare_output_engine, INFO
from kogiri._utils import warn_internal

SummaryWriter = None


@declare_output_engine
class TensorBoardOutput(OutputEngine):
    """OutputEngine using tensorboard SummaryWriter.

    When constructed, will attempt to use torch's SummaryWriter,
    then tensorboardX, then tf.
    """

    def __init__(
        self, runs_dir, run_name, flush_secs=120, log_level=INFO, log_hparams=False
    ):
        super().__init__(log_level=log_level)
        global SummaryWriter
        try:
            if SummaryWriter is None:
                # Apparently this import is necessary?
                import caffe2
                from torch.utils.tensorboard import SummaryWriter
        except (ImportError, ModuleNotFoundError):
            pass
        try:
            if SummaryWriter is None:
                from tensorboardX import SummaryWriter
        except ImportError:
            pass
        try:
            if SummaryWriter is None:
                from tf.summary import SummaryWriter
        except ImportError:
            pass

        if SummaryWriter is None:
            raise ImportError("Could not find tensorboard API")

        self.writer = SummaryWriter(f"{runs_dir}/{run_name}", flush_secs=flush_secs)
        self.run_name = run_name
        self.log_hparams = log_hparams
        logging.getLogger("kogiri").info(
            f"TensorBoardOutput logging at level {self.log_level}"
        )

    def log_row_inner(self, row):
        if row.table_name == "hparams" and self.log_hparams:
            flat_dict = row.as_summary()
            hparams = {
                k: v for (k, v) in flat_dict.items() if not k.startswith("metric")
            }
            metrics = {k: v for (k, v) in flat_dict.items() if k.startswith("metric")}
            # Handle tensorboardX API difference
            try:
                self.writer.add_hparams(hparams, metrics, run_name="hparams")
            except TypeError:
                self.writer.add_hparams(hparams, metrics, name="hparams")
        else:
            for k, v in row.as_summary().items():
                if v is not None and not isinstance(v, str):
                    try:
                        self.writer.add_scalar(
                            f"{row.table_name}/{k}".replace(":", "_"), v, row.step
                        )
                    except (TypeError, NotImplementedError) as ex:
                        warn_internal(f"Could not log key {k} in TensorBoard: {ex}")
        self.writer.flush()

    def close(self):
        """Flush all the events to disk and close the file."""
        self.writer.close()
