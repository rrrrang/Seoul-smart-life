import { useState } from "react";

import Sidebar from "./components/layout/Sidebar";
import MainPage from "./components/MainPage";
import DetailAnalysis from "./components/DetailAnalysis";
import RegionComparison from "./components/RegionComparison";

import "./App.css";

// 메인과 상세분석의 전환 및 선택한 자치구를 공통 관리합니다.
function App() {
  // 현재 메인 메뉴
  const [activeMenu, setActiveMenu] = useState("메인");

  // 지도에서 선택한 지역
  const [selectedDistrict, setSelectedDistrict] = useState<string | null>(null);

  // 자치구 한 번 클릭: 선택만 변경
  const handleDistrictClick = (district: string) => {
    setSelectedDistrict(district);
  };

  // 지도에서 자치구를 더블클릭하면 상세분석으로 이동
  const handleDistrictDoubleClick = (district: string) => {

    console.log("App 페이지 이동 실행:", district);
    setSelectedDistrict(district);
    setActiveMenu("상세분석");
  };
  // 메인 지도 선택 상태 초기화
  const handleMapReset = () => {
    setSelectedDistrict(null);
  };

  return (
    <div className="app-layout">

      <Sidebar activeMenu={activeMenu} onMenuChange={setActiveMenu} />

      <div className="main-layout">
        <main className="page-content">
          {activeMenu === "메인" ? (
            <MainPage
              selectedDistrict={selectedDistrict}
              onDistrictClick={handleDistrictClick}
              onDistrictDoubleClick={handleDistrictDoubleClick}
              onMapReset={handleMapReset}
            />
          ) : activeMenu === "상세분석" ? (
            <DetailAnalysis
              selectedDistrict={selectedDistrict}
              onDistrictClick={setSelectedDistrict}
            />
          ) : activeMenu === "지역 비교" ? (
            <RegionComparison />
          ) : (
            <p className="content-placeholder">
              {activeMenu} 화면 개발 예정
            </p>
          )}
        </main>
      </div>
    </div>
  );
}


export default App;