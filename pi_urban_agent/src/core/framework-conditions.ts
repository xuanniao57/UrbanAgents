/** Versioned independently from the historical single-session ablations. */
export const FOUR_CONDITIONS = {
  urban_full_v2: { delegation: true, memory: true },
  urban_single_v2: { delegation: false, memory: true },
  urban_no_memory_v2: { delegation: true, memory: false },
  pi_native_v2: { delegation: false, memory: false },
} as const;
export type FourCondition = keyof typeof FOUR_CONDITIONS;
export function fourCondition(value: string) {
  return FOUR_CONDITIONS[value as FourCondition];
}
export function roleInstruction(role: string, delegation: boolean): string {
  if (role === "reviewer") return "You are an independent Reviewer in a fresh session. Inspect the assignment, human constraints, source code and actual artifacts. Report findings with file evidence and suggested repairs. Do not treat the Worker's explanation as verification. Do not grant human authorization or perform new scientific analyses. Save your review under outputs/.";
  if (role === "worker") return "You are a Worker in a fresh session. Execute only the delegated assignment within the human constraints. Save code, results and execution evidence. Do not grant human authorization or describe your self-check as independent review.";
  return delegation
    ? "You coordinate the research and communicate with the human. You may perform tasks yourself or use urban_delegate for a bounded Worker or independent Reviewer assignment when useful. Delegation is optional; a review can cover multiple artifacts. Pass relevant human constraints and evidence paths explicitly. Do not pass private reasoning or the entire conversation."
    : "You conduct the research and communicate with the human. Plan, execute and inspect results in this session. Do not claim an independent agent review occurred.";
}
