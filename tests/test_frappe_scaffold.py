"""Static schema and safety checks; not a substitute for Frappe integration tests."""
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "frappe_app" / "agentsteers_frappe"

class FrappeScaffoldTests(unittest.TestCase):
    def test_three_owner_scoped_doctypes(self):
        for slug in ("agentsteers_task", "agentsteers_connection", "agentsteers_user_settings"):
            path = APP / "agentsteers" / "doctype" / slug / (slug + ".json")
            schema = json.loads(path.read_text())
            fields = {x["fieldname"] for x in schema["fields"]}
            self.assertIn("owner_user", fields)
            self.assertTrue(schema["permissions"])
            self.assertEqual({"System Manager"}, {p["role"] for p in schema["permissions"]})

    def test_read_api_requires_session_and_owner_filter(self):
        api = (APP / "api.py").read_text()
        self.assertIn('user == "Guest"', api)
        self.assertEqual(4, api.count('filters={"owner_user": user}'))
        self.assertNotIn("subprocess", api)
        self.assertNotIn("os.system", api)

if __name__ == "__main__":
    unittest.main()
