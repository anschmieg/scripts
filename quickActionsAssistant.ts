#!/usr/bin/env /Users/adrian/.deno/bin/deno run --allow-env --allow-read --allow-net

import { load } from "https://deno.land/std@0.210.0/dotenv/mod.ts";

async function readStdin(): Promise<string> {
  const decoder = new TextDecoder();
  let input = "";

  for await (const chunk of Deno.stdin.readable) {
    input += decoder.decode(chunk);
  }

  return input.trim();
}

async function run() {
  // Load environment variables from .env file
  const env = await load({
    export: true,
    allowEmptyValues: true,
    envPath: new URL(".env", import.meta.url).pathname, // Use absolute path
  });

  const input = await readStdin();

  const model = Deno.env.get("GOOGLE_AI_MODEL");
  const apiKey = Deno.env.get("GOOGLE_AI_API_KEY");
  console.error("Model:", model);
  console.error("API Key exists:", !!apiKey);

  if (!model || !apiKey) {
    return "Environment variables GOOGLE_AI_MODEL and GOOGLE_AI_API_KEY must be set";
  }

  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;

  const requestBody = {
    contents: [{
      parts: [{
        text:
          "You are a helpful assistant that completes sentences. Only provide the direct completion of the input text, without explanations or alternatives. Keep it concise and natural.\n\nInput:\n\n" +
          input,
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
    const errorText = await response.text();
    return `Error: ${response.status} ${response.statusText}\n${errorText}`;
  }

  const data = await response.json();
  const newText = data.candidates[0].content.parts[0].text;
  return `${input.trimEnd()} ${newText.trimEnd()}`;
}

run().then(console.log);
