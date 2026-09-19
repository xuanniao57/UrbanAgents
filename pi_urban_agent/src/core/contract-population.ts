/** Observation/sample scope, not a required population-count predictor. */
export function contractPopulation(source: Record<string, unknown>, proposed?: string): string {
  const text = (value: unknown) => typeof value === "string" ? value.trim() : "";
  const supplied = text(source.population) || [source.sampling, source.eligibility].map(text).filter(Boolean).join(" ");
  const population = supplied || text(proposed);
  if (!population) throw new Error("Read the data contract and supply population to urban_initialize: describe the observed population/sample scope, not a population-count variable. Do not invent sampling or eligibility rules.");
  return population;
}
