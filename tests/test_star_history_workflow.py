from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "star-history.yml"
RELEASE_ASSET_URL = (
    "https://github.com/LB623/no-negative-echo/releases/download/"
    "star-history/star-history.svg"
)


class StarHistoryWorkflowTests(unittest.TestCase):
    def test_workflow_publishes_release_asset_without_commits(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("gh release upload star-history", workflow)
        self.assertIn("--clobber", workflow)
        self.assertNotIn("git commit", workflow)
        self.assertNotIn("git push", workflow)

    def test_readmes_use_the_release_asset(self):
        for name in ("README.md", "README_EN.md"):
            readme = (REPOSITORY_ROOT / name).read_text(encoding="utf-8")
            self.assertIn(RELEASE_ASSET_URL, readme)
            self.assertNotIn("docs/assets/star-history.svg)]", readme)


if __name__ == "__main__":
    unittest.main()
