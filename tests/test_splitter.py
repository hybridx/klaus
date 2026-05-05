"""Tests for the task splitter."""

from klaus.routing.splitter import SubTask, split_tasks


class TestSplitTasks:
    def test_single_simple_message(self):
        result = split_tasks("write a python function")
        assert len(result) == 1
        assert result[0].text == "write a python function"
        assert result[0].task_type == "coding"

    def test_single_short_message(self):
        result = split_tasks("hello")
        assert len(result) == 1
        assert result[0].text == "hello"

    def test_empty_message(self):
        result = split_tasks("")
        assert len(result) == 1

    def test_split_on_then(self):
        result = split_tasks("create a code for prime number then create a poem")
        assert len(result) == 2
        assert "prime" in result[0].text.lower()
        assert "poem" in result[1].text.lower()
        assert result[0].task_type == "coding"
        assert result[1].task_type == "creative"

    def test_split_on_comma_then(self):
        result = split_tasks("write a sorting algorithm, then write a haiku")
        assert len(result) == 2
        assert result[0].task_type == "coding"
        assert result[1].task_type == "creative"

    def test_split_on_and_also(self):
        result = split_tasks("analyze this data and also summarize the results")
        assert len(result) == 2
        assert result[0].task_type == "analysis"
        assert result[1].task_type == "summarization"

    def test_split_on_semicolon(self):
        result = split_tasks("write a python script; write a poem about coding")
        assert len(result) == 2

    def test_split_on_after_that(self):
        result = split_tasks("debug this function after that write documentation")
        assert len(result) == 2
        assert result[0].task_type == "coding"

    def test_numbered_list(self):
        text = "1. Write a fibonacci function\n2. Write a poem about recursion"
        result = split_tasks(text)
        assert len(result) == 2
        assert "fibonacci" in result[0].text.lower()
        assert "poem" in result[1].text.lower()

    def test_numbered_list_with_parens(self):
        text = "1) Create a sorting algorithm\n2) Summarize how it works"
        result = split_tasks(text)
        assert len(result) == 2

    def test_bullet_list(self):
        text = "- Write code for binary search\n- Write a story about a computer"
        result = split_tasks(text)
        assert len(result) == 2

    def test_no_split_for_short_parts(self):
        result = split_tasks("do this then ok")
        assert len(result) == 1

    def test_preserves_index(self):
        result = split_tasks("code a prime checker then write a limerick")
        assert result[0].index == 0
        assert result[1].index == 1

    def test_three_tasks(self):
        text = "1. Write a python sort\n2. Write a poem\n3. Summarize both approaches"
        result = split_tasks(text)
        assert len(result) == 3

    def test_subtask_dataclass(self):
        st = SubTask(index=0, text="hello", task_type="coding")
        assert st.index == 0
        assert st.text == "hello"
        assert st.task_type == "coding"

    def test_period_then(self):
        result = split_tasks(
            "Write a binary search function. Then write a creative story about it."
        )
        assert len(result) == 2

    def test_no_false_split_on_then_in_word(self):
        result = split_tasks("authenticate the user")
        assert len(result) == 1

    def test_classify_each_subtask_independently(self):
        result = split_tasks(
            "solve this math equation then summarize the key points of this article"
        )
        assert len(result) == 2
        assert result[0].task_type == "reasoning"
        assert result[1].task_type == "summarization"
