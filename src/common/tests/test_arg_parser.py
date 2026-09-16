"""`src/common/arg_parser.py` 的离线单测。

不连数据库 / Redis，也不需要 ``nonebot.init()``：只依赖适配器的 ``Message`` 类型。
运行：``python -m unittest discover -s src/common/tests -v``
"""
import unittest

from nonebot.adapters.onebot.v11 import Message, MessageSegment

from src.common.arg_parser import ArgToken, tokenize_arguments, try_parse_qq


def _text(value: str) -> MessageSegment:
    return MessageSegment("text", {"text": value})


def _at(qq) -> MessageSegment:
    return MessageSegment("at", {"qq": qq})


def _pairs(tokens) -> list[tuple[str, str]]:
    return [(t.kind, t.value) for t in tokens]


class TokenizeArgumentsTests(unittest.TestCase):
    def test_plain_text_splits_on_whitespace(self):
        self.assertEqual(_pairs(tokenize_arguments(Message([_text("a b c")]))),
                         [("text", "a"), ("text", "b"), ("text", "c")])

    def test_newline_acts_as_separator(self):
        self.assertEqual(_pairs(tokenize_arguments(Message([_text("a\nb")]))),
                         [("text", "a"), ("text", "b")])

    def test_runs_of_whitespace_collapse(self):
        self.assertEqual(_pairs(tokenize_arguments(Message([_text("a  \t b ")]))),
                         [("text", "a"), ("text", "b")])

    def test_chinese_text_splits_on_space(self):
        self.assertEqual(_pairs(tokenize_arguments(Message([_text("组名 昵称")]))),
                         [("text", "组名"), ("text", "昵称")])

    def test_empty_inputs_yield_no_tokens(self):
        for message in (Message(), Message([_text("")]), Message([_text("   ")])):
            with self.subTest(message=str(message)):
                self.assertEqual(tokenize_arguments(message), [])

    def test_at_segment_becomes_at_token(self):
        self.assertEqual(_pairs(tokenize_arguments(Message([_at("123")]))),
                         [("at", "123")])

    def test_at_then_text_keeps_order(self):
        self.assertEqual(
            _pairs(tokenize_arguments(Message([_at("123"), _text("x")]))),
            [("at", "123"), ("text", "x")],
        )

    def test_mixed_segments_keep_order(self):
        message = Message([_at("123"), _text("456"), _at("789"), _text("abc")])
        self.assertEqual(_pairs(tokenize_arguments(message)),
                         [("at", "123"), ("text", "456"), ("at", "789"), ("text", "abc")])

    def test_at_all_and_at_zero_are_skipped(self):
        for qq in ("all", "0", "", None):
            with self.subTest(qq=qq):
                self.assertEqual(tokenize_arguments(Message([_at(qq)])), [])

    def test_at_segment_without_qq_key_is_skipped(self):
        self.assertEqual(tokenize_arguments(Message([MessageSegment("at", {})])), [])

    def test_at_prefix_in_text_is_kept_verbatim(self):
        # 分词阶段不剥 @，剥离发生在 try_parse_qq
        for raw in ("@123", "@@123"):
            with self.subTest(raw=raw):
                self.assertEqual(_pairs(tokenize_arguments(Message([_text(raw)]))),
                                 [("text", raw)])

    def test_fullwidth_at_is_not_special(self):
        self.assertEqual(_pairs(tokenize_arguments(Message([_text("＠123")]))),
                         [("text", "＠123")])


class TryParseQqTests(unittest.TestCase):
    def test_at_token_with_digits(self):
        self.assertEqual(try_parse_qq(ArgToken("at", "123")), 123)

    def test_at_token_with_leading_zeros(self):
        self.assertEqual(try_parse_qq(ArgToken("at", "00123")), 123)

    def test_at_token_without_digits(self):
        for value in ("abc", "all", "0abc", ""):
            with self.subTest(value=value):
                self.assertIsNone(try_parse_qq(ArgToken("at", value)))

    def test_text_token_with_digits(self):
        self.assertEqual(try_parse_qq(ArgToken("text", "123")), 123)
        self.assertEqual(try_parse_qq(ArgToken("text", "0")), 0)

    def test_text_token_strips_at_prefix(self):
        self.assertEqual(try_parse_qq(ArgToken("text", "@123")), 123)
        self.assertEqual(try_parse_qq(ArgToken("text", "@@123")), 123)

    def test_text_token_rejects_non_digits(self):
        for value in ("abc", "-123", "＠123", "", " 123 ", "@abc", "@"):
            with self.subTest(value=value):
                self.assertIsNone(try_parse_qq(ArgToken("text", value)))

    def test_unknown_kind_is_never_parsed(self):
        for kind in ("other", "image", "AT", "Text", ""):
            with self.subTest(kind=kind):
                self.assertIsNone(try_parse_qq(ArgToken(kind, "123")))


class ArgTokenTests(unittest.TestCase):
    def test_is_a_value_object(self):
        self.assertEqual(ArgToken("at", "1"), ArgToken("at", "1"))
        self.assertNotEqual(ArgToken("at", "1"), ArgToken("text", "1"))

    def test_holds_kind_and_value(self):
        token = ArgToken("text", "hello")
        self.assertEqual((token.kind, token.value), ("text", "hello"))


class KnownLimitationTests(unittest.TestCase):
    def test_int_qq_segment_raises(self):
        """已知缺陷（本次抽取前就存在，行为未改）：手工构造的 at 段若 qq 是 int，
        `try_parse_qq` 会调 `int.isdigit()` 抛 AttributeError。

        适配器的 `MessageSegment.at()` 自身会 `str(user_id)` 归一，线上事件经
        JSON 解析后 qq 恒为 str，因此不可达；仅手工塞 dict 会踩到。
        修好（例如分词时统一 `str(qq)`）之后请同步改掉这条断言。
        """
        tokens = tokenize_arguments(Message([_at(123)]))
        self.assertEqual(_pairs(tokens), [("at", 123)])
        with self.assertRaises(AttributeError):
            try_parse_qq(tokens[0])


if __name__ == "__main__":
    unittest.main()
