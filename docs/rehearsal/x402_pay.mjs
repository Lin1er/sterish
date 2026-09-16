// One x402 purchase against GET /use, reported as JSON on stdout.
//
// Called by run_rehearsal.py, which pipes this file into
// `node --input-type=module` with demo/x402-buyer as the working directory, so
// the bare imports below resolve against that package's node_modules without
// this file needing a package of its own.
//
// Unlike demo/x402-buyer/buy.js it never decides pass or fail and never exits
// early: it records what each request returned, including the failures, and
// leaves the verdict to the caller. The agent secret arrives in AGENT_SECRET and
// is never echoed; only the public address is printed.
//
//   STERISH_API, AGENT_SECRET, SKILL_ID, SKILL_VERSION, STELLAR_RPC_URL
//   MODE = "buy"  -> unpaid request, then pay and retry (steps 4)
//   MODE = "held" -> one request carrying only X-AGENT-ADDRESS (step 5)
import { x402Client, x402HTTPClient } from "@x402/fetch";
import { createEd25519Signer } from "@x402/stellar";
import { ExactStellarScheme } from "@x402/stellar/exact/client";

const API = process.env.STERISH_API;
const RPC = process.env.STELLAR_RPC_URL ?? "https://soroban-testnet.stellar.org";
const NETWORK = "stellar:testnet";
const SKILL = process.env.SKILL_ID;
const VERSION = process.env.SKILL_VERSION;
const MODE = process.env.MODE ?? "buy";

const signer = createEd25519Signer(process.env.AGENT_SECRET, NETWORK);
const url = `${API}/use/${SKILL}/${VERSION}`;
const agentHeaders = { "X-AGENT-ADDRESS": signer.address };
const out = { agent: signer.address, url, mode: MODE, requests: [] };

async function record(label, response) {
  const text = await response.text();
  const pick = (name) => response.headers.get(name);
  const entry = {
    label,
    status: response.status,
    license: pick("X-STERISH-LICENSE"),
    license_tx: pick("X-STERISH-LICENSE-TX"),
    payment_required: Boolean(pick("PAYMENT-REQUIRED")),
    payment_response: null,
    body_excerpt: text.slice(0, 400),
    body_bytes: text.length,
  };
  const receipt = pick("X-PAYMENT-RESPONSE");
  if (receipt) {
    try {
      entry.payment_response = JSON.parse(Buffer.from(receipt, "base64").toString("utf8"));
    } catch {
      entry.payment_response = { undecodable: receipt.slice(0, 80) };
    }
  }
  out.requests.push(entry);
  return entry;
}

try {
  if (MODE === "held") {
    await record("held", await fetch(url, { headers: agentHeaders }));
  } else {
    const first = await fetch(url, { headers: agentHeaders });
    const firstHeaders = first.headers;
    const unpaid = await record("unpaid", first);
    if (unpaid.status === 402) {
      const client = new x402Client().register("stellar:*", new ExactStellarScheme(signer, { url: RPC }));
      const required = new x402HTTPClient(client).getPaymentRequiredResponse((n) => firstHeaders.get(n));
      out.accepts = required.accepts[0];
      const payload = await client.createPaymentPayload(required);
      const header = Buffer.from(JSON.stringify(payload)).toString("base64");
      await record("paid", await fetch(url, { headers: { ...agentHeaders, "X-PAYMENT": header } }));
    }
  }
} catch (err) {
  out.error = String(err && err.stack ? err.stack.split("\n")[0] : err);
}

console.log(JSON.stringify(out));
