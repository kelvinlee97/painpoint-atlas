import unittest
from pathlib import Path


class WorkflowSecurityTests(unittest.TestCase):
    def test_workflow_scopes_secret_and_pins_actions(self):
        workflow = Path(".github/workflows/refresh-pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            workflow.count("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}"), 1
        )
        secret_line = workflow.index(
            "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}"
        )
        refresh_step = workflow.index("- name: Refresh collected data and analysis")
        self.assertGreater(secret_line, refresh_step)
        self.assertNotIn("env:\n      OPENAI_API_KEY", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        for action in (
            "actions/checkout@",
            "actions/setup-python@",
            "actions/configure-pages@",
            "actions/upload-pages-artifact@",
            "actions/deploy-pages@",
        ):
            self.assertRegex(
                workflow,
                rf"{action}[0-9a-f]{{40}}",
            )


if __name__ == "__main__":
    unittest.main()
