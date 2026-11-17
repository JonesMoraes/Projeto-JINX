from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from skills import SkillContext, SkillRegistry


def write_skill(root: Path, response: str) -> Path:
    folder = root / "sample_skill"
    folder.mkdir(exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\n"
        "name: sample_skill\n"
        "description: Minimal test skill\n"
        "intents:\n"
        "  - run sample\n"
        "supported_os: [any]\n"
        "version: '1.0'\n"
        "required_capabilities: []\n"
        "params:\n"
        "  type: object\n"
        "  properties:\n"
        "    value:\n"
        "      type: string\n"
        "  required: [value]\n"
        "  additionalProperties: false\n"
        "---\n\nA test fixture.\n",
        encoding="utf-8")
    (folder / "handler.py").write_text(
        "from skills import BaseSkill, SkillResult\n"
        "class Skill(BaseSkill):\n"
        "    async def run(self, params, ctx):\n"
        f"        return SkillResult('done', {response!r}, {{'value': params['value']}})\n",
        encoding="utf-8")
    return folder


class SkillRegistryTests(unittest.TestCase):
    def test_discovers_validates_and_runs_async_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            write_skill(Path(temp), "first")
            registry = SkillRegistry(Path(temp), watch=False,
                                     context=SkillContext(metadata={"test": True}))
            self.addCleanup(lambda: asyncio.run(registry.close()))
            self.assertEqual(registry.resolve_intent("  RUN   SAMPLE "), "sample_skill")
            result = asyncio.run(registry.run("sample_skill", {"value": "ok"}))
            self.assertEqual(result.status, "done")
            self.assertEqual(result.message, "first")
            self.assertEqual(result.data["value"], "ok")

    def test_schema_rejects_missing_wrong_and_extra_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            write_skill(Path(temp), "first")
            registry = SkillRegistry(Path(temp), watch=False)
            self.addCleanup(lambda: asyncio.run(registry.close()))
            for params in ({}, {"value": 3}, {"value": "ok", "extra": True}):
                result = asyncio.run(registry.run("sample_skill", params))
                self.assertEqual(result.status, "failed")

    def test_failed_edit_keeps_last_good_handler(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = write_skill(Path(temp), "first")
            registry = SkillRegistry(Path(temp), watch=False)
            self.addCleanup(lambda: asyncio.run(registry.close()))
            (folder / "handler.py").write_text("this is not valid Python !!!", encoding="utf-8")
            self.assertFalse(registry.reload_skill(folder))
            result = asyncio.run(registry.run("sample_skill", {"value": "ok"}))
            self.assertEqual(result.message, "first")

    def test_watchdog_hot_reloads_changed_handler(self):
        with tempfile.TemporaryDirectory() as temp:
            write_skill(Path(temp), "first")
            registry = SkillRegistry(Path(temp), watch=True)
            self.addCleanup(lambda: asyncio.run(registry.close()))
            self.assertIsNotNone(registry._observer)
            write_skill(Path(temp), "second")
            async def wait_for_reload():
                deadline = time.monotonic() + 5
                result = None
                while time.monotonic() < deadline:
                    result = await registry.run("sample_skill", {"value": "ok"})
                    if result.message == "second":
                        break
                    await asyncio.sleep(0.05)
                return result

            result = asyncio.run(wait_for_reload())
            self.assertIsNotNone(result)
            self.assertEqual(result.message, "second")

    def test_os_restriction_is_enforced_using_injected_backend(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = write_skill(Path(temp), "first")
            manifest = folder / "SKILL.md"
            manifest.write_text(manifest.read_text(encoding="utf-8").replace(
                "supported_os: [any]", "supported_os: [windows]"), encoding="utf-8")
            backend = type("Backend", (), {"os_name": "Linux"})()
            registry = SkillRegistry(Path(temp), watch=False,
                                     context=SkillContext(os_backend=backend))
            self.addCleanup(lambda: asyncio.run(registry.close()))
            result = asyncio.run(registry.run("sample_skill", {"value": "ok"}))
            self.assertEqual(result.status, "failed")

    def test_platform_neutral_skill_runs_with_each_os_backend(self):
        from adapters.os_adapter import get_backend

        with tempfile.TemporaryDirectory() as temp:
            write_skill(Path(temp), "portable")
            registry = SkillRegistry(Path(temp), watch=False)
            self.addCleanup(lambda: asyncio.run(registry.close()))
            for os_name in ("Windows", "macOS", "Linux"):
                context = SkillContext(os_backend=get_backend(os_name))
                result = asyncio.run(registry.run("sample_skill", {"value": "ok"}, context))
                self.assertEqual(result.status, "done", os_name)
                self.assertEqual(result.message, "portable")


if __name__ == "__main__":
    unittest.main()
