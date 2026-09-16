"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import { ApiError, requestSkill, type UseOutcome } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { PaymentRequired, PaymentRequirement } from "@/lib/types";
import {
  classifyPaymentFailure,
  createPaymentHeader,
  readTokenBalance,
  selectRequirement,
  type PaymentFailure,
} from "@/lib/x402";

/**
 * The 402, pay, 200 loop for one version, as a state machine the card renders.
 *
 * Each step is a state of its own because each is a different thing to tell
 * the buyer: "asking", "here is the price", "sign in your wallet", "settling
 * and minting". Collapsing them into one spinner would hide the one moment
 * that matters most, which is the gap between signing and the answer, when
 * money may already have moved.
 */
export type PurchaseState =
  | { step: "idle" }
  | { step: "requesting" }
  | {
      step: "quoted";
      paymentRequired: PaymentRequired;
      requirement: PaymentRequirement;
      /** Base units, null when the read failed, undefined while it is running. */
      balance: bigint | null | undefined;
    }
  | { step: "signing"; requirement: PaymentRequirement }
  | { step: "settling"; requirement: PaymentRequirement }
  | { step: "granted"; outcome: Extract<UseOutcome, { kind: "granted" }> }
  | {
      step: "failed";
      error: ApiError | PaymentFailure;
      /** Where it failed. After a signature, money may have moved. */
      after: "request" | "signature" | "payment";
    };

export function usePurchase(
  skillId: string,
  version: string,
  agent: string | null,
) {
  const [state, setState] = useState<PurchaseState>({ step: "idle" });
  const queryClient = useQueryClient();
  // Guards against a double click sending two signed payments. State updates
  // are not synchronous enough to do this on their own.
  const inFlight = useRef(false);
  // Bumped by cancel. A wallet prompt cannot be withdrawn, so a signature can
  // still arrive after the buyer gave up waiting; comparing generations is what
  // stops that late signature from being sent as a payment nobody wanted.
  const generation = useRef(0);

  const refreshLicence = useCallback(() => {
    if (!agent) return;
    void queryClient.invalidateQueries({
      queryKey: queryKeys.licence(skillId, version, agent),
    });
  }, [agent, queryClient, skillId, version]);

  /** Ask for the skill without paying. Serves a held licence, or quotes a price. */
  const start = useCallback(async () => {
    if (!agent || inFlight.current) return;
    inFlight.current = true;
    setState({ step: "requesting" });
    try {
      const outcome = await requestSkill(skillId, version, { agent });
      if (outcome.kind === "granted") {
        setState({ step: "granted", outcome });
        refreshLicence();
        return;
      }

      const requirement = selectRequirement(outcome.paymentRequired);
      if (!requirement) {
        setState({
          step: "failed",
          after: "request",
          error: {
            kind: "failed",
            message:
              "The API asked for payment on a network or in a scheme this dashboard does not pay with, so nothing was offered for signing.",
          },
        });
        return;
      }

      setState({
        step: "quoted",
        paymentRequired: outcome.paymentRequired,
        requirement,
        balance: undefined,
      });
      const balance = await readTokenBalance(requirement.asset, agent);
      setState((current) =>
        current.step === "quoted" && current.requirement === requirement
          ? { ...current, balance }
          : current,
      );
    } catch (cause) {
      if (!(cause instanceof ApiError)) throw cause;
      setState({ step: "failed", after: "request", error: cause });
    } finally {
      inFlight.current = false;
    }
  }, [agent, refreshLicence, skillId, version]);

  /** Sign the quoted payment in the wallet, then send it. */
  const pay = useCallback(async () => {
    if (!agent || inFlight.current || state.step !== "quoted") return;
    inFlight.current = true;
    const { paymentRequired, requirement } = state;
    const mine = ++generation.current;

    setState({ step: "signing", requirement });
    let header: string;
    try {
      header = await createPaymentHeader(paymentRequired, agent);
      if (generation.current !== mine) {
        inFlight.current = false;
        return;
      }
    } catch (cause) {
      if (generation.current !== mine) {
        inFlight.current = false;
        return;
      }
      // Nothing has been sent yet: a failure here never moved money.
      setState({
        step: "failed",
        after: "signature",
        error: classifyPaymentFailure(cause),
      });
      inFlight.current = false;
      return;
    }

    setState({ step: "settling", requirement });
    try {
      const outcome = await requestSkill(skillId, version, {
        agent,
        payment: header,
      });
      if (outcome.kind === "granted") {
        setState({ step: "granted", outcome });
      } else {
        // Cannot happen: requestSkill only returns a challenge when no payment
        // was attached. Treated as a failure rather than a second price.
        setState({
          step: "failed",
          after: "payment",
          error: {
            kind: "failed",
            message:
              "The API asked for payment again after a payment was sent.",
          },
        });
      }
    } catch (cause) {
      if (!(cause instanceof ApiError)) throw cause;
      setState({ step: "failed", after: "payment", error: cause });
    } finally {
      // Whatever happened after a signed payment went out, the licence may
      // have changed, so the status above the flow is re-read.
      refreshLicence();
      inFlight.current = false;
    }
  }, [agent, refreshLicence, skillId, state, version]);

  /**
   * Read the balance again while the quote is on screen. The testnet setup
   * guide calls this after funding, trusting and topping up, so the quote
   * does not keep saying "unavailable" about an account that is now ready.
   */
  const refreshBalance = useCallback(async () => {
    if (!agent || state.step !== "quoted") return;
    const { requirement } = state;
    setState((current) =>
      current.step === "quoted" ? { ...current, balance: undefined } : current,
    );
    const balance = await readTokenBalance(requirement.asset, agent);
    setState((current) =>
      current.step === "quoted" && current.requirement === requirement
        ? { ...current, balance }
        : current,
    );
  }, [agent, state]);

  const reset = useCallback(() => {
    generation.current += 1;
    inFlight.current = false;
    setState({ step: "idle" });
  }, []);

  return { state, start, pay, reset, refreshBalance };
}
