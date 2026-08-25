"use client";
import { RequireAuth } from "@/components/RequireAuth";
import { Planned } from "@/components/Planned";

export default function Page() {
  return (
    <RequireAuth roles={["super_admin","finance","content","data_ml","support"]}>
      <Planned
        title="Item bank"
        sub="Authoring, versioning and staged rollout of simulation items."
        milestone="M6"
        what="Includes the guardrail that blocks verbatim vendor items — the item bank is -style content by design, and that check ships with the authoring tools."
      />
    </RequireAuth>
  );
}
