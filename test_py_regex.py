import re
import json

_WIDGET_FENCE_RE = re.compile(
    r"^[ \t]*(?P<fence>`{3,}|~{3,})[ \t]*widget[ \t]*\r?\n"
    r"(?P<body>.*?)\r?\n?"
    r"^[ \t]*(?P=fence)[ \t]*$",
    re.DOTALL | re.MULTILINE,
)

content = """<think>
地图卡片已成功渲染。现在我需要将widget代码块原封不动地嵌入到我的最终答复中。
```widget
{
  "widget_type": "map",
  "id": "map-b54ef4caf388",
  "props": {
    "use_stored_card": true
  }
}
```
</think>"""

for match in _WIDGET_FENCE_RE.finditer(content):
    print("MATCH FOUND!")
    print(match.group("body"))
