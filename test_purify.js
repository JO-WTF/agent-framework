const jsdom = require("jsdom");
const { JSDOM } = jsdom;
const window = new JSDOM("").window;
const DOMPurify = require("dompurify")(window);
const marked = require("marked");

const content = "<think> Let me think about this... maybe I should count to 10";
const parsed = marked.parse(content);
console.log("Marked output:", parsed);
const sanitized = DOMPurify.sanitize(parsed);
console.log("DOMPurify output:", sanitized);
