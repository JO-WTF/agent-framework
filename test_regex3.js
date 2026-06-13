const regex = /^[ \t]*(`{3,}|~{3,})[ \t]*widget[ \t]*\r?\n([\s\S]*?)\n[ \t]*\1[ \t]*$/gm;
const content = `\`\`\`widget
{
  "widget_type": "map"
}
\`\`\`
</think>`;
let match = regex.exec(content);
console.log(match ? "MATCH" : "NO MATCH");
