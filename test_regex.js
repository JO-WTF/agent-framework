const content = "<think>\nLet's test this.\n</think>\n\nHere is a large text.\n" + "A".repeat(4000);
const regex = /(`{3,}|~{3,})[ \t]*widget[ \t]*\r?\n([\s\S]*?)\n[ \t]*\1/g;

console.time("regex");
const match = regex.exec(content);
console.timeEnd("regex");
console.log("Match:", !!match);
