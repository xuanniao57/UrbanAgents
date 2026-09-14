import type { ResearchContract } from "../src/core/types.js";

export const CONTRACT: ResearchContract = {
  researchQuestion: "How sensitive are Shanghai street-vitality associations to spatial scale?",
  boundary: "Shanghai inner ring",
  observationWindow: "fixed two-day device-event sample",
  population: "observed anonymized device users",
  outcome: "log-transformed grid-level stay intensity",
  covariates: [
    "building_density", "building_coverage", "mean_height", "volume_proxy",
    "function_entropy", "poi_density", "poi_entropy", "road_density",
  ],
  candidateSupports: ["200 m", "300 m", "400 m", "500 m", "600 m", "700 m", "800 m"],
  intendedClaim: "Scale-conditioned predictive associations within the observed city and period.",
  prohibitedClaims: ["causal effect", "universal optimal scale", "population-wide representativeness"],
  crs: "EPSG:32651",
  gridOrigin: "shared 100 m-aligned origin",
  validationGeography: "five shared macro-regions",
};
