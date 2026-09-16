// Prove to Sterish that this agent controls the address holding a licence (STE-48).
//
// A licence holder is served for free, but holders are public on chain, so the API
// asks for a signature over a single-use challenge before it hands the bytes over:
//
//   1. GET /use/<skill>/<version>/challenge?agent=G...   -> { nonce, message, ... }
//   2. sign `message` with SEP-53: ed25519 over SHA-256("Stellar Signed Message:\n" + message)
//      (the same bytes `stellar message sign` and a wallet's SEP-43 signMessage sign)
//   3. repeat GET /use with X-AGENT-ADDRESS, X-STERISH-PROOF-NONCE, X-STERISH-PROOF-SIGNATURE
//
// As a module: `proofHeaders({ api, skillId, version, secret })` returns the headers.
// As a script, it fetches a skill you already hold:
//
//   STERISH_API=https://api-sterish.jameshub.fun AGENT_SECRET=S... \
//   SKILL_ID=org.stellar.skills.dapp.react SKILL_VERSION=2026.8.31 node prove.js
//
// The secret is only ever read from the environment and never printed.
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";
import { Keypair } from "@stellar/stellar-sdk";

const SEP53_PREFIX = "Stellar Signed Message:\n";

export function sep53Sign(keypair, message) {
  const digest = createHash("sha256").update(SEP53_PREFIX + message, "utf8").digest();
  return keypair.sign(digest).toString("base64");
}

export async function proofHeaders({ api, skillId, version, secret }) {
  const keypair = Keypair.fromSecret(secret);
  const agent = keypair.publicKey();
  const url = `${api}/use/${skillId}/${version}/challenge?agent=${agent}`;
  const response = await fetch(url);
  if (response.status !== 200) {
    throw new Error(`challenge request failed: ${response.status} ${await response.text()}`);
  }
  const challenge = await response.json();
  return {
    "X-AGENT-ADDRESS": agent,
    "X-STERISH-PROOF-NONCE": challenge.nonce,
    "X-STERISH-PROOF-SIGNATURE": sep53Sign(keypair, challenge.message),
  };
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const api = process.env.STERISH_API ?? "http://127.0.0.1:8000";
  const skillId = process.env.SKILL_ID;
  const version = process.env.SKILL_VERSION ?? "1.0.0";
  if (!process.env.AGENT_SECRET) throw new Error("AGENT_SECRET is required");
  if (!skillId) throw new Error("SKILL_ID is required");

  const headers = await proofHeaders({ api, skillId, version, secret: process.env.AGENT_SECRET });
  const response = await fetch(`${api}/use/${skillId}/${version}`, { headers });
  const body = await response.text();
  console.log(`agent   ${headers["X-AGENT-ADDRESS"]}`);
  console.log(`status  ${response.status}`);
  console.log(`licence ${response.headers.get("X-STERISH-LICENSE")}`);
  if (response.status !== 200) {
    console.log(body);
    process.exit(1);
  }
  process.stdout.write(`${body}\n`);
}
