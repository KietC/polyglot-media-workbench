"""Synthetic contracts; no real recordings or model weights.
合成输入约定测试，不使用真实录音或模型权重。
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from media_workbench import asr
from media_workbench.core import cached, command, fingerprint, load_config, read_json, save_json, sha256, timestamp
from media_workbench.translation import request_batch, NoRedirect
from media_workbench.learning_video import video_timeline


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="media-unit-")
        self.root = Path(self.temp.name)
        self.config = load_config()

    def tearDown(self):
        self.temp.cleanup()

    def test_timestamp_rounds_across_minute(self):
        self.assertEqual(timestamp(59.9996), "00:01:00.000")
        self.assertEqual(timestamp(-3), "00:00:00.000")
        self.assertEqual(timestamp(3661.25), "01:01:01.250")

    def test_vendored_model_architecture_is_present(self):
        # A generic models/ ignore rule must not remove the speaker architecture source.
        # 通用models/忽略规则不能误删说话人模型架构源码。
        root = Path(__file__).resolve().parents[1] / "vendor/3d-speaker/speakerlab"
        for filename in ("models/campplus/DTDNN.py", "models/campplus/layers.py", "process/cluster.py"):
            self.assertTrue((root / filename).is_file(), filename)

    def test_config_is_relative_to_config_file(self):
        path = self.root / "settings.json"
        save_json(path, {"models": {"whisper": "checkpoints/a"}, "speaker_repo": "engines/speaker"})
        config = load_config(path)
        self.assertEqual(config["models"]["whisper"], str((self.root / "checkpoints/a").resolve()))
        self.assertEqual(config["speaker_repo"], str((self.root / "engines/speaker").resolve()))

    def test_config_rejects_invalid_batch(self):
        path = self.root / "settings.json"
        for value in (0, -1, 1.5, True):
            save_json(path, {"batch_size": value})
            with self.assertRaises(ValueError):
                load_config(path)

    def test_json_atomic_utf8_and_no_shared_temp(self):
        p = self.root / "nested/record.json"
        save_json(p, {"text": "合成文本 Deutsch English"})
        self.assertEqual(read_json(p)["text"], "合成文本 Deutsch English")
        self.assertEqual(len(list(p.parent.glob("*.tmp"))), 0)

    def test_cache_rejects_partial_wrong_and_corrupt(self):
        p = self.root / "checkpoint.json"
        self.assertIsNone(cached(p, "a"))
        save_json(p, {"status": "complete", "fingerprint": "a"})
        self.assertIsNotNone(cached(p, "a"))
        self.assertIsNone(cached(p, "b"))
        save_json(p, {"status": "running", "fingerprint": "a"})
        self.assertIsNone(cached(p, "a"))
        p.write_text("{truncated", encoding="utf8")
        self.assertIsNone(cached(p, "a"))

    def test_fingerprint_changes_for_parameters_and_input(self):
        a = fingerprint("input-A", "fuse", self.config)
        self.assertNotEqual(a, fingerprint("input-B", "fuse", self.config))
        self.assertNotEqual(a, fingerprint("input-A", "fuse", dict(self.config, batch_size=4)))

    def test_fingerprint_changes_for_model_content(self):
        model = self.root / "model"
        model.mkdir()
        (model / "config.json").write_text("{}")
        config = dict(self.config, models=dict(self.config["models"], whisper=str(model)))
        a = fingerprint("input", "whisper", config)
        (model / "config.json").write_text('{"changed":true}')
        self.assertNotEqual(a, fingerprint("input", "whisper", config))

    def test_missing_model_is_explicit(self):
        config = dict(self.config, models=dict(self.config["models"], whisper=str(self.root / "missing")))
        with self.assertRaises(FileNotFoundError):
            fingerprint("input", "whisper", config)

    def test_speaker_accumulates_disjoint_intervals(self):
        rows = [
            dict(start=0, end=1, speaker="S0"),
            dict(start=1, end=2.5, speaker="S1"),
            dict(start=2.5, end=3.5, speaker="S0"),
        ]
        self.assertEqual(asr.speaker_for(0, 4, rows), "S0")
        self.assertEqual(asr.speaker_for(4, 5, rows), "SPEAKER_UNKNOWN")

    def test_fusion_keeps_alternatives_and_review(self):
        save_json(
            self.root / "whisper.json",
            {
                "segments": [
                    dict(
                        start=0,
                        end=2,
                        text="Synthetic sample",
                        words=[dict(start=0, end=1, word="Synthetic "), dict(start=1, end=2, word="sample")],
                    )
                ]
            },
        )
        save_json(
            self.root / "qwen.json",
            {"results": [dict(start=0, end=2, text="A completely different phrase", language="English")]},
        )
        save_json(self.root / "diar.json", {"segments": [dict(start=0, end=2, speaker="S0")]})
        result = asr.fuse(self.root)
        self.assertEqual(result["editorial_status"], "pending")
        self.assertTrue(result["units"][0]["needs_review"])
        self.assertEqual(result["units"][0]["whisper"], "Synthetic sample")

    def test_failure_records_failed_stage(self):
        media = dict(source_sha256="synthetic", wav="unused", duration=1)
        with (
            patch.object(asr, "prepare", return_value=media),
            patch.object(asr, "fingerprint", return_value="a"),
            patch.object(asr, "whisper", side_effect=RuntimeError("synthetic failure")),
        ):
            with self.assertRaises(RuntimeError):
                asr.run(self.root / "source.wav", self.root, self.config, ["whisper"])
        self.assertEqual(read_json(self.root / "state.json")["status"], "failed")

    def test_loopback_restriction(self):
        config = dict(
            self.config, translation=dict(self.config["translation"], url="https://example.invalid/v1/chat/completions")
        )
        with self.assertRaises(ValueError):
            request_batch([], config)

    def test_translation_rejects_wrong_order(self):
        units = [
            dict(id="U1", original="First synthetic phrase", language="English"),
            dict(id="U2", original="Second synthetic phrase", language="English"),
        ]
        answer = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"translations": [{"id": "U2", "zh": "二"}, {"id": "U1", "zh": "一"}]})
                    }
                }
            ]
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return json.dumps(answer).encode()

        with patch("media_workbench.translation.local_open", return_value=Response()):
            with self.assertRaises(ValueError):
                request_batch(units, self.config)

    def test_translation_never_follows_redirect(self):
        from urllib.request import Request
        from urllib.error import HTTPError

        with self.assertRaises(HTTPError):
            NoRedirect().redirect_request(
                Request("http://127.0.0.1:5127/v1/chat/completions"), None, 302, "Found", {}, "https://example.invalid/"
            )

    def test_nonzero_command_fails(self):
        import sys

        with self.assertRaises(RuntimeError):
            command([sys.executable, "-c", "raise SystemExit(3)"], 10)

    def test_hash_is_content_based(self):
        a = self.root / "a.txt"
        b = self.root / "b.txt"
        a.write_text("synthetic")
        b.write_text("synthetic")
        self.assertEqual(sha256(a), sha256(b))

    def test_video_span_uses_packets_not_container_duration(self):
        packets = {
            "packets": [
                {"pts_time": "0.080", "duration_time": "0.040"},
                {"pts_time": "0.000", "duration_time": "0.040"},
            ]
        }
        with patch("media_workbench.learning_video.command", return_value=json.dumps(packets)):
            result = video_timeline("synthetic.mkv", self.config)
        self.assertAlmostEqual(result["start"], 0)
        self.assertAlmostEqual(result["end"], 0.12)
        self.assertEqual(result["packets"], 2)

    def test_video_span_rejects_empty_packets(self):
        with patch("media_workbench.learning_video.command", return_value='{"packets": []}'):
            with self.assertRaises(RuntimeError):
                video_timeline("synthetic.mkv", self.config)


if __name__ == "__main__":
    unittest.main()
