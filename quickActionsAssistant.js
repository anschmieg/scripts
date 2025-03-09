#!node --require=/opt/homebrew/lib/node_modules/dotenv/lib/main.js

const fs = require("fs");
require("dotenv").config();

const url =
  `https://generativelanguage.googleapis.com/v1beta/models/${process.env.GOOGLE_AI_MODEL}:generateContent`;
const apiKey = process.env.GOOGLE_AI_API_KEY;

if (require.main === module) {
  const input = fs.readFileSync(process.stdin.fd).toString();
  run(input).then(console.log);
}

async function run(input) {
  const requestBody = {
    contents: [{
      parts: [{
        text: input,
      }],
    }],
    generationConfig: {
      temperature: 0.7,
      topK: 40,
      topP: 0.95,
      maxOutputTokens: 2048,
    },
  };

  const response = await fetch(`${url}?key=${apiKey}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    return input + "\nSomething went wrong";
  }

  const data = await response.json();
  const newText = data.candidates[0].content.parts[0].text;

  return input + newText;
}
