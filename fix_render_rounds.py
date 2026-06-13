import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_logic = """  if (status === "running" && model_output) {
    const rounds = model_output.split(/\\n*\\[\\[MODEL_OUTPUT_ROUND_BREAK\\]\\]\\n*/g);
    const activeRound = rounds[rounds.length - 1].trim();
    if (activeRound) {
      const parsedBlocks = parseMessageBlocksJS(activeRound);
      if (parsedBlocks) {
        displayMessages.push({ role: "assistant", content: activeRound, blocks: parsedBlocks });
      } else {
        displayMessages.push({ role: "assistant", content: activeRound });
      }
    }
  }"""

new_logic = """  if (status === "running" && model_output) {
    const rounds = model_output.split(/\\n*\\[\\[MODEL_OUTPUT_ROUND_BREAK\\]\\]\\n*/g);
    for (const round of rounds) {
      const activeRound = round.trim();
      if (activeRound) {
        const parsedBlocks = parseMessageBlocksJS(activeRound);
        if (parsedBlocks) {
          displayMessages.push({ role: "assistant", content: activeRound, blocks: parsedBlocks });
        } else {
          displayMessages.push({ role: "assistant", content: activeRound });
        }
      }
    }
  }"""

content = content.replace(old_logic, new_logic)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Fixed rounds rendering!")
