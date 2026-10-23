
import { useEffect, useMemo, useState } from "react";
import SeoulMap from "./SeoulMap";
import "../CSS/MainPage.css";
import { fetchRealScores, fetchRealDistricts, type DomainScores } from "../services/recommendationApi";

// 1. 기본 설정

// 기존 자치구 점수 데이터
// 행정동 색상은 dongScores를 통해 별도로 전달
const regionScores: { district: string; score: number }[] = [];

// 메인페이지 기본 가중치
// 상세분석에서 설정한 기본 가중치와 동일
const DEFAULT_WEIGHTS = {
  economy: 20,
  energy: 20,
  comfort: 20,
  health: 20,
  safety: 20,
};

// 지도에 전달할 행정동 점수 타입
type DongMapScore = {
  dongCode: string;
  score: number;
};

const RANK_METRICS = [
  { key: "overall", label: "종합 점수", icon: "✦" },
  { key: "economy", label: "경제 활력도", icon: "📈" },
  { key: "energy", label: "에너지 소비효율", icon: "⚡" },
  { key: "comfort", label: "생활 쾌적도", icon: "🌿" },
  { key: "health", label: "건강 안전도", icon: "❤️" },
  { key: "safety", label: "치안 안전도", icon: "🛡️" },
] as const;

type RankMetric = (typeof RANK_METRICS)[number]["key"];

// 환경 진단 순위에 사용할 공통 데이터 타입
type EnvironmentRanking = {
  regionCode: string;      // 지역 코드
  regionName: string;      // 자치구명 또는 행정동명
  districtName?: string;   // 행정동이 속한 자치구
  spatialUnit: "district" | "dong"; // 자치구 / 행정동 구분
  score: number;           // 모델 예측 점수
};

// 실데이터 API를 기존 화면의 지역/점수 구조로 연결하기 위한 내부 타입
// 점수 미제공(null)인 항목도 보존하여 임의로 0점 처리하지 않음
type DisplayScore = {
  region: {
    region_code: string;
    name_ko: string;
    parent_region_code?: string;
    spatial_unit: "district" | "dong";
  };
  scores: DomainScores;
};

// 백엔드의 점수 데이터는 region, scores 두 필드로 구성됨.
const validScore = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;

function metricScore(item: DisplayScore, metric: RankMetric): number | null {
  if (metric === "overall") return calculateScore(item.scores);
  const value = item.scores[metric];
  return validScore(value) ? value : null;
}

// 부모 컴포넌트에서 전달받는 데이터 타입
type MainPageProps = {
  selectedDistrict: string | null;
  onDistrictClick: (district: string) => void;
  onDistrictDoubleClick: (district: string) => void;
  onMapReset: () => void;
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
// 4. 메인페이지
// ==========================================

export default function MainPage({
  selectedDistrict,
  onDistrictClick,
  onDistrictDoubleClick,
  onMapReset,
}: MainPageProps) {

  const [selectedRank, setSelectedRank] = useState<string | null>(null);

// 지도 초기화 신호
const [mapResetKey, setMapResetKey] = useState(0);

// 메인 지도에서 선택한 행정동 코드
const [selectedDongCode, setSelectedDongCode] =
  useState<string | null>(null);

// 백엔드에서 가져온 행정동별 종합점수
const [dongScores, setDongScores] = useState<DongMapScore[]>([]);

  // API 요청 진행 상태
  const [isLoading, setIsLoading] = useState(true);

  // API 오류 메시지
  const [apiError, setApiError] = useState<string | null>(null);

  // 자치구/행정동 단위 실데이터 점수를 별도 저장
  const [districtSource, setDistrictSource] = useState<DisplayScore[]>([]);
  const [dongSource, setDongSource] = useState<DisplayScore[]>([]);
  const [rankMetric, setRankMetric] = useState<RankMetric>("overall");
  
  // 클릭 직후 확대하면 더블클릭 두 번째 이벤트가 끊길 수 있어 확대를 지연합니다.
  const [mapFocusDistrict, setMapFocusDistrict] = useState<string | null>(null);
  useEffect(() => {
    if (!selectedDistrict) { setMapFocusDistrict(null); return; }
    const timer = window.setTimeout(() => setMapFocusDistrict(selectedDistrict), 700);
    return () => window.clearTimeout(timer);
  }, [selectedDistrict]);

  const districtScores = useMemo(() => districtSource.find(
    item => item.region.name_ko === selectedDistrict
  )?.scores, [districtSource, selectedDistrict]);

  // 서울시 전체 행정동의 영역별 평균 점수
  const seoulAverageScores = useMemo(() => {
    const metrics = [
      "economy",
      "energy",
      "comfort",
      "health",
      "safety",
    ] as const;
  
    const averages: Record<string, number | null> = {};
  
    for (const metric of metrics) {
      const values = dongSource
        .map((item) => item.scores[metric])
        .filter((value): value is number => validScore(value));
  
      averages[metric] =
        values.length > 0
          ? values.reduce((sum, value) => sum + value, 0) / values.length
          : null;
    }
  
    return averages;
  }, [dongSource]);

  // 자치구 선택 여부에 따라 표시할 점수 변경
  const displayedScores = selectedDistrict
    ? districtScores
    : seoulAverageScores;

  // 경제: 자치구별 경제 점수 1위 행정동, 나머지: 자치구별 점수
  const rankUnit = rankMetric === "economy" ? "dong" : "district";

  const environmentRankings = useMemo<EnvironmentRanking[]>(() => {
    if (rankMetric === "economy") {
      // parent_region_code는 구 코드(5자리)이며, 지도용 geometry_key와 다릅니다.
      const bestByDistrict = new Map<string, EnvironmentRanking>();
      const districtNameByCode = new Map(
        districtSource.map((district) => [
          district.region.region_code,
          district.region.name_ko,
        ])
      );

      for (const dong of dongSource) {
        const districtCode = dong.region.parent_region_code;
        const score = metricScore(dong, "economy");
        if (!districtCode || score === null) continue;

        const candidate: EnvironmentRanking = {
          regionCode: dong.region.region_code,
          regionName: dong.region.name_ko,
          districtName: districtNameByCode.get(districtCode),
          spatialUnit: "dong",
          score,
        };

        const previous = bestByDistrict.get(districtCode);
        if (
          !previous ||
          score > previous.score ||
          (score === previous.score &&
            candidate.regionCode.localeCompare(previous.regionCode) < 0)
        ) {
          bestByDistrict.set(districtCode, candidate);
        }
      }

      return Array.from(bestByDistrict.values()).sort(
        (a, b) =>
          b.score - a.score || a.regionCode.localeCompare(b.regionCode)
      );
    }

    return districtSource
      .flatMap((district): EnvironmentRanking[] => {
        const score = metricScore(district, rankMetric);
        if (score === null) return [];
        return [{
          regionCode: district.region.region_code,
          regionName: district.region.name_ko,
          spatialUnit: "district",
          score,
        }];
      })
      .sort(
        (a, b) =>
          b.score - a.score || a.regionCode.localeCompare(b.regionCode)
      );
  }, [rankMetric, dongSource, districtSource]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setApiError(null);

      try {
        // DB에 적재한 실제 AI 점수: 행정동 전체 + 자치구 평균
        const [dongs, districts] = await Promise.all([
          fetchRealScores(),
          fetchRealDistricts(),
        ]);
        if (cancelled) return;

        // 지도에서는 실제 API의 6자리 region_code 대신 10자리 geometry_key 사용
        const convertedDongs: DisplayScore[] = dongs.items.flatMap((item) => {
          if (!item.geometry_key) return [];
          return [{
            region: {
              region_code: item.geometry_key,
              name_ko: item.region_name,
              parent_region_code: item.sigungu_code,
              spatial_unit: "dong" as const,
            },
            scores: item.category_scores,
          }];
        });

        const convertedDistricts: DisplayScore[] = districts.items.map((item) => ({
          region: {
            region_code: item.sigungu_code,
            name_ko: item.sigungu_name,
            spatial_unit: "district" as const,
          },
          scores: item.category_scores,
        }));

        setDistrictSource(convertedDistricts);
        setDongSource(convertedDongs);
        setDongScores(convertedDongs.flatMap((item) => {
          const score = calculateScore(item.scores);
          return score === null ? [] : [{ dongCode: item.region.region_code, score }];
        }));
      } catch (error) {
        if (!cancelled) {
          setApiError(error instanceof Error ? error.message : "실제 AI 점수 API 연결 실패");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  // 선택한 아이콘의 실제 행정동 점수를 기존 지도 색상 로직에 전달합니다.
  const mapMetricScores = useMemo<DongMapScore[]>(() => {
    if (rankMetric === "overall") return dongScores;
    return dongSource.flatMap(item => {
      const score = item.scores[rankMetric];
      return validScore(score) ? [{ dongCode: item.region.region_code, score }] : [];
    });
  }, [rankMetric, dongScores, dongSource]);

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
              <h2>AI 기반 환경 진단</h2>
              <p>서울시 5대 환경 지표 기반 분석</p>
            </div>

          </div>

          {/* 실제 AI 점수 스냅샷 로딩 상태 (실시간 데이터 아님) */}
          <span className="diagnosis-status">
            {isLoading
              ? "데이터 불러오는 중"
              : apiError
                ? "데이터 연결 확인 필요"
                : "AI 점수 연결됨 · 잠정값 포함"}
          </span>
        </div>

        <div className="diagnosis-grid">
          {[
            ["📈", "경제 활력도", "상권·일자리"],
            ["⚡", "에너지 소비효율", "에너지·효율"],
            ["🌿", "생활 쾌적도", "환경·녹지"],
            ["❤️", "건강 안전도", "의료·건강"],
            ["🛡️", "치안 안전도", "안전·범죄"],
          ].map(([icon, title, desc], index) => (

            <div className="diagnosis-card" key={title}>
              <div className="diagnosis-cardbox">

                <div className="diagnosis-info">
                  <span className="diagnosis-card-icon">
                    {icon}
                  </span>

                  <h3>{title}</h3>
                  <p>{desc}</p>
                </div>

                <strong>
                  {(() => {
                    const metric = ([
                      "economy",
                      "energy",
                      "comfort",
                      "health",
                      "safety",
                    ] as const)[index];
                    
                    const score = displayedScores?.[metric];
                
                    return validScore(score)
                      ? `${score.toFixed(1)}점`
                      : "분석 대기";
                  })()}
                </strong>
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
          <div className="card-head">
            <div className="card-heading">
              <div>
                <h2>생활환경 평가 지도 (종합 평가)</h2>
  
                <p>
                  {selectedDistrict
                    ? `선택 지역: ${selectedDistrict}`
                    : "지도에서 분석할 지역을 선택하세요."}
                </p>
              </div>
            </div>
  
            <button
              type="button"
              className="main_map-reset_btn"
              onClick={() => {
                onMapReset();
                setSelectedDongCode(null);
                setMapResetKey((prev) => prev + 1);
              }}
            >
              지도 초기화
            </button>
          </div>

          {/* 백엔드 점수 전달 및 기존 지도 재사용 */}
          <SeoulMap
            data={regionScores}
            selectedDistrict={selectedDistrict}
            onDistrictClick={onDistrictClick}
            onDistrictDoubleClick={onDistrictDoubleClick}
          
            // 선택한 자치구의 전체 경계를 지도에 맞춰 확대
            focusDistrict={mapFocusDistrict}
            resetKey={mapResetKey}
            dongScores={mapMetricScores}

            // 아래 두 줄 추가
            selectedDongCode={selectedDongCode}
            onDongClick={setSelectedDongCode}
          />

        </section>

        {/* ==========================================
            3. 오른쪽 AI 분석 패널
        ========================================== */}
        
        <div className="mainpage-right">
          <section className="mainpage-card district-ranking-card">
        
            <h2 className="score-panel-title">환경 진단 점수</h2>
        
            {/* 평가 항목 선택: 아이콘 버튼 6개 */}
            <div className="score-category-buttons">
              {RANK_METRICS.map((metric) => (
                <button
                  key={metric.key}
                  type="button"
                  className={`score-category-button ${
                    rankMetric === metric.key ? "is-active" : ""
                  }`}
                  title={metric.label}
                  aria-label={metric.label}
                  aria-pressed={rankMetric === metric.key}
                  onClick={() => {
                    setRankMetric(metric.key);
                    setSelectedRank(null);
                  }}
                >
                  {metric.icon}
                </button>
              ))}
            </div>
        
            {/* 현재 선택된 평가 항목의 지역 기준 안내 */}
            <div className="score-panel-description">
              <strong>
                {rankUnit === "dong"
                  ? "행정동 기준 점수"
                  : "자치구 기준 점수"}
              </strong>
        
              <p>
                {rankUnit === "dong"
                  ? "자치구별 행정동 1곳 중 평균이 높은 순"
                  : "서울시 25개 자치구별 환경 진단 점수"}
              </p>
            </div>
        
            {/* 지역별 점수: 2열 표시 */}
            <div
              className={`score-region-grid ${
                rankUnit === "dong" ? "is-dong" : "is-district"
              }`}
            >
              {isLoading ? (
                <p className="score-region-message">
                  점수를 불러오는 중입니다.
                </p>
              ) : environmentRankings.length === 0 ? (
                <p className="score-region-message">
                  표시할 점수 데이터가 없습니다.
                </p>
              ) : (
                environmentRankings.map((item) => (
                  <button
                    key={item.regionCode}
                    type="button"
                    className={`score-region-item ${
                      selectedRank === item.regionCode
                        ? "is-selected"
                        : ""
                    }`}
                    onClick={() => {
                      setSelectedRank(item.regionCode);
        
                      if (item.spatialUnit === "district") {
                        setSelectedDongCode(null);
                        onDistrictClick(item.regionName);
                      } else {
                        setSelectedDongCode(item.regionCode);
        
                        if (item.districtName) {
                          onDistrictClick(item.districtName);
                        }
                      }
                    }}
                  >
                    <span className="score-region-name">
                      {item.regionName}
                      {item.spatialUnit === "dong" && item.districtName && (
                        <small className="score-region-district">
                          {item.districtName}
                        </small>
                      )}
                    </span>
        
                    <strong className="score-region-value">
                      {item.score.toFixed(1)}점
                    </strong>
                  </button>
                ))
              )}
            </div>
        
          </section>
        </div>


      </div>
    </div>
  );
}
