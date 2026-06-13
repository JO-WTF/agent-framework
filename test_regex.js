const regex = /^[ \t]*(`{3,}|~{3,})[ \t]*widget[ \t]*\r?\n([\s\S]*?)\n[ \t]*\1[ \t]*$/gm;
const content = `<think>
地图卡片已成功渲染。现在我需要将widget代码块原封不动地嵌入到我的最终答复中。
\`\`\`widget
{
  "widget_type": "map",
  "id": "map-b54ef4caf388",
  "props": {
    "use_stored_card": true
  }
}
\`\`\`
</think>`;

let match;
let found = false;
while ((match = regex.exec(content)) !== null) {
    found = true;
    console.log("MATCH FOUND!");
    console.log(match[2]);
}
if (!found) {
    console.log("NO MATCH");
}
