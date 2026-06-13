import re

_WIDGET_FENCE_RE = re.compile(
    r"(?P<fence>`{3,}|~{3,})[ \t]*widget[ \t]*\r?\n"
    r"(?P<body>.*?)\r?\n?"
    r"(?P=fence)",
    re.DOTALL
)

text = "<think>地图卡片已成功渲染。</think>```widget\n{\n  \"a\": 1\n}\n```"

blocks = []
cursor = 0
for match in _WIDGET_FENCE_RE.finditer(text):
    leading = text[cursor:match.start()]
    print("LEADING:", repr(leading))
    print("BODY:", repr(match.group("body")))
    cursor = match.end()

print("TRAILING:", repr(text[cursor:]))
