/*
 * 앱 최상위 컴포넌트: 메뉴 전환 및 선택 자치구 상태를 관리합니다.
 * 안내: 실행 로직은 변경하지 않고 설명 주석만 추가한 버전입니다.
 */
import { useState } from "react";

import Sidebar from "./components/layout/Sidebar";
import MainPage from "./components/MainPage";
import DetailAnalysis from "./components/DetailAnalysis";

import "./App.css";

// [앱 상태] 메인과 상세분석의 전환 및 선택한 자치구를 공통 관리합니다.
function App() {
  // 현재 선택된 메뉴
  const [activeMenu, setActiveMenu] = useState("메인");

  // 지도에서 선택한 지역
  const [selectedDistrict, setSelectedDistrict] = useState<string | null>(null);

  // [페이지 이동] 메인 지도에서 더블클릭한 자치구를 상세분석에 넘깁니다.
  // 지도에서 자치구를 더블클릭하면 상세분석으로 이동
  const handleDistrictDoubleClick = (district: string) => {
    setSelectedDistrict(district);
    setActiveMenu("상세분석");
  };

  return (
    <div className="app-layout">

      <Sidebar activeMenu={activeMenu} onMenuChange={setActiveMenu} />

      <div className="main-layout">
        <main className="page-content">
          {activeMenu === "메인" ? (
            <MainPage
              selectedDistrict={selectedDistrict}
              onDistrictClick={setSelectedDistrict}
              onDistrictDoubleClick={handleDistrictDoubleClick}
            />
          ) : activeMenu === "상세분석" ? (
            <DetailAnalysis
              selectedDistrict={selectedDistrict}
              onDistrictClick={setSelectedDistrict}
            />
          ) : (
            <p className="content-placeholder">{activeMenu} 화면 개발 예정</p>
          )}
        </main>
      </div>
    </div>
  );
}


export default App;