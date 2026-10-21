
import { useEffect, useMemo, useState } from "react";
import SeoulMap from "./SeoulMap";
import "../CSS/MainPage.css";
import { fetchDongScores } from "../services/regionApi";

// ==========================================
// 1. 기본 설정
// ==========================================

// 기존 자치구 점수 데이터
// 행정동 색상은 dongScores를 통해 별도로 전달
const regionScores: { district: string; score: number }[] = [];

// 메인페이지 기본 가중치
// 상세분석에서 설정한 기본 가중치와 동일
const DEFAULT_WEIGHTS = {
  economy: 20,
  energy: 15,
  comfort: 25,
  health: 20,
  safety: 20,
};

// 지도에 전달할 행정동 점수 타입
type DongMapScore = {
  dongCode: string;
  score: number;
};

// 백엔드 API 데이터의 필드 형태
type ApiDongScore = {
  dongCode?: string;
  dong_code?: string;
  region_code?: string;
  code?: string;
  score?: number | null;
  total_score?: number | null;
  overall_score?: number | null;
  scores?: Record<string, unknown>;
};

// [추가] 오른쪽 자치구 순위 패널의 평가 항목
const RANK_METRICS = [
  { key: "overall", label: "종합점수" },
  { key: "economy", label: "경제 활력도" },
  { key: "energy", label: "에너지 소비효율" },
  { key: "comfort", label: "생활 쾌적도" },
  { key: "health", label: "건강 안전도" },
  { key: "safety", label: "치안 안전도" },
] as const;

type RankMetric = (typeof RANK_METRICS)[number]["key"];
type DistrictRanking = { district: string; score: number; count: number };

// [추가] 점수 데이터의 가능한 배열 포맷을 추출
function getScoreItems(response: unknown): ApiDongScore[] {
  if (Array.isArray(response)) return response as ApiDongScore[];
  if (!response || typeof response !== "object") return [];
  const root = response as Record<string, unknown>;
  const items = root.items ?? root.data ?? root.scores;
  return Array.isArray(items) ? (items as ApiDongScore[]) : [];
}

// [추가] 자치구 순위용 행정동 점수 조회 (자료가 없으면 계산하지 않음)
function metricScore(item: ApiDongScore, metric: RankMetric): number | null {
  if (metric === "overall") {
    if (item.scores && typeof item.scores === "object") {
      const calculated = calculateScore(item.scores);
      if (calculated !== null) return calculated;
    }
    const raw = item.score ?? item.total_score ?? item.overall_score;
    return typeof raw === "number" && Number.isFinite(raw) && raw >= 0 && raw <= 100
      ? raw : null;
  }
  const value = item.scores?.[metric];
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100
    ? value : null;
}

// 부모 컴포넌트에서 전달받는 데이터 타입
type MainPageProps = {
  selectedDistrict: string | null;
  onDistrictClick: (district: string) => void;
  onDistrictDoubleClick: (district: string) => void;
};

// ==========================================
// 2. 백엔드 점수 계산 함수
// ==========================================

// 5개 항목 점수로 가중평균 계산
function calculateScore(
  scores: Record<string, unknown>
): number | null {
  const keys = [
    "economy",
    "energy",
    "comfort",
    "health",
    "safety",
  ] as const;

  const totalWeight = Object.values(DEFAULT_WEIGHTS).reduce(
    (sum, weight) => sum + weight,
    0
  );

  if (totalWeight === 0) return null;

  let weightedSum = 0;

  for (const key of keys) {
    const value = scores[key];

    // 점수가 누락된 행정동은 계산하지 않음
    if (
      typeof value !== "number" ||
      !Number.isFinite(value) ||
      value < 0 ||
      value > 100
    ) {
      return null;
    }

    weightedSum += value * DEFAULT_WEIGHTS[key];
  }

  return weightedSum / totalWeight;
}

// ==========================================
// 3. 백엔드 응답을 지도 데이터로 변환
// ==========================================

// 응답 형태가 배열이거나 {items: []}인 경우 처리
function normalizeDongScores(response: unknown): DongMapScore[] {
  let items: unknown[] = [];

  if (Array.isArray(response)) {
    items = response;
  } else if (
    response !== null &&
    typeof response === "object"
  ) {
    const result = response as Record<string, unknown>;

    if (Array.isArray(result.items)) {
      items = result.items;
    } else if (Array.isArray(result.data)) {
      items = result.data;
    } else if (Array.isArray(result.scores)) {
      items = result.scores;
    }
  }

  const dongScores: DongMapScore[] = [];

  for (const item of items) {
    if (!item || typeof item !== "object") continue;

    const dong = item as ApiDongScore;

    // GeoJSON adm_cd2와 매칭할 행정동 코드
    const dongCode = String(
      dong.dongCode ??
      dong.dong_code ??
      dong.region_code ??
      dong.code ??
      ""
    );

    if (!dongCode) continue;

    // 개별 평가 점수 데이터 확인
    const scores = dong.scores;

    // 5개 항목이 있으면 기본 가중치로 계산
    let score: number | null =
      scores && typeof scores === "object"
        ? calculateScore(scores)
        : null;

    // 이미 백엔드에서 계산한 종합점수가 있으면 사용
    if (score === null) {
      const total =
        dong.score ??
        dong.total_score ??
        dong.overall_score;

      if (
        typeof total === "number" &&
        Number.isFinite(total) &&
        total >= 0 &&
        total <= 100
      ) {
        score = total;
      }
    }

    if (score === null) continue;

    dongScores.push({
      dongCode,
      score,
    });
  }

  return dongScores;
}

// ==========================================
// 4. 메인페이지
// ==========================================

export default function MainPage({
  selectedDistrict,
  onDistrictClick,
  onDistrictDoubleClick,
}: MainPageProps) {

  // 백엔드에서 가져온 행정동별 종합점수
  const [dongScores, setDongScores] = useState<DongMapScore[]>([]);

  // API 요청 진행 상태
  const [isLoading, setIsLoading] = useState(true);

  // API 오류 메시지
  const [apiError, setApiError] = useState<string | null>(null);

  // [추가] 순위용 원본 점수/GeoJSON 지역명 매핑/선택 지표
  const [rankSource, setRankSource] = useState<unknown>(null);
  const [dongDistrictMap, setDongDistrictMap] = useState<Record<string, string>>({});
  const [rankMetric, setRankMetric] = useState<RankMetric>("overall");

  // [추가] 기존 지도에서 쓰는 GeoJSON의 자치구 이름을 사용해 코드 일치 여부 확인
  useEffect(() => {
    const controller = new AbortController();
    fetch("/data/seoul_dong.geojson", { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`행정동 GeoJSON 로드 실패: ${r.status}`);
        return r.json();
      })
      .then((geojson: { features?: { properties?: { adm_cd2?: string | number; sggnm?: string } }[] }) => {
        const mapped: Record<string, string> = {};
        for (const feature of geojson.features ?? []) {
          const code = String(feature.properties?.adm_cd2 ?? "");
          const district = feature.properties?.sggnm ?? "";
          if (code && district) mapped[code] = district;
        }
        setDongDistrictMap(mapped);
      })
      .catch((error) => {
        if (!controller.signal.aborted) console.error("순위 지역명 매핑 오류:", error);
      });
    return () => controller.abort();
  }, []);

  // [추가] 행정동 점수를 자치구별 단순 평균으로 집계한 순위 (0~100점)
  const districtRankings = useMemo<DistrictRanking[]>(() => {
    const totals = new Map<string, { sum: number; count: number }>();
    for (const item of getScoreItems(rankSource)) {
      const code = String(item.dongCode ?? item.dong_code ?? item.region_code ?? item.code ?? "");
      const district = dongDistrictMap[code];
      const score = metricScore(item, rankMetric);
      if (!district || score === null) continue;
      const current = totals.get(district) ?? { sum: 0, count: 0 };
      current.sum += score;
      current.count += 1;
      totals.set(district, current);
    }
    return [...totals].map(([district, value]) => ({
      district, score: value.sum / value.count, count: value.count,
    })).sort((a, b) => b.score - a.score || a.district.localeCompare(b.district, "ko"));
  }, [rankSource, dongDistrictMap, rankMetric]);


  // ==========================================
  // 5. 백엔드 행정동 데이터 가져오기
  // ==========================================

  useEffect(() => {
    let cancelled = false;

    async function loadDongScores() {
      try {
        setIsLoading(true);
        setApiError(null);

        // 백엔드 전체 행정동 점수 API 호출
        const response = await fetchDongScores();

        if (cancelled) return;

        // API 응답 확인
        console.log("백엔드 행정동 점수 응답:", response);

        // [추가] 동일한 API 응답을 자치구 순위에도 재사용
        setRankSource(response);

        // 지도에서 사용할 점수 데이터로 변환
        const formattedScores = normalizeDongScores(response);

        console.log(
          "지도에 전달할 행정동 점수:",
          formattedScores
        );

        // React 상태에 저장
        setDongScores(formattedScores);

        if (formattedScores.length === 0) {
          setApiError(
            "점수 데이터 형식 또는 행정동 코드를 확인해 주세요."
          );
        }

      } catch (error) {
        if (cancelled) return;

        console.error("행정동 점수 API 오류:", error);

        setApiError(
          error instanceof Error
            ? error.message
            : "백엔드 연결에 실패했습니다."
        );

      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    loadDongScores();

    // 컴포넌트 종료 후 상태 업데이트 방지
    return () => {
      cancelled = true;
    };
  }, []);

  // ==========================================
  // 6. 기존 메인페이지 UI
  // ==========================================

  return (
    <div className="mainpage">

      {/* ==========================================
          1. AI 환경 진단 안내 바
      ========================================== */}
      <section className="diagnosis-section">

        <div className="diagnosis-header">
          <div className="diagnosis-title">

            <div className="diagnosis-icon">✦</div>

            <div>
              <h2>AI 모델 기반 환경 진단</h2>
              <p>서울시 5대 환경 지표 기반 분석</p>
            </div>

          </div>

          {/* 백엔드 가데이터 연결 상태 */}
          <span className="diagnosis-status">
            {isLoading
              ? "데이터 불러오는 중"
              : apiError
                ? "데이터 연결 확인 필요"
                : "테스트 데이터 연결"}
          </span>
        </div>

        <div className="diagnosis-grid">
          {[
            ["📈", "경제 활력도", "상권·일자리"],
            ["⚡", "에너지 소비효율", "에너지·효율"],
            ["🌿", "생활 쾌적도", "환경·녹지"],
            ["❤️", "건강 안전도", "의료·건강"],
            ["🛡️", "치안 안전도", "안전·범죄"],
          ].map(([icon, title, desc]) => (

            <div className="diagnosis-card" key={title}>
              <div className="diagnosis-cardbox">

                <div className="diagnosis-info">
                  <span className="diagnosis-card-icon">
                    {icon}
                  </span>

                  <h3>{title}</h3>
                  <p>{desc}</p>
                </div>

                <strong>분석 대기</strong>
              </div>
            </div>

          ))}
        </div>
      </section>

      {/* ==========================================
          2. 지도 + 오른쪽 분석 패널
      ========================================== */}
      <div className="mainpage-grid">

        {/* 왼쪽: 서울 지도 */}
        <section className="mainpage-card map-card">

          <div className="card-heading">
            <div>
              <h2>생활환경 평가 지도</h2>

              <p>
                {selectedDistrict
                  ? `선택 지역: ${selectedDistrict}`
                  : "지도에서 분석할 지역을 선택하세요."}
              </p>
            </div>
          </div>

          {/* 백엔드 점수 전달 및 기존 지도 재사용 */}
          <SeoulMap
            data={regionScores}
            selectedDistrict={selectedDistrict}
            onDistrictClick={onDistrictClick}
            onDistrictDoubleClick={onDistrictDoubleClick}
            dongScores={dongScores}
          />

        </section>

        {/* ==========================================
            3. 오른쪽 AI 분석 패널
        ========================================== */}
        <div className="mainpage-right">
          {/* [추가] AI 인사이트 아래 자치구별 순위 패널 — 기존 인사이트 유지 */}
          <section className="mainpage-card district-ranking-card">
            <div className="card-heading">
              <h2>자치구별 환경 진단 순위</h2>
              <p>백엔드 행정동 점수의 자치구별 단순 평균 · 테스트 데이터</p>
            </div>
            <label className="district-ranking-filter">
              <span>평가 항목</span>
              <select
                value={rankMetric}
                onChange={(event) => setRankMetric(event.target.value as RankMetric)}
              >
                {RANK_METRICS.map((metric) => (
                  <option key={metric.key} value={metric.key}>{metric.label}</option>
                ))}
              </select>
            </label>

            <div className="district-ranking-list">
              {isLoading ? (
                <p className="district-ranking-empty">순위를 불러오는 중...</p>
              ) : districtRankings.length === 0 ? (
                <p className="district-ranking-empty">
                  표시 가능한 순위가 없습니다. API 점수와 GeoJSON 행정동 코드를 확인해 주세요.
                </p>
              ) : (
                districtRankings.map((item, index) => (
                  <button
                    type="button"
                    className={`district-ranking-row${selectedDistrict === item.district ? " is-selected" : ""}`}
                    key={item.district}
                    onClick={() => onDistrictClick(item.district)}
                    title={`${item.count}개 행정동 점수 평균`}
                  >
                    <span className="district-ranking-position">{index + 1}</span>
                    <span className="district-ranking-name">{item.district}</span>
                    <strong>{item.score.toFixed(1)}점</strong>
                  </button>
                ))
              )}
            </div>
            <p className="district-ranking-footnote">
              점수가 있는 행정동만 집계 · 실제 AI 결과가 아닌 테스트 데이터
            </p>
          </section>
          <section className="mainpage-card insight-card">
            <div className="card-heading">
              <h2>✦ AI 추천 인사이트</h2>
            </div>
            <div className="insight-content">
              <h3>분석 결과</h3>
              <p>
                {selectedDistrict
                  ? `${selectedDistrict}의 AI 분석 결과는 모델 연동 후 제공됩니다.`
                  : "지도에서 지역을 선택하면 분석 결과가 표시됩니다."}
              </p>
            </div>
            <div className="insight-content warning">
              <h3>주의할 점</h3>
              <p>
                환경 및 생활안전 관련 주요 지표를
                분석한 뒤 안내할 예정입니다.
              </p>
            </div>
          </section>
        </div>

      </div>
    </div>
  );
}
