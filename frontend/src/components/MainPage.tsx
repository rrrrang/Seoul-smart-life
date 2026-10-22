
import { useEffect, useMemo, useState } from "react";
import SeoulMap from "./SeoulMap";
import "../CSS/MainPage.css";
import { fetchScores, type ScoresResponse } from "../services/regionApi";

// 1. 기본 설정

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

// 환경 진단 순위에 사용할 공통 데이터 타입
type EnvironmentRanking = {
  regionCode: string;      // 지역 코드
  regionName: string;      // 자치구명 또는 행정동명
  districtName?: string;   // 행정동이 속한 자치구
  spatialUnit: "district" | "dong"; // 자치구 / 행정동 구분
  score: number;           // 모델 예측 점수
};

// 백엔드의 점수 데이터는 region, scores 두 필드로 구성됨.
const validScore = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;

function metricScore(item: ScoresResponse, metric: RankMetric): number | null {
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

  // 자치구/행정동 단위 점수를 별도 저장 (모든 점수는 백엔드 표기상 테스트 포함)
  const [districtSource, setDistrictSource] = useState<ScoresResponse[]>([]);
  const [dongSource, setDongSource] = useState<ScoresResponse[]>([]);
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

  // 선택 지표의 원천 지역 단위를 따름: 경제=행정동, 그 외=자치구 (현재 UI 정책)
  // 백엔드는 치안의 행정동 원자료도 갖고 있지만 화면에서는 자치구별 평균을 제공함.
  const rankUnit = rankMetric === "economy" ? "dong" : "district";
  const environmentRankings = useMemo<EnvironmentRanking[]>(() => {
    const source = rankUnit === "dong" ? dongSource : districtSource;
    return source.flatMap(item => {
      const score = metricScore(item, rankMetric);
      if (score === null) return [];
      return [{
        regionCode: item.region.region_code,
        regionName: item.region.name_ko,
        districtName: rankUnit === "dong" ? districtSource.find(
          district => district.region.region_code === item.region.parent_region_code
        )?.region.name_ko : undefined,
        spatialUnit: rankUnit as "district" | "dong",
        score,
      }];
    }).sort((a,b) => b.score - a.score || a.regionCode.localeCompare(b.regionCode)).slice(0,10);
  }, [rankUnit, rankMetric, dongSource, districtSource]);

  const selectedRanking = environmentRankings.find(item => item.regionCode === selectedRank);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      setApiError(null);
      try {
        const [districts, dongs] = await Promise.all([
          fetchScores("district"), fetchScores("dong"),
        ]);
        if (cancelled) return;
        setDistrictSource(districts.items);
        setDongSource(dongs.items);
        const mapScores = dongs.items.flatMap(item => {
          const score = calculateScore(item.scores);
          return score === null ? [] : [{ dongCode: item.region.region_code, score }];
        });
        setDongScores(mapScores);
      } catch (error) {
        if (!cancelled) setApiError(error instanceof Error ? error.message : "점수 API 연결 실패");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
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
              <h2>AI 기반 환경 진단</h2>
              <p>서울시 5대 환경 지표 기반 분석</p>
            </div>

          </div>

          {/* 백엔드 가데이터 연결 상태 */}
          <span className="diagnosis-status">
            {isLoading
              ? "데이터 불러오는 중"
              : apiError
                ? "데이터 연결 확인 필요"
                : "테스트 점수 포함 · 실모델 미연동"}
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

                <strong>{selectedDistrict && districtScores && validScore(
                  districtScores[["economy", "energy", "comfort", "health", "safety"][index] as keyof typeof districtScores]
                ) ? `${Number(districtScores[["economy", "energy", "comfort", "health", "safety"][index] as keyof typeof districtScores]).toFixed(1)}점` : "분석 대기"}</strong>
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
                <h2>생활환경 평가 지도</h2>
  
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
            dongScores={dongScores}

            // 아래 두 줄 추가
            selectedDongCode={selectedDongCode}
            onDongClick={setSelectedDongCode}
          />

        </section>

        {/* ==========================================
            3. 오른쪽 AI 분석 패널
        ========================================== */}
        <div className="mainpage-right">
          {/* [추가] AI 인사이트 아래 자치구별 순위 패널 — 기존 인사이트 유지 */}
          <section className="mainpage-card district-ranking-card">
            <div className="card-heading">
              <h2>환경 진단 순위</h2>
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
              {isLoading ? <p className="district-ranking-empty">순위 불러오는 중...</p> :
                environmentRankings.length === 0 ? <p className="district-ranking-empty">연결된 점수가 없습니다.</p> :
                environmentRankings.map((item, index) => (
                  <button type="button" key={item.regionCode}
                    className={`district-ranking-row${selectedRank === item.regionCode ? " is-selected" : ""}`}
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
                    <span className="district-ranking-position">{index + 1}</span>
                    <span className="district-ranking-name">{item.regionName}{item.districtName && <small>{item.districtName}</small>}</span>
                    <strong>{item.score.toFixed(1)}점</strong>
                  </button>
                ))}
            </div>
            <div className="ranking-selected-score">
              {selectedRanking
                ? `${selectedRanking.regionName} · ${
                    RANK_METRICS.find(metric => metric.key === rankMetric)?.            label
                  } ${selectedRanking.score.toFixed(1)}점`
                : "지역을 선택하면 해당 지역의 점수가 표시됩니다."}
            </div>
          </section>
        </div>

      </div>
    </div>
  );
}
