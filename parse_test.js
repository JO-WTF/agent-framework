function parseMessageBlocksJS(content) {
  if (!content) return null;
  
  const blocks = [];
  // Regex to match ```widget ... ```
  // We use [\s\S]*? to match across newlines
  const regex = /^[ \t]*(`{3,}|~{3,})[ \t]*widget[ \t]*\r?\n([\s\S]*?)\n[ \t]*\1[ \t]*$/gm;
  
  let lastIndex = 0;
  let match;
  
  while ((match = regex.exec(content)) !== null) {
    // Add preceding text block if any
    const textBefore = content.substring(lastIndex, match.index);
    if (textBefore.trim()) {
      blocks.push({ type: "text", content: textBefore.trim() });
    }
    
    // Parse widget
    try {
      const payload = JSON.parse(match[2].trim());
      if (payload && payload.widget_type) {
        blocks.push({
          type: "widget",
          widget_type: payload.widget_type,
          id: payload.id || "",
          props: payload.props || {}
        });
      } else {
        // Fallback to text if missing widget_type
        blocks.push({ type: "text", content: match[0] });
      }
    } catch (e) {
      // JSON parse error, treat as text
      blocks.push({ type: "text", content: match[0] });
    }
    
    lastIndex = regex.lastIndex;
  }
  
  // Add remaining text
  const textAfter = content.substring(lastIndex);
  if (textAfter.trim()) {
    blocks.push({ type: "text", content: textAfter.trim() });
  }
  
  // If no widgets found, return null so caller can use raw content
  return blocks.some(b => b.type === "widget") ? blocks : null;
}

const testContent = `Here is a map:
\`\`\`widget
{
  "widget_type": "map",
  "id": "123",
  "props": {}
}
\`\`\`
And some text.
`;

console.log(JSON.stringify(parseMessageBlocksJS(testContent), null, 2));
