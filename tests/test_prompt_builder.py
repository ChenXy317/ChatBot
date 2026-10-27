"""三段式 System Prompt 拼接规则测试。"""

import unittest

from app.engine.prompt_builder import compose_system_prompt


class ComposeSystemPromptTests(unittest.TestCase):
    def test_joins_three_parts_with_blank_lines(self):
        self.assertEqual(
            compose_system_prompt("角色", "好友", "输出"),
            "角色\n\n好友\n\n输出",
        )

    def test_omits_empty_friend_prompt(self):
        self.assertEqual(
            compose_system_prompt("角色", "", "输出"),
            "角色\n\n输出",
        )

    def test_trims_each_part(self):
        self.assertEqual(
            compose_system_prompt("  角色  ", "  好友  ", "  输出  "),
            "角色\n\n好友\n\n输出",
        )


if __name__ == "__main__":
    unittest.main()
