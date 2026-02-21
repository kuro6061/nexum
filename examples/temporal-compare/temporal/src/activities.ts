// Activities = pure functions, no workflow state access
export async function analyzeTopic(query: string): Promise<string> {
  // Simulates LLM call that sometimes returns broken JSON
  const responses = [
    `{"facts": ["LLM agents need durability", "crash recovery is critical"], "confidence": 0.9}`,
    `{"facts": ["event sourcing enables replay"  "idempotency prevents duplication"}, "confidence": 0.85`,  // intentionally broken
  ];
  await sleep(300);
  return responses[Math.floor(Math.random() * responses.length)];
}

export async function repairJson(brokenJson: string, originalQuery: string): Promise<string> {
  // Simulates LLM repair call
  await sleep(200);
  return `{"facts": ["repaired: ${originalQuery} requires durable execution"], "confidence": 0.75}`;
}

export async function extractFacts(validJson: string): Promise<string[]> {
  const parsed = JSON.parse(validJson);
  return parsed.facts ?? [];
}

export async function checkConfidence(validJson: string): Promise<number> {
  // V2 only: confidence check step
  const parsed = JSON.parse(validJson);
  return parsed.confidence ?? 0;
}

export async function generateReport(facts: string[], confidence: number): Promise<string> {
  await sleep(200);
  return `Report (confidence: ${confidence}): ${facts.join('; ')}`;
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
