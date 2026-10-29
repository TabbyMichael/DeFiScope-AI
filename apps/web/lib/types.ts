// API domain types derived from the generated OpenAPI contract
// (services/api/openapi.json -> lib/api-types.ts via `npm run gen:types`).
// Do NOT hand-mirror the backend here: add fields to the FastAPI/Pydantic
// schema, regenerate openapi.json, then run `npm run gen:types`.

import type { components } from "./api-types";

type Schemas = components["schemas"];

/**
 * Make every property (recursively, incl. array elements) required.
 *
 * Pydantic response models expose defaulted fields as OpenAPI-optional, but our
 * API always serializes them at runtime. This keeps the ergonomic non-optional
 * shape the UI already depends on without hand-writing the struct again.
 * Nullable fields (`T | null`) stay nullable; only the "missing" state is
 * removed.
 */
type DeepRequired<T> = T extends Array<infer U>
  ? Array<DeepRequired<U>>
  : T extends object
    ? { [K in keyof T]-?: DeepRequired<T[K]> }
    : T;

export type TvlPoint = DeepRequired<Schemas["TvlPoint"]>;
export type ProtocolOverview = DeepRequired<Schemas["ProtocolOverview"]>;
export type ChainShare = DeepRequired<Schemas["ChainShare"]>;
export type RiskIndicator = DeepRequired<Schemas["RiskIndicatorOut"]>;
export type RiskAssessment = DeepRequired<Schemas["RiskAssessmentOut"]>;
export type ProtocolResearch = DeepRequired<Schemas["ProtocolResearch"]>;
export type Alert = DeepRequired<Schemas["Alert"]>;
export type BriefSections = DeepRequired<Schemas["BriefSection"]>;
export type ResearchBrief = DeepRequired<Schemas["ResearchBrief"]>;
export type Mover = DeepRequired<Schemas["Mover"]>;
export type DashboardStats = DeepRequired<Schemas["DashboardStats"]>;
export type DashboardResponse = DeepRequired<Schemas["DashboardResponse"]>;

