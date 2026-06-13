const regex = /(?:^[ \t]*(?:`{3,}|~{3,})[ \t]*(?:widget|json)?[ \t]*\r?\n|^[ \t]*(?:widget|json)[ \t]*\r?\n)?(\{\s*"widget_type"[\s\S]*?\n\})(?:\r?\n^[ \t]*(?:`{3,}|~{3,}))?/gm;

const str1 = `json
{
  "widget_type": "map",
  "id": "map-41c92b7ebe0e",
  "props": {
    "use_stored_card": true
  }
}
---`;

const str2 = `\`\`\`json
{
  "widget_type": "map",
  "id": "map-41c92b7ebe0e"
}
\`\`\``;

for (let i = 0; i < 2; i++) {
  const str = i === 0 ? str1 : str2;
  let match;
  regex.lastIndex = 0;
  while ((match = regex.exec(str)) !== null) {
    console.log(`MATCH ${i+1}:`, JSON.stringify(match[0]));
    console.log(`BODY ${i+1}:`, JSON.stringify(match[1]));
  }
}
