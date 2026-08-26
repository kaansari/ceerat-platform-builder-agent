import unittest

from ceerat_builder.main import _tool_profiles_from_source


class AppToolInventoryTests(unittest.TestCase):
    def test_extracts_agent_and_customer_profiles_without_duplicates(self) -> None:
        source = '''
func toolDefinitions() []tool {
    return []tool{{Function: toolFunction{Name: "shared"}}, {Function: toolFunction{Name: "agent_only"}}, {Function: toolFunction{Name: "shared"}}}
}
func customerToolDefinitions() []tool {
    return []tool{{Function: toolFunction{Name: "shared"}}, {Function: toolFunction{Name: "customer_only"}}}
}
func (r *ToolRunner) Run() {}
'''
        self.assertEqual(
            _tool_profiles_from_source(source),
            {"agent": ["shared", "agent_only"], "customer": ["shared", "customer_only"]},
        )

    def test_returns_empty_profiles_for_unrecognized_source(self) -> None:
        self.assertEqual(_tool_profiles_from_source("package agent"), {"agent": [], "customer": []})


if __name__ == "__main__":
    unittest.main()
