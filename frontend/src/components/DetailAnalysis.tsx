import { useEffect, useMemo, useState } from "react";
import SeoulMap from "./SeoulMap";
import "../CSS/DetailAnalysis.css";

import {
  getTop10Dongs,
  calculateTotalScore,
  type DongScore,
  type ScoreWeights,
} from "../data/mockDongScores";

import {
  fetchAllDongScores,
  fetchDistricts,
} from "../services/regionApi";

// AI 데이터 연동 전에는 점수를 표시하지 않음
// [지도 데이터] 실제 점수 연동 전에는 자치구 점수를 비워 둡니다.
const emptyRegionScores: { district: string; score: number }[] = [];

// 평가 항목과 초기 가중치
// [기본 가중치] 5개 평가 항목의 초기 비율이며 초기화 시에도 사용합니다.
const criteria = [
  { key: "economy", label: "경제 활력도", defaultWeight: 20 },
  { key: "energy", label: "에너지 소비효율", defaultWeight: 15 },
  { key: "comfort", label: "생활 쾌적도", defaultWeight: 25 },
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
// 백엔드 가데이터를 한 번 읽어 5개 평가 점수의 공통 원본으로 사용합니다.
const [dongScores, setDongScores] = useState<DongScore[]>([]);
const [dataError, setDataError] = useState("");
const [loadingScores, setLoadingScores] = useState(true);
const [selectedDongCode, setSelectedDongCode] = useState("");

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

// 가중치 또는 지역 선택이 바뀔 때 같은 백엔드 점수로 TOP 10을 계산합니다.
const top10Dongs = useMemo(() => {
  if (!selectedDistrict) return [];
  return getTop10Dongs(dongScores, selectedDistrict, scoreWeights);
}, [dongScores, selectedDistrict, ...weights]);

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
        {/* 왼쪽: 가중치 + TOP 10 */}
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

          {/* [TOP 10] 종합점수 내림차순 목록이며, 데이터가 없을 때 분석 대기를 표시 */}
          {/* 추천 행정동 순위 */}
          <section className="detail-panel">
            <div className="detail-panel-heading">
    <h2>추천 행정동 TOP 10</h2>
            </div>
          
            <div className="detail-ranking-list">
              {dataError ? (
                <div className="detail-pending">API 연결 실패: {dataError}</div>
              ) : top10Dongs.length > 0 ? (
                top10Dongs.map((dong) => (
                  <div
                    className="detail-ranking-item"
                    key={dong.dongCode}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedDongCode(dong.dongCode)}
                    onKeyDown={event => { if (event.key === "Enter") setSelectedDongCode(dong.dongCode); }}
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
                ))
              ) : (
                <div className="detail-pending">
                  <strong>분석 대기</strong>
                  <p>
                    행정동별 평가 점수가 연결되면
                    가중치에 따라 순위가 표시됩니다.
                  </p>
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
              <p className="detail-muted">
                자치구 자동 확대는 다음 단계에서 연결
              </p>
            </div>
          </div>

          <SeoulMap
            data={emptyRegionScores}
            selectedDistrict={showAllSeoul ? null : selectedDistrict}
            onDistrictClick={onDistrictClick}
            focusDistrict={showAllSeoul ? null : selectedDistrict}
            resetKey={mapResetKey}
            dongScores={mapDongScores}
          />

          <p className="detail-map-note">
            지도 색상과 동별 순위는
            AI 분석 점수 연동 후 표시됩니다.
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
            <select id="detail-dong-select" value={selectedDongCode}
              onChange={event => setSelectedDongCode(event.target.value)}
              style={{ width: "100%", padding: "10px", marginTop: "8px", borderRadius: "8px" }}>
              <option value="">행정동을 선택하세요</option>
              {districtDongs.map(d => <option value={d.dongCode} key={d.dongCode}>{d.dongName}</option>)}
            </select>
          </div>

          <div className="detail-overall-score">
            <span>AI 종합점수 (테스트 데이터)</span>
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
                {criteria.map((item) => (
                  <div
                    className="detail-score-row"
                    key={item.key}
                  >
                    <span>{item.label}</span>
                    <strong>{selectedDong ? `${selectedDong.scores[item.key].toFixed(1)}점` : "분석 대기"}</strong>
                  </div>
                ))}
              </div>
            ) : (
              <div className="detail-pending">
                {activeTab === "trend"
                  ? "환경 시계열 데이터 연동 예정"
                  : "서울 및 자치구 평균 데이터 연동 예정"}
              </div>
            )}
          </div>

          <div className="detail-insight">
            <h3>AI 분석 인사이트</h3>
            <p>
              실제 분석 결과가 준비되면
              추천 근거와 주의 요인을 제공합니다.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
