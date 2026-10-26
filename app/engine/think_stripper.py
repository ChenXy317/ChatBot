"""过滤推理模型中的思维链标签，保留最终口语回复。"""

import re


class ThinkStripper:
    """思考块过滤器。"""

    _THINK_START = re.compile(
        r"<think(?:ing)?>|◁think▷|<redacted_thinking>",
        re.IGNORECASE,
    )
    _THINK_END = re.compile(
        r"</think(?:ing)?>|◁/think▷|</redacted_thinking>",
        re.IGNORECASE,
    )

    def __init__(self):
        self._buf = ""
        self._hiding = False

    def strip(self, text: str) -> str:
        """剥除文本中完整的思维链块。"""
        if not text:
            return ""
        
        # 移除已成对的完整思考标签
        cleaned = re.sub(
            r"(<think(?:ing)?>|◁think▷|<redacted_thinking>).*?(</think(?:ing)?>|◁/think▷|</redacted_thinking>)",
            "",
            text,
            flags=re.DOTALL | re.IGNORECASE
        )
        # 清除残留的孤立标签
        cleaned = self._THINK_START.sub("", cleaned)
        cleaned = self._THINK_END.sub("", cleaned)
        return cleaned.strip()
