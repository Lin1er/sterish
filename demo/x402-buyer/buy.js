// Demo buyer: an agent with no licence pays for one over x402 and gets the skill.
//
// The agent holds USDC but needs no XLM — the OZ Channels facilitator sponsors
// network fees, and the client signs Soroban auth entries rather than a full
// transaction envelope.
//
//   STERISH_API   base URL of the Sterish API      (default http://127.0.0.1:8000)
//   AGENT_SECRET  S... secret of the buying agent  (needs USDC + a trustline)
//   SKILL_ID / SKILL_VERSION  what to buy
import { x402Client, x402HTTPClient } from "@x402/fetch";
import { createEd25519Signer } from "@x402/stellar";
import { ExactStellarScheme } from "@x402/stellar/exact/client";

const API = process.env.STERISH_API ?? "http://127.0.0.1:8000";
const NETWORK = "stellar:testnet";
const RPC = process.env.STELLAR_RPC_URL ?? "https://soroban-testnet.stellar.org";
const SKILL = process.env.SKILL_ID;
const VERSION = process.env.SKILL_VERSION ?? "1.0.0";

if (!process.env.AGENT_SECRET) throw new Error("AGENT_SECRET is required");
if (!SKILL) throw new Error("SKILL_ID is required");

const signer = createEd25519Signer(process.env.AGENT_SECRET, NETWORK);
const client = new x402Client().register(
  "stellar:*",
  new ExactStellarScheme(signer, { url: RPC }),
);
const http = new x402HTTPClient(client);
const url = `${API}/use/${SKILL}/${VERSION}`;
const agentHeaders = { "X-AGENT-ADDRESS": signer.address };

console.log(`agent   ${signer.address}`);
console.log(`target  ${url}\n`);

// 1. No licence, no payment -> 402 with the requirements.
const first = await fetch(url, { headers: agentHeaders });
console.log(`1. unpaid request        -> ${first.status}`);
if (first.status !== 402) {
  console.log("   expected 402; body:", await first.text());
  process.exit(1);
}

const required = http.getPaymentRequiredResponse((n) => first.headers.get(n));
const accepts = required.accepts[0];
console.log(`   price ${accepts.amount} base units of ${accepts.asset.slice(0, 8)}…`);
console.log(`   payTo ${accepts.payTo}`);

// 2. Build and sign the payment, then retry.
const payload = await client.createPaymentPayload(required);
const header = Buffer.from(JSON.stringify(payload)).toString("base64");

const paid = await fetch(url, { headers: { ...agentHeaders, "X-PAYMENT": header } });
console.log(`\n2. paid request          -> ${paid.status}`);
if (paid.status !== 200) {
  console.log("   body:", await paid.text());
  process.exit(1);
}
console.log(`   licence   ${paid.headers.get("X-STERISH-LICENSE")}`);
console.log(`   mint tx   ${paid.headers.get("X-STERISH-LICENSE-TX")}`);

// 3. The licence is on chain now, so the next call is free.
const again = await fetch(url, { headers: agentHeaders });
console.log(`\n3. second request (free) -> ${again.status}`);
console.log(`   licence   ${again.headers.get("X-STERISH-LICENSE")}`);
if (again.status !== 200 || again.headers.get("X-STERISH-LICENSE") !== "held") {
  console.log("   expected a held licence and no payment");
  process.exit(1);
}
console.log("\nOK: 402 -> pay -> licence minted -> 200, and the repeat call paid nothing.");
