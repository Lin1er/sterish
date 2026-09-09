/**
 * Fixtures shaped exactly like `docs/api-spec.md` responses.
 *
 * Two reasons these exist even though the live API is already up:
 *
 * 1. The testnet registry currently holds only SAFE and DANGEROUS rows, so
 *    WARNING and UNAUDITED have no live example to build or review against.
 *    Every verdict the contract can hold is represented here.
 * 2. They make the dashboard developable with no network at all, and give the
 *    mock server under /api/mock something honest to serve.
 *
 * The skill ids are obviously fictional on purpose. Nothing here should ever be
 * mistaken for a real registry row, and none of it is served unless
 * NEXT_PUBLIC_API_URL is pointed at the mock.
 */

import type {
  Evidence,
  Health,
  SkillDetail,
  SkillList,
  VersionCheck,
} from "@/lib/types";

const REGISTRY_CONTRACT_ID =
  "CAPDQW2XWTOCFQEP3AUCRRQHVJ5IOUZ45DWPNPVG7USNPE6RZQ3BUXND";
const EXPLORER = "https://stellar.expert/explorer/testnet";

const OWNER = "GBRPYHIL2CI3FNQ4BXLFMNDLFJUNPU2HY3ZMFSHONUCEOASW7QC7OX2H";
const AUDITOR = "GCBYQKNSA4LQPYCPQTRIFCXKM3IVBLNPMDJUKPRIXPGHKUXFSMTLNMBK";

/**
 * Spec section 2 requires evidence on every verdict-bearing response, so the
 * fixtures carry it too. An unaudited version gets nulls for the audit half
 * rather than a plausible-looking fake hash: a fixture that invents evidence
 * teaches the UI to render something the chain never said.
 */
function evidence(opts: { audited: boolean; evidenceHash?: string }): Evidence {
  const registrationTx = "0".repeat(63) + "1";
  const auditTx = "0".repeat(63) + "2";
  return {
    registry_contract_id: REGISTRY_CONTRACT_ID,
    contract_url: `${EXPLORER}/contract/${REGISTRY_CONTRACT_ID}`,
    registration_tx: registrationTx,
    registration_tx_url: `${EXPLORER}/tx/${registrationTx}`,
    audit_tx: opts.audited ? auditTx : null,
    audit_tx_url: opts.audited ? `${EXPLORER}/tx/${auditTx}` : null,
    evidence_hash: opts.audited ? (opts.evidenceHash ?? "a".repeat(64)) : null,
    report_uri: null,
  };
}

/** Every version the mock knows about, keyed by `skill_id@version`. */
export const FIXTURE_VERSIONS: Record<string, VersionCheck> = {
  // SAFE, and the audited version is NOT the latest: exercises the section 3.3
  // warning path, the exact confusion the spec was rewritten to stop.
  "com.acme.pdf-suite@0.9.0": {
    skill_id: "com.acme.pdf-suite",
    version: "0.9.0",
    content_hash:
      "a67ded9f1b2c3d4e5f60718293a4b5c6d7e8f9012a3b4c5d6e7f8091a2b3c0d5",
    verdict: "SAFE",
    trust_score: 88,
    is_verified: true,
    owner: OWNER,
    auditor: AUDITOR,
    registered_at: 1756800000,
    audited_at: 1756810000,
    audited_at_iso: "2025-09-02T09:26:40Z",
    evidence: evidence({ audited: true }),
  },
  // The newer version of the same skill, never audited. Its verdict does not
  // inherit from 0.9.0: that inheritance was the scaffold bug STE-5 removed.
  "com.acme.pdf-suite@0.9.3": {
    skill_id: "com.acme.pdf-suite",
    version: "0.9.3",
    content_hash:
      "b78efe0a2c3d4e5f60718293a4b5c6d7e8f9012a3b4c5d6e7f8091a2b3c4d1e6",
    verdict: "UNAUDITED",
    trust_score: 0,
    is_verified: false,
    owner: OWNER,
    auditor: null,
    registered_at: 1756860000,
    audited_at: null,
    audited_at_iso: null,
    evidence: evidence({ audited: false }),
  },
  "com.evil.token-drainer@1.0.0": {
    skill_id: "com.evil.token-drainer",
    version: "1.0.0",
    content_hash:
      "c2bd4a316415b4919e3f1f40d9925f4052d020cf3dc2ecabe0e7c9dd28cc87f0",
    verdict: "DANGEROUS",
    trust_score: 5,
    is_verified: false,
    owner: OWNER,
    auditor: AUDITOR,
    registered_at: 1756890000,
    audited_at: 1756893600,
    audited_at_iso: "2025-09-03T09:20:00Z",
    evidence: evidence({ audited: true, evidenceHash: "c".repeat(64) }),
  },
  "com.contrib.csv-cleaner@2.1.0": {
    skill_id: "com.contrib.csv-cleaner",
    version: "2.1.0",
    content_hash:
      "d3ce5b427526c5a2af4e2f51ea036f5163e131da4ed3fdbcf1f8daee39dd98a1",
    verdict: "WARNING",
    trust_score: 61,
    is_verified: false,
    owner: OWNER,
    auditor: AUDITOR,
    registered_at: 1756900000,
    audited_at: 1756903600,
    audited_at_iso: "2025-09-03T12:06:40Z",
    evidence: evidence({ audited: true, evidenceHash: "d".repeat(64) }),
  },
  "com.newbie.hello-world@0.1.0": {
    skill_id: "com.newbie.hello-world",
    version: "0.1.0",
    content_hash:
      "e4df6c538637d6b3b05f3062fb14706274f242eb5fe40ecd0209ebff4aeea9b2",
    verdict: "UNAUDITED",
    trust_score: 0,
    is_verified: false,
    owner: OWNER,
    auditor: null,
    registered_at: 1756910000,
    audited_at: null,
    audited_at_iso: null,
    evidence: evidence({ audited: false }),
  },
};

export const FIXTURE_SKILLS: Record<string, SkillDetail> = {
  "com.acme.pdf-suite": {
    skill_id: "com.acme.pdf-suite",
    owner: OWNER,
    registered_at: 1756800000,
    versions: ["0.9.0", "0.9.3"],
    latest_version: "0.9.3",
    latest_audited_version: "0.9.0",
    audited_versions: [
      {
        version: "0.9.0",
        content_hash: FIXTURE_VERSIONS["com.acme.pdf-suite@0.9.0"].content_hash,
        verdict: "SAFE",
        trust_score: 88,
        is_verified: true,
        audited_at: 1756810000,
        evidence: evidence({ audited: true }),
      },
    ],
    warning:
      "latest_version 0.9.3 is NOT the audited version. A verdict applies to one version only.",
  },
  "com.evil.token-drainer": {
    skill_id: "com.evil.token-drainer",
    owner: OWNER,
    registered_at: 1756890000,
    versions: ["1.0.0"],
    latest_version: "1.0.0",
    latest_audited_version: "1.0.0",
    audited_versions: [
      {
        version: "1.0.0",
        content_hash:
          FIXTURE_VERSIONS["com.evil.token-drainer@1.0.0"].content_hash,
        verdict: "DANGEROUS",
        trust_score: 5,
        is_verified: false,
        audited_at: 1756893600,
        evidence: evidence({ audited: true, evidenceHash: "c".repeat(64) }),
      },
    ],
    warning: null,
  },
  "com.contrib.csv-cleaner": {
    skill_id: "com.contrib.csv-cleaner",
    owner: OWNER,
    registered_at: 1756900000,
    versions: ["2.1.0"],
    latest_version: "2.1.0",
    latest_audited_version: "2.1.0",
    audited_versions: [
      {
        version: "2.1.0",
        content_hash:
          FIXTURE_VERSIONS["com.contrib.csv-cleaner@2.1.0"].content_hash,
        verdict: "WARNING",
        trust_score: 61,
        is_verified: false,
        audited_at: 1756903600,
        evidence: evidence({ audited: true, evidenceHash: "d".repeat(64) }),
      },
    ],
    warning: null,
  },
  "com.newbie.hello-world": {
    skill_id: "com.newbie.hello-world",
    owner: OWNER,
    registered_at: 1756910000,
    versions: ["0.1.0"],
    latest_version: "0.1.0",
    // Never audited, so there is no audited version to point at. Null, not the
    // latest version wearing a hopeful UNAUDITED badge.
    latest_audited_version: null,
    audited_versions: [],
    warning: null,
  },
};

export const FIXTURE_SKILL_LIST: SkillList = {
  skills: [
    {
      skill_id: "com.acme.pdf-suite",
      owner: OWNER,
      registered_at: 1756800000,
      version_count: 2,
      latest_version: "0.9.3",
      latest_audited_version: "0.9.0",
      latest_audited_verdict: "SAFE",
      latest_audited_trust_score: 88,
      latest_audited_is_verified: true,
    },
    {
      skill_id: "com.evil.token-drainer",
      owner: OWNER,
      registered_at: 1756890000,
      version_count: 1,
      latest_version: "1.0.0",
      latest_audited_version: "1.0.0",
      latest_audited_verdict: "DANGEROUS",
      latest_audited_trust_score: 5,
      latest_audited_is_verified: false,
    },
    {
      skill_id: "com.contrib.csv-cleaner",
      owner: OWNER,
      registered_at: 1756900000,
      version_count: 1,
      latest_version: "2.1.0",
      latest_audited_version: "2.1.0",
      latest_audited_verdict: "WARNING",
      latest_audited_trust_score: 61,
      latest_audited_is_verified: false,
    },
    {
      skill_id: "com.newbie.hello-world",
      owner: OWNER,
      registered_at: 1756910000,
      version_count: 1,
      latest_version: "0.1.0",
      latest_audited_version: null,
      latest_audited_verdict: null,
      latest_audited_trust_score: null,
      latest_audited_is_verified: null,
    },
  ],
  total: 4,
  start: 0,
  limit: 20,
};

export const FIXTURE_HEALTH: Health = {
  status: "ok",
  version: "1.0.0-mock",
  network: "testnet",
  registry_contract_id: REGISTRY_CONTRACT_ID,
  rpc_url: "https://soroban-testnet.stellar.org",
  rpc_reachable: true,
  indexer_lag_ledgers: 0,
  facilitator_reachable: true,
};

/** Spec section 3.1 resolves bytes to a version, so the mock needs that index. */
export const FIXTURE_BY_HASH: Record<string, VersionCheck> = Object.fromEntries(
  Object.values(FIXTURE_VERSIONS).map((v) => [v.content_hash, v]),
);
