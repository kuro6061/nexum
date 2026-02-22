# @nexum/sdk

TypeScript SDK for [Nexum](https://github.com/kuro6061/nexum) — Durable Execution Engine for LLM Agents.

## Install

```bash
npm install @nexum/sdk
# or
pnpm add @nexum/sdk
```

## Quick Start

```typescript
import { workflow, worker } from "@nexum/sdk";
import { z } from "zod";

const SearchResult = z.object({ content: z.string() });

const myWorkflow = workflow("ResearchAgent")
  .effect("search", SearchResult, async (ctx, io) => {
    return await io.call(mySearchTool, ctx.input.query);
  })
  .compute("summarize", z.string(), (ctx) => {
    return ctx.get("search").content.slice(0, 500);
  })
  .build();

// Start the worker (connects to Nexum server)
const w = worker({ serverAddress: "localhost:50051" });
w.register(myWorkflow);
await w.start();
```

Requires a running [Nexum server](https://github.com/kuro6061/nexum). Start locally with:

```bash
npx @nexum/cli dev
```

## License

MIT
