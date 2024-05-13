import kogiri


class MyPoint:
    def __init__(self, x, y, metadata):
        self.x = x
        self.y = y
        self.metadata = metadata


@kogiri.declare_summarizer(MyPoint)
def summarize_mypoint(point, prefix: str, dst: dict[str, kogiri.ScalarTypes]):
    # Include x and y fields directly
    dst[f"{prefix}.x"] = point.x
    dst[f"{prefix}.y"] = point.y
    # Recursively summarize metadata
    kogiri.summarize(point.metadata, f"{prefix}.metadata", dst)


def test_summarize_mypoint():
    p = MyPoint(10, 20, {"hat": True, "color": "green"})
    summary = {}
    kogiri.summarize({"p": p}, "test", summary)
    assert summary["test/p.x"] == 10
    assert summary["test/p.y"] == 20
    assert summary["test/p.metadata/color"] == "green"
