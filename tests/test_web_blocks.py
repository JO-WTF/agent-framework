import unittest

from app.web_blocks import message_has_widgets, parse_message_blocks


class WebBlocksTests(unittest.TestCase):
    def test_plain_text_yields_single_text_block(self):
        blocks = parse_message_blocks("你好，这是一个普通回复。")

        self.assertEqual(
            blocks,
            [{"type": "text", "format": "markdown", "content": "你好，这是一个普通回复。"}],
        )
        self.assertFalse(message_has_widgets(blocks))

    def test_empty_content_yields_no_blocks(self):
        self.assertEqual(parse_message_blocks(""), [])
        self.assertEqual(parse_message_blocks("   \n  "), [])

    def test_widget_between_text_is_split_in_order(self):
        content = (
            "下面是雅加达的位置：\n\n"
            "```widget\n"
            '{"widget_type": "map", "id": "w1", "props": {"center": {"lat": -6.2, "lng": 106.8}, "zoom": 8}}\n'
            "```\n\n"
            "以上就是地图。"
        )

        blocks = parse_message_blocks(content)

        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0], {"type": "text", "format": "markdown", "content": "下面是雅加达的位置："})
        self.assertEqual(
            blocks[1],
            {
                "type": "widget",
                "widget_type": "map",
                "id": "w1",
                "props": {"center": {"lat": -6.2, "lng": 106.8}, "zoom": 8},
            },
        )
        self.assertEqual(blocks[2], {"type": "text", "format": "markdown", "content": "以上就是地图。"})
        self.assertTrue(message_has_widgets(blocks))

    def test_multiple_widgets(self):
        content = (
            "```widget\n"
            '{"widget_type": "map", "props": {"zoom": 5}}\n'
            "```\n"
            "中间文字\n"
            "```widget\n"
            '{"widget_type": "weather", "props": {"location": "Jakarta"}}\n'
            "```"
        )

        blocks = parse_message_blocks(content)

        self.assertEqual([b.get("type") for b in blocks], ["widget", "text", "widget"])
        self.assertEqual(blocks[0]["widget_type"], "map")
        self.assertEqual(blocks[0]["props"], {"zoom": 5})
        self.assertNotIn("id", blocks[0])
        self.assertEqual(blocks[2]["widget_type"], "weather")

    def test_invalid_widget_json_is_kept_as_text(self):
        content = "前缀\n```widget\n{not valid json}\n```\n后缀"

        blocks = parse_message_blocks(content)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "text")
        self.assertIn("```widget", blocks[0]["content"])

    def test_widget_missing_type_is_kept_as_text(self):
        content = "```widget\n{\"props\": {\"zoom\": 3}}\n```"

        blocks = parse_message_blocks(content)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "text")

    def test_widget_props_default_to_empty_dict(self):
        blocks = parse_message_blocks('```widget\n{"widget_type": "map"}\n```')

        self.assertEqual(blocks, [{"type": "widget", "widget_type": "map", "props": {}}])


if __name__ == "__main__":
    unittest.main()
