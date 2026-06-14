const fs = require('fs');
const code = fs.readFileSync('app/web_static/app.js', 'utf8');

const regex = /node\.querySelectorAll\("\.chat-widget"\)\.forEach\(w => \{[\s\S]*?w\.parentNode\.replaceChild\(saved, w\);[\s\S]*?\}\);/m;
const match = code.match(regex);
console.log("Match found?", !!match);
