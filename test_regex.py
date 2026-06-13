import re

_WIDGET_RE = re.compile(
    r"(?:^[ \t]*(?:`{3,}|~{3,})[ \t]*(?:widget|json)?[ \t]*\r?\n|^[ \t]*(?:widget|json)[ \t]*\r?\n)?"
    r"(?P<body>\{\s*\"widget_type\"[\s\S]*?\n\})"
    r"(?:\r?\n^[ \t]*(?:`{3,}|~{3,}))?",
    re.MULTILINE
)

str3 = """json
{
  "widget_type": "map",
  "props": {
    "nested": {
      "a": 1
    }
  }
}
"""

match = _WIDGET_RE.search(str3)
if match:
    print("Match 3:", match.group(0))
    print("Body 3:", match.group("body"))
