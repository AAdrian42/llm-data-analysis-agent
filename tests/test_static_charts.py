from io import BytesIO

import pandas as pd
import pytest
from PIL import Image, ImageStat

from analysis_agent import DataAnalysisAgent
from analysis_agent.charting import build_static_chart


@pytest.mark.parametrize("question", [
    "各信用等级的违约率是多少？",
    "月度申请量趋势。",
    "不同信用等级和贷款期限的违约率对比。",
    "申请量是多少？",
])
def test_static_chart_is_a_nonblank_png(question):
    result = DataAnalysisAgent().analyze(question, log_event=False)
    payload = build_static_chart(pd.DataFrame(result.rows), result.plan)
    assert payload is not None
    image = Image.open(BytesIO(payload))
    assert image.format == "PNG"
    assert image.width >= 800 and image.height >= 400
    assert ImageStat.Stat(image.convert("L")).stddev[0] > 8
