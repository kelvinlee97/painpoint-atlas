import unittest
from pathlib import Path


class WorkflowSecurityTests(unittest.TestCase):
    def test_workflow_scopes_secret_and_pins_actions(self):
        workflow = Path(".github/workflows/refresh-pages.yml").read_text(
            encoding="utf-8"
        )
        refresh_job = workflow.split("  refresh:\n", 1)[1].split(
            "  persist:\n", 1
        )[0]
        persist_job = workflow.split("  persist:\n", 1)[1].split(
            "  deploy:\n", 1
        )[0]
        deploy_job = workflow.split("  deploy:\n", 1)[1]

        self.assertEqual(
            workflow.count("OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}"), 1
        )
        self.assertIn("permissions: {}", workflow)
        self.assertIn("    permissions:\n      contents: read", refresh_job)
        self.assertNotIn("contents: write", refresh_job)
        self.assertNotIn("pages: write", refresh_job)
        self.assertNotIn("id-token: write", refresh_job)
        self.assertIn("needs: refresh", persist_job)
        self.assertIn("contents: write", persist_job)
        self.assertIn("pull-requests: write", persist_job)
        self.assertIn("GH_TOKEN: ${{ github.token }}", persist_job)
        self.assertIn('branch="automation/refresh-${GITHUB_RUN_ID}"', persist_job)
        self.assertIn('git push --set-upstream origin "$branch"', persist_job)
        self.assertIn("gh pr create", persist_job)
        self.assertIn('gh pr merge "$pr_url"', persist_job)
        self.assertNotIn("\n            git push\n", persist_job)
        self.assertNotIn("OPENAI_API_KEY", persist_job)
        self.assertIn("needs: refresh", deploy_job)
        self.assertIn("contents: read", deploy_job)
        self.assertIn("pages: write", deploy_job)
        self.assertIn("id-token: write", deploy_job)
        self.assertNotIn("OPENAI_API_KEY", deploy_job)
        self.assertNotIn("GITHUB_TOKEN", deploy_job)
        self.assertNotIn("Build static Dashboard", refresh_job)
        self.assertIn("Build static Dashboard without API secret", deploy_job)
        self.assertEqual(workflow.count("actions/download-artifact@"), 2)
        self.assertEqual(workflow.count("actions/upload-artifact@"), 1)
        self.assertIn("retention-days: 1", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", refresh_job)
        self.assertIn("if: github.ref == 'refs/heads/main'", persist_job)
        self.assertIn("if: github.ref == 'refs/heads/main'", deploy_job)
        self.assertEqual(workflow.count("persist-credentials: false"), 3)
        for action in (
            "actions/checkout@",
            "actions/setup-python@",
            "actions/upload-artifact@",
            "actions/download-artifact@",
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
