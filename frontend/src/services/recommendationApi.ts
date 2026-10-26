/**
 * 서울 Smart Life 실데이터 추천 API 클라이언트.
 * 기존 regionApi.ts(Mock 호환 API)는 변경하지 않습니다.
 * Vite의 /api -> 127.0.0.1:8000 프록시 설정을 그대로 사용합니다.
 */
const API_BASE = "/api/recommendation";

export type Domain = "economy" | "energy" | "comfort" | "health" | "safety";
export type DomainScores = Record<Domain, number | null>;
export type SliderWeights = Record<Domain, number>;
export const DEFAULT_WEIGHTS: SliderWeights = {
  economy: 20, energy: 20, comfort: 20, health: 20, safety: 20,
};

export interface RecommendationStatus {
  database: "ready";
  active_release: { release_id: string; [key: string]: unknown };
  available_domains: Domain[];
  warnings: unknown[];
  is_mock: boolean;
  [key: string]: unknown;
}

export interface RealRegion {
  /** 실제 추천 API의 6자리 행정동 코드 */
  region_code: string;
  region_name: string;
  /** 자치구 5자리 코드 */
  sigungu_code: string;
  sigungu_name: string;
  /** 지도 GeoJSON 매핑 키. null일 수 있음 */
  geometry_key: string | null;
  category_scores: DomainScores;
  personalized_score_100?: number | null;
  safety_grade?: number | null;
}

export interface ScoreList {
  snapshot_version: string;
  target_month: string;
  count: number;
  items: RealRegion[];
  available_domains: Domain[];
  warnings: unknown[];
  is_mock: boolean;
}

export interface DistrictScore {
  sigungu_code: string;
  sigungu_name: string;
  category_scores: DomainScores;
  personalized_score_100: number | null;
  region_count: number;
  valid_region_counts: Record<Domain, number>;
}

export interface DistrictList {
  snapshot_version: string;
  target_month: string;
  items: DistrictScore[];
  warnings: unknown[];
  is_mock: boolean;
}

export interface RealRegionList {
  snapshot_version: string;
  count: number;
  items: Pick<RealRegion, "region_code" | "region_name" | "sigungu_code" | "sigungu_name" | "geometry_key">[];
  is_mock: boolean;
}

export class RecommendationApiError extends Error {
  public readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "RecommendationApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  if (!response.ok) {
    let detail = "";
    try { detail = JSON.stringify((await response.json()).detail ?? ""); } catch { /* 응답 본문이 JSON이 아닐 수 있음 */ }
    throw new RecommendationApiError(response.status, `추천 API 오류 (${response.status}) ${detail}`.trim());
  }
  return (await response.json()) as T;
}

function query(args: Record<string, string | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(args).forEach(([key, value]) => { if (value !== undefined) params.set(key, value); });
  const result = params.toString();
  return result ? `?${result}` : "";
}

/** 서버와 DB 활성 배포본 확인. DB 준비 전에는 503을 정상적인 준비 실패로 처리 */
export function fetchRecommendationStatus() {
  return request<RecommendationStatus>("/status");
}

/** 행정동 전체 실데이터 점수. snapshot_version을 뒤이은 요청의 release_id로 전달 */
export function fetchRealScores(options: { sigunguCode?: string; releaseId?: string; weights?: SliderWeights } = {}) {
  return request<ScoreList>(`/scores${query({
    sigungu_code: options.sigunguCode,
    release_id: options.releaseId,
    weights: options.weights ? JSON.stringify(options.weights) : undefined,
  })}`);
}

/** 자치구별 평균 점수 */
export function fetchRealDistricts(options: { releaseId?: string; weights?: SliderWeights } = {}) {
  return request<DistrictList>(`/districts${query({
    release_id: options.releaseId,
    weights: options.weights ? JSON.stringify(options.weights) : undefined,
  })}`);
}

/** 6자리 행정동 코드와 지도 geometry_key 매핑에 사용할 명부 */
export function fetchRealRegions(options: { sigunguCode?: string; releaseId?: string } = {}) {
  return request<RealRegionList>(`/regions${query({
    sigungu_code: options.sigunguCode,
    release_id: options.releaseId,
  })}`);
}

export interface RecommendationResponse {
  snapshot_version: string;
  rank_scope: "seoul" | "sigungu";
  sigungu_code: string | null;
  recommendation: unknown;
  map_scores: { region_code: string; personalized_score_100: number | null }[];
}

/** TOP 5까지만 지원 (TOP 10 UI는 전체 점수 조회로 정렬해야 함) */
export function fetchRecommendations(weights: SliderWeights, options: { sigunguCode?: string; releaseId?: string; topK?: 1 | 2 | 3 | 4 | 5 } = {}) {
  return request<RecommendationResponse>("/recommendations", {
    method: "POST",
    body: JSON.stringify({
      weights,
      top_k: options.topK ?? 5,
      ...(options.sigunguCode ? { sigungu_code: options.sigunguCode } : {}),
      ...(options.releaseId ? { release_id: options.releaseId } : {}),
    }),
  });
}

// 행정동 AI 설명 요청
export interface RegionExplanation {
  region_code: string;
  region_name: string;
  advantages: string;
  disadvantages: string;
  limitations: string[];
}

export interface ExplanationResponse {
  snapshot_version: string;
  rank_scope: "seoul" | "sigungu" | "selected_regions";
  explanation: {
    generation_status: "llm" | "fallback" | "empty";
    snapshot_version: string;
    warnings: string[];
    diagnostics: unknown[];
    items: RegionExplanation[];
  };
}

export async function fetchAIExplanation(
  regionCode: string,
  weights: SliderWeights,
  options: { releaseId?: string; sigunguCode?: string; signal?: AbortSignal } = {}
) {
  const result = await request<ExplanationResponse>("/explanations", {
    method: "POST",
    signal: options.signal,
    body: JSON.stringify({
      region_codes: [regionCode],
      weights,
      ...(options.releaseId ? { release_id: options.releaseId } : {}),
      ...(options.sigunguCode ? { sigungu_code: options.sigunguCode } : {}),
    }),
  });
  // TypeScript types do not validate network data. Reject stale/wrong-region prose.
  const explanation = result?.explanation;
  if (!explanation || !["llm", "fallback", "empty"].includes(explanation.generation_status) ||
      !Array.isArray(explanation.items) || typeof result.snapshot_version !== "string" ||
      explanation.snapshot_version !== result.snapshot_version ||
      (options.releaseId && result.snapshot_version !== options.releaseId)) {
    throw new Error("AI 설명 응답의 형식 또는 데이터 버전이 일치하지 않습니다.");
  }
  const items = explanation.items;
  if (explanation.generation_status === "empty" ? items.length !== 0 :
      items.length !== 1 || items[0]?.region_code !== regionCode ||
      typeof items[0]?.region_name !== "string" ||
      typeof items[0]?.advantages !== "string" || !items[0].advantages.trim() ||
      typeof items[0]?.disadvantages !== "string" || !items[0].disadvantages.trim() ||
      !Array.isArray(items[0]?.limitations) || !items[0].limitations.every(value => typeof value === "string")) {
    throw new Error("선택한 지역과 AI 설명 응답이 일치하지 않거나 설명이 올바르지 않습니다.");
  }
  return result;
}
