// ============================================
// 백엔드 지역 데이터 API 연결
// ============================================

// 평가 항목별 점수 (0~100, 미수집 시 null)
export type RegionScores = {
  economy: number | null;
  energy: number | null;
  comfort: number | null;
  health: number | null;
  safety: number | null;
};

// 행정동 데이터
export type RegionData = {
  dongCode: string;
  dongName: string;
  district: string;
  scores: RegionScores;
  updatedAt?: string;
};

// 자치구 및 행정동 정보
export type ApiRegion = {
  region_code: string;
  name_ko: string;
  parent_region_code?: string;
  spatial_unit: "district" | "dong";
};

// 지역별 평가 점수
export type ApiScores = {
  economy: number;
  energy: number;
  comfort: number;
  health: number;
  safety: number;
};

// 지역 목록 API 응답
type RegionsResponse = {
  level: string;
  count: number;
  items: ApiRegion[];
  is_mock: boolean;
};

// 지역 점수 API 응답
export type ScoresResponse = {
  region: ApiRegion;
  scores: ApiScores;
  is_mock: boolean;
};

export type ScoreListResponse = {
  level: "district" | "dong";
  count: number;
  items: ScoresResponse[];
  is_mock: boolean;
  mock_domains: string[];
};

export function fetchScores(level: "district" | "dong") {
  return apiGet<ScoreListResponse>(`/api/scores?level=${level}`);
}

// 공통 API 요청 함수
async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`API 요청 실패: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// 서울 자치구 25개 조회
export function fetchDistricts() {
  return apiGet<RegionsResponse>("/api/regions");
}

// 서울 행정동 목록 조회
export function fetchDongs() {
  return apiGet<RegionsResponse>(
    "/api/regions?level=dong"
  );
}

// 특정 행정동의 5개 영역 점수 조회
export function fetchRegionScores(regionCode: string) {
  return apiGet<ScoresResponse>(
    `/api/regions/${encodeURIComponent(regionCode)}/scores`
  );
}
// 기존 컴포넌트 호환용: 새 백엔드 /api/scores 엔드포인트 사용
export function fetchDongScores() { return fetchScores("dong"); }
export const fetchAllDongScores = fetchDongScores;
