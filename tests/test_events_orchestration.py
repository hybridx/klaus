"""Tests for orchestration detection in event handling."""

from __future__ import annotations

from klaus.api.routes.events import _is_complex


class TestIsComplex:
    def test_simple_greeting(self):
        assert not _is_complex("Hello, how are you?")

    def test_single_sentence(self):
        assert not _is_complex("Write a poem about cats.")

    def test_multi_sentence_complex(self):
        assert _is_complex("Write a poem about cats. Then create a Python function for sorting.")

    def test_multi_task_marker_then(self):
        assert _is_complex("Create a function then write tests for it")

    def test_multi_task_marker_also(self):
        assert _is_complex("Write a poem and also create a drawing")

    def test_multi_task_marker_additionally(self):
        assert _is_complex("Create a login page. Additionally implement the API endpoint.")

    def test_short_fragments_not_complex(self):
        assert not _is_complex("hi there")

    def test_empty_string(self):
        assert not _is_complex("")

    def test_threshold_parameter(self):
        text = "First sentence. Second sentence. Third sentence."
        assert _is_complex(text, threshold=3)
        assert _is_complex(text, threshold=2)
        assert not _is_complex("Just one.", threshold=3)
