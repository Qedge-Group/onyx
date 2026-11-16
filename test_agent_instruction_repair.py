import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "repair", Path(__file__).parent / "backend/onyx/db/agent_configuration.py"
)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class RepairTests(unittest.TestCase):
    def test_complete_only_known_incomplete_citation_rule(self):
        original = "业务排除规则必须保留。\n二、回答语言\n所有回答必须使用简体中文。\n三、检索与回答流程\n只使用指定 Document Set\n五、引用要求\n1. 使用 Onyx 支持的文档引用方式，为回答中的关键事实附上"
        result = repair.repair_prompt(original, 2)
        self.assertIn("业务排除规则必须保留", result)
        self.assertIn("只使用指定 Document Set", result)
        self.assertIn("真实来源引用", result)
        self.assertIn("回答语言跟随用户当前问题", result)
        self.assertEqual(repair.repair_prompt(result, 2), result)

    def test_language_alignment_preserves_source_and_evidence_rules(self):
        original = "Only this Document Set.\nII. OUTPUT LANGUAGE\nAlways English.\nIII. RETRIEVAL AND ANSWERING PROCESS\nNever invent evidence.\nAlways write the final response in English."
        result = repair.repair_prompt(original, 1)
        self.assertIn("Only this Document Set", result)
        self.assertIn("Never invent evidence", result)
        self.assertNotIn("Always English", result)
        self.assertIn("language of the current user question", result)
        self.assertEqual(repair.repair_prompt(result, 1), result)
        self.assertNotIn(
            "English-only",
            repair.repair_reminders(
                "Always respond in English, regardless of question.\n\nKeep English-only output requirements.",
                1,
            ),
        )


if __name__ == "__main__":
    unittest.main()
