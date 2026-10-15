/*
 * 메인 대시보드: 환경 진단 안내, 서울 지도 및 분석 대기 화면을 렌더링합니다.
 * 안내: 실행 로직은 변경하지 않고 설명 주석만 추가한 버전입니다.
 */
import SeoulMap from "./SeoulMap";
import "../CSS/MainPage.css";

// AI 점수 연동 전 빈 데이터
// [진단 점수] 실제 AI 분석값이 없으므로 빈 배열을 사용합니다.
const regionScores: { district: string; score: number }[] = [];

// 부모 컴포넌트에서 전달받는 데이터 타입
type MainPageProps = {
  selectedDistrict: string | null;
  onDistrictClick: (district: string) => void;
  onDistrictDoubleClick: (district: string) => void;
};

// 환경 노출 항목
// [환경 지표] 오른쪽 정보 패널에서 사용할 항목 및 표시 단위입니다.
const exposureItems = [
  { label: "PM2.5", unit: "µg/m³" },
  { label: "PM10", unit: "µg/m³" },
  { label: "소음 (주간)", unit: "dB" },
  { label: "평균 기온", unit: "°C" },
  { label: "평균 습도", unit: "%" },
];

// [메인 페이지] 선택된 구와 클릭/더블클릭 이벤트를 서울 지도에 전달합니다.
export default function MainPage({
  selectedDistrict,
  onDistrictClick,
  onDistrictDoubleClick,
}: MainPageProps) {
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
      
          <span className="diagnosis-status">
            모델 연동 예정
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
                  <span className="diagnosis-card-icon">{icon}</span>
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

          {/* 기존에 구현한 지도 재사용 */}
          <SeoulMap
            data={regionScores}
            selectedDistrict={selectedDistrict}
            onDistrictClick={onDistrictClick}
            onDistrictDoubleClick={onDistrictDoubleClick}
          />
        </section>

        {/* 오른쪽: AI 분석 및 환경 데이터 */}
        <div className="mainpage-right">
          {/* AI 추천 인사이트 */}
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

          {/* 환경 노출 현황 */}
          <section className="mainpage-card exposure-card">
            <div className="card-heading">
              <h2>환경 노출 현황</h2>
            </div>

            <div className="exposure-list">
              {exposureItems.map((item) => (
                <div className="exposure-row" key={item.label}>
                  <span>{item.label}</span>

                  <span className="exposure-value">
                    -- {item.unit}
                  </span>

                  <span className="exposure-badge">
                    대기
                  </span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
