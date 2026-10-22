import { useEffect, useMemo, useState } from "react";
import SeoulMap from "./SeoulMap";
import "../CSS/DetailAnalysis.css";

import {
  // getTop10Dongs,
  calculateTotalScore,
  type DongScore,
  type ScoreWeights,
} from "../data/mockDongScores";

import {
  fetchAllDongScores,
  fetchDistricts,
  fetchRegionScores,
  fetchDongs,
  fetchScores,
} from "../services/regionApi";

// AI 데이터 연동 전에는 점수를 표시하지 않음
// [지도 데이터] 실제 점수 연동 전에는 자치구 점수를 비워 둡니다.
const emptyRegionScores: { district: string; score: number }[] = [];

// 평가 항목과 초기 가중치
// [기본 가중치] 5개 평가 항목의 초기 비율이며 초기화 시에도 사용합니다.
const criteria = [
  { key: "economy", label: "경제 활력도", defaultWeight: 20 },
  { key: "energy", label: "에너지 소비효율", defaultWeight: 20 },
  { key: "comfort", label: "생활 쾌적도", defaultWeight: 20 },
  { key: "health", label: "건강 안전도", defaultWeight: 20 },
  { key: "safety", label: "치안 안전도", defaultWeight: 20 },
] as const;

type Props = {
  selectedDistrict: string | null;
  onDistrictClick: (district: string) => void;
};

// [상세분석] 선택된 자치구 및 클릭 이벤트를 상위 App으로부터 받습니다.
export default function DetailAnalysis({
  selectedDistrict,
  onDistrictClick,
}: Props) {
  // [슬라이더 상태] 가중치를 바꾸면 화면과 추천 계산이 갱신됩니다.
  // 사용자가 변경하는 가중치
  const [weights, setWeights] = useState<number[]>(
    criteria.map((item) => item.defaultWeight)
  );

  // 지도 초기화 버튼을 누른 횟수
  const [mapResetKey, setMapResetKey] = useState(0);
  // 서울 전체 지도 표시 여부
  const [showAllSeoul, setShowAllSeoul] = useState(false);

  // 오른쪽 분석 탭
  const [activeTab, setActiveTab] = useState<
    "scores" | "trend" | "compare"
  >("scores");

  // 가중치 합계
  const weightSum = weights.reduce(
    (sum, weight) => sum + weight,
    0
  );
  

// 슬라이더 가중치를 평가 항목별 데이터로 변환
const scoreWeights: ScoreWeights = {
  economy: weights[0],
  energy: weights[1],
  comfort: weights[2],
  health: weights[3],
  safety: weights[4],

};

// ================================
  // 2. 백엔드 API 연결 테스트 (추가)
  // ================================
  useEffect(() => {
    async function testBackend() {
      try {
        // 행정동 목록 조회
        const regions = await fetchDongs();

        console.log("백엔드 행정동 개수:", regions.count);
        console.log("백엔드 행정동 목록:", regions.items);

        // 청운효자동 점수 조회
        const result = await fetchRegionScores("1111051500");

        console.log("선택 행정동:", result.region.name_ko);
        console.log("행정동 평가 점수:", result.scores);
        console.log("테스트 데이터 여부:", result.is_mock);

      } catch (error) {
        console.error("백엔드 연결 실패:", error);
      }
    }

    testBackend();
  }, []);

// 백엔드 가데이터를 한 번 읽어 5개 평가 점수의 공통 원본으로 사용합니다.
const [dongScores, setDongScores] = useState<DongScore[]>([]);
const [dataError, setDataError] = useState("");
const [loadingScores, setLoadingScores] = useState(true);
const [selectedDongCode, setSelectedDongCode] = useState("");
const [seoulAverage, setSeoulAverage] = useState<Record<string, number>>({});
const [districtAverage, setDistrictAverage] = useState<Record<string, number>>({});


useEffect(() => {
  let cancelled = false;
  async function loadBackendScores() {
    try {
      const [districts, result] = await Promise.all([
        fetchDistricts(), fetchAllDongScores(),
      ]);
      const districtNames = new Map(districts.items.map(d => [d.region_code, d.name_ko]));
      const converted: DongScore[] = result.items.map(({ region, scores }) => ({
        dongCode: region.region_code,
        dongName: region.name_ko,
        district: districtNames.get(region.parent_region_code ?? "") ?? "",
        scores,
      }));
      if (!cancelled) {
        setDongScores(converted);
        setDataError("");
        console.log("백엔드 행정동 점수 연결:", converted.length, "개", "Mock:", result.is_mock);
      }
    } catch (error) {
      if (!cancelled) setDataError(error instanceof Error ? error.message : "API 연결 실패");
    } finally {
      if (!cancelled) setLoadingScores(false);
    }
  }
  loadBackendScores();
  return () => { cancelled = true; };
}, []);

// 평균 비교는 동일한 동 단위 데이터의 단순 평균으로 계산 (현재는 테스트 점수 포함).
useEffect(() => {
  let cancelled = false;
  fetchScores("dong").then(result => {
    if (cancelled) return;
    const keys = criteria.map(item => item.key);
    const avg = (items: typeof result.items) => Object.fromEntries(keys.map(key => [key,
      items.length ? items.reduce((sum, item) => sum + item.scores[key], 0) / items.length : 0
    ]));
    setSeoulAverage(avg(result.items));
  }).catch(error => console.error("서울 평균 API:", error));
  return () => { cancelled = true; };
}, []);

useEffect(() => {
  // 현재 선택 자치구 소속 행정동들의 평균 (원본 지역 코드 매핑 기준)
  const scores = dongScores.filter(item => item.district === selectedDistrict);
  setDistrictAverage(Object.fromEntries(criteria.map(item => [item.key,
    scores.length ? scores.reduce((sum, dong) => sum + dong.scores[item.key], 0) / scores.length : 0
  ])));
}, [dongScores, selectedDistrict]);

// 가중치 또는 지역 선택이 바뀔 때 같은 백엔드 점수로 TOP 5을 계산합니다.
// 선택 자치구의 추천 행정동 TOP 10 계산
const top10Dongs = useMemo(() => {
  if (!selectedDistrict) return [];

  return dongScores
    .filter((dong) => dong.district === selectedDistrict)
    .flatMap((dong) => {
      const totalScore = calculateTotalScore(dong.scores, scoreWeights);

      if (totalScore === null) return [];

      return [{
        dongCode: dong.dongCode,
        dongName: dong.dongName,
        totalScore,
      }];
    })
    .sort((a, b) =>
      b.totalScore - a.totalScore ||
      a.dongCode.localeCompare(b.dongCode)
    )
    .slice(0, 10)
    .map((dong, index) => ({
      ...dong,
      rank: index + 1,
    }));
}, [dongScores, selectedDistrict, ...weights]);

// TOP 10 자동 스크롤 상태
const [rollingIndex, setRollingIndex] = useState(0);
const [isRollingPaused, setIsRollingPaused] = useState(false);
const [isRollingAnimated, setIsRollingAnimated] = useState(false);

// 10위 다음에도 1~5위가 자연스럽게 이어지도록 목록 복제
const rollingDongs = useMemo(() => {
  return [
    ...top10Dongs,
    ...top10Dongs.slice(0, 5),
  ];
}, [top10Dongs]);

// 자치구, 가중치, 순위 변경 시 처음부터 다시 시작
useEffect(() => {
  setRollingIndex(0);
  setIsRollingAnimated(false);
}, [top10Dongs]);

// 3초마다 한 칸씩 위로 이동
useEffect(() => {
  if (isRollingPaused || top10Dongs.length <= 5) return;

  const timer = window.setTimeout(() => {
    setIsRollingAnimated(true);
    setRollingIndex((prev) => prev + 1);
  }, 2000);

  return () => window.clearTimeout(timer);
}, [rollingIndex, isRollingPaused, top10Dongs]);

// 마지막 순위 이후 처음으로 돌아가는 처리
const handleRollingEnd = () => {
  if (rollingIndex >= top10Dongs.length) {
    setIsRollingAnimated(false);
    setRollingIndex(0);
  }
};

const districtDongs = useMemo(() => dongScores
  .filter(item => item.district === selectedDistrict)
  .sort((a, b) => a.dongName.localeCompare(b.dongName, "ko")),
  [dongScores, selectedDistrict]);

useEffect(() => { setSelectedDongCode(""); }, [selectedDistrict]);

const selectedDong = districtDongs.find(item => item.dongCode === selectedDongCode);

const selectedScore = selectedDong ? calculateTotalScore(selectedDong.scores, scoreWeights) : null;

const mapDongScores = useMemo(() => dongScores.flatMap(item => {
  const score = calculateTotalScore(item.scores, scoreWeights);
  return score === null ? [] : [{ dongCode: item.dongCode, score }];
}), [dongScores, ...weights]);

  return (
    <div className="detail-analysis">
      {/* 상세분석 페이지 제목 */}
      <header className="detail-page-header">
        
        <div className="detail-page-title">
          <div className="diagnosis-icon">✦</div>
          <div className="diagnosis-box">
            <h1>지역 상세분석</h1>
            <p>
              {selectedDistrict
                ? `${selectedDistrict} · 행정동별 생활환경 분석`
                : "분석할 자치구를 선택해 주세요."}
            </p>
          </div>
        </div>
        <span className="detail-progress-tag">
          {loadingScores ? "데이터 불러오는 중" : dataError ? "API 연결 오류" : "백엔드 가데이터 연결됨"}
        </span>
      </header>

      {/* [화면 배치] 왼쪽 가중치/순위, 가운데 지도, 오른쪽 분석의 3단 구성 */}
      {/* 전체 3단 레이아웃 */}
      <div className="detail-layout">
        {/* 왼쪽: 가중치 + TOP 5 */}
        <aside className="detail-left-panel">
          <section className="detail-panel">
            <div className="detail-panel-heading">
              <h2>평가 가중치</h2>
              <button
                className="detail-reset-button"
                type="button"
                onClick={() => {
                  // 1. 가중치를 기본값으로 복구
                  setWeights(criteria.map((item) => item.defaultWeight));
              
                  // 2. 서울 전체 지도 표시
                  setShowAllSeoul(true);
              
                  // 3. 지도 초기화 신호 전달
                  setMapResetKey((prev) => prev + 1);
                }}
              >
                초기화
              </button>
              
            </div>

            <p className="detail-muted">
              항목별 중요도를 자유롭게 조절하세요.
            </p>

            <div className="detail-weight-list">
              {criteria.map((item, index) => (
                <label
                  className="detail-weight-item"
                  key={item.key}
                >
                  <span className="detail-weight-label">
                    <span>{item.label}</span>
                    <strong>{weights[index]}%</strong>
                  </span>

                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                    value={weights[index]}
                    onChange={(event) =>
                      setWeights((prev) =>
                        prev.map((weight, i) =>
                          i === index
                            ? Number(event.target.value)
                            : weight
                        )
                      )
                    }
                  />
                </label>
              ))}
            </div>

            <div className="detail-weight-total">
              <span>현재 가중치 합계</span>
              <strong>{weightSum}%</strong>
            </div>

            <p className="detail-help">
              실제 점수 연동 시 가중치 합계로 나눠
              계산합니다. 합계가 0이면 계산하지 않습니다.
            </p>
          </section>

          {/* [TOP 5] 종합점수 내림차순 목록이며, 데이터가 없을 때 분석 대기를 표시 */}
          {/* 추천 행정동 순위 */}
          {/* 추천 행정동 TOP 10 자동 롤링 */}
          <section className="detail-panel detail-ranking-panel">
          
            <div className="detail-panel-heading">
              <h2>추천 행정동 TOP 10</h2>
            </div>
          
            <div
              className="detail-ranking-list"
              onMouseEnter={() => setIsRollingPaused(true)}
              onMouseLeave={() => setIsRollingPaused(false)}
            >
              {dataError ? (
                <div className="detail-pending">
                  API 연결 실패: {dataError}
                </div>
              ) : top10Dongs.length > 0 ? (
          
                <div
                  className={`detail-ranking-track ${
                    isRollingAnimated ? "is-animated" : ""
                  }`}
                  style={{
                    transform: `translateY(-${rollingIndex * 56}px)`,
                  }}
                  onTransitionEnd={(event) => {
                    if (event.target === event.currentTarget) {
                      handleRollingEnd();
                    }
                  }}
                >
                  {rollingDongs.map((dong, index) => (
                    <div
                      className="detail-ranking-item"
                      key={`${dong.dongCode}-${index}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedDongCode(dong.dongCode)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          setSelectedDongCode(dong.dongCode);
                        }
                      }}
                    >
                      <span className="detail-ranking-number">
                        {dong.rank}
                      </span>
          
                      <span className="detail-ranking-name">
                        {dong.dongName}
                      </span>
          
                      <strong>
                        {dong.totalScore.toFixed(1)}점
                      </strong>
                    </div>
                  ))}
                </div>
          
              ) : (
                <div className="detail-pending">
                  <strong>분석 대기</strong>
                  <p>행정동별 평가 점수가 연결되면 순위가 표시됩니다.</p>
                </div>
              )}
            </div>
          
          </section>
        </aside>

        {/* [지도 연결] showAllSeoul과 resetKey를 전달하여 전체 지도 복원 처리 */}
        {/* 가운데: 기존 서울 지도 */}
        <section className="detail-panel detail-map-panel">
          <div className="detail-panel-heading">
            <div>
              <h2>
                {selectedDistrict
                  ? `${selectedDistrict} 행정동 지도`
                  : "서울 행정동 지도"}
              </h2>
            </div>
          </div>

          <SeoulMap
            data={emptyRegionScores}
            selectedDistrict={showAllSeoul ? null : selectedDistrict}
            onDistrictClick={onDistrictClick}
            focusDistrict={showAllSeoul ? null : selectedDistrict}
            resetKey={mapResetKey}
            dongScores={mapDongScores}
            selectedDongCode={selectedDongCode}
            onDongClick={setSelectedDongCode}
          />

          <p className="detail-map-note">
            행정동 상세분석을 통해 선택한 자치구의 생활환경 점수를 확인할 수 있습니다. <br />
          </p>
        </section>

        {/* 오른쪽: 선택 지역 상세분석 */}
        <section className="detail-panel detail-result-panel">

          <div className="detail-panel-heading">
            <h2>행정동 상세분석</h2>
          </div>

          <div className="detail-selected-area">
            <span>선택 자치구</span>

            <h3>{selectedDistrict ?? "선택 대기"}</h3>

            <label htmlFor="detail-dong-select">행정동 선택</label>

            <div className="detail-select-wrapper">
              <select id="detail-dong-select" value={selectedDongCode} onChange={(event) => setSelectedDongCode(event.target.value)}>

                <option value="">행정동을 선택하세요</option>

                {districtDongs.map((dong) => (
                  <option key={dong.dongCode} value={dong.dongCode}>
                    {dong.dongName}
                  </option>
                ))}

              </select>
            
              {/* 오른쪽 화살표 영역 */}
              <span className="detail-select-icon" aria-hidden="true">

                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m6 9 6 6 6-6" />
                </svg>

              </span>
            </div>
          </div>

          <div className="detail-overall-score">

            <span>AI 종합점수</span>

            <strong>{selectedScore === null ? "분석 대기" : `${selectedScore.toFixed(1)}점`}</strong>
          </div>

          {/* 분석 결과 탭 */}
          <div className="detail-tab-group" role="tablist">
            <button
              type="button"
              className={activeTab === "scores" ? "active" : ""}
              onClick={() => setActiveTab("scores")}
            >
              항목별 점수
            </button>
            <button
              type="button"
              className={activeTab === "trend" ? "active" : ""}
              onClick={() => setActiveTab("trend")}
            >
              환경 노출 추이
            </button>
            <button
              type="button"
              className={activeTab === "compare" ? "active" : ""}
              onClick={() => setActiveTab("compare")}
            >
              평균 비교
            </button>
          </div>

          <div className="detail-tab-content">
            {activeTab === "scores" ? (
              <div className="detail-score-list">
                {criteria.map((item) => {
                  const score = selectedDong?.scores[item.key];
                  return <div className="detail-score-row" key={item.key}>
                    <span>{item.label}</span>
                    <div className="detail-score-track"><div className="detail-score-fill" style={{ width: `${score ?? 0}%` }} /></div>
                    <strong>{typeof score === "number" ? `${score.toFixed(1)}점` : "분석 대기"}</strong>
                  </div>;
                })}
              </div>
            ) : activeTab === "trend" ? (
              <div className="detail-data-placeholder">
                <h3>환경 노출 추이</h3>
                <p>월별 PM2.5 · PM10 · 소음 관측 API 연결 대기</p>
                <div className="detail-empty-chart" aria-label="환경 노출 추이 데이터 대기">관측 기간별 데이터가 제공되면 그래프를 표시합니다.</div>
                <small>실시간/시계열 관측 API 미제공 · 임의 관측값 표시하지 않음</small>
              </div>
            ) : (
              <div className="detail-average-table">
                <p className="detail-muted">행정동 데이터 기반 평균 · 테스트 점수 포함</p>
                <table>
                  <thead>
                    <tr>
                      <th>항목</th>
                      <th>선택 행정동</th>
                      <th>소속 구 평균</th>
                      <th>서울 평균</th>
                    </tr>
                  </thead>
                <tbody>
                  {criteria.map(item => <tr key={item.key}><th>{item.label}</th>
                    <td>{selectedDong ? selectedDong.scores[item.key].toFixed(1) : "—"}</td>
                    <td>{districtDongs.length ? districtAverage[item.key]?.toFixed(1) : "—"}</td>
                    <td>{dongScores.length ? seoulAverage[item.key]?.toFixed(1) : "—"}</td>
                  </tr>)}
                </tbody></table>
              </div>
            )}
          </div>

          {/* ==========================================
              AI 추천 근거 / 주의할 점
              추후 백엔드 LLM 응답 연결 예정
          ========================================== */}
          <div className="detail-ai-insights">

            {/* AI 추천 근거 */}
            <div className="detail-ai-card recommendation">
              <h3>추천 근거</h3>
              <p>
                선택한 행정동의 환경 지표를 바탕으로
                AI 추천 근거가 표시될 예정입니다.
              </p>
            </div>

            {/* AI 주의할 점 */}
            <div className="detail-ai-card caution">
              <h3>주의할 점</h3>
              <p>
                선택한 행정동에서 확인해야 할
                생활환경 관련 주의사항이 표시될 예정입니다.
              </p>
            </div>

          </div>

        </section>
      </div>
    </div>
  );
}
