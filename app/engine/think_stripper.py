"""过滤各类大语言模型中的思维链与思考块标签，确保只保留真实对外回复。"""

import re


class ThinkStripper:
    """思考块与思维链清洗器。"""

    # 匹配完整成对的思考标签
    _PAIRED_THINK = re.compile(
        r"<(?:think|thinking|thought|reasoning)(?:ing)?>.*?</(?:think|thinking|thought|reasoning)(?:ing)?>|"
        r"◁(?:think|thought)▷.*?◁/(?:think|thought)▷|"
        r"<redacted_thinking>.*?</redacted_thinking>",
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 匹配未闭合或截断的思考标签（防止因 Token 耗尽残留思考）
    _UNCLOSED_THINK = re.compile(
        r"<(?:think|thinking|thought|reasoning)(?:ing)?>.*|"
        r"◁(?:think|thought)▷.*",
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 匹配独立的孤立闭合标签
    _ORPHAN_TAGS = re.compile(
        r"</?(?:think|thinking|thought|reasoning)(?:ing)?>|"
        r"◁/?(?:think|thought)▷|"
        r"</?redacted_thinking>",
        flags=re.IGNORECASE,
    )

    def strip(self, text: str) -> str:
        """剥除文本中所有思维链内容。"""
        if not text:
            return ""

        # 1. 移除成对完整的思考块
        cleaned = self._PAIRED_THINK.sub("", text)
        
        # 2. 如果包含尚未闭合的思考标签，移除标签之后的内容
        cleaned = self._UNCLOSED_THINK.sub("", cleaned)

        # 3. 移除残留孤立的标签符号
        cleaned = self._ORPHAN_TAGS.sub("", cleaned)

        return cleaned.strip()
