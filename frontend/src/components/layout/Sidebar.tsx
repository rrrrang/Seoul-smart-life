import "../../CSS/Sidebar.css";

type SidebarProps = {
  activeMenu: string;
  onMenuChange: (menu: string) => void;
};

// [메뉴 목록] 그룹 단위로 메뉴를 구성합니다.
const menuGroups = [
  {
    title: "환경 진단",
    menus: [
      "메인",
      "상세분석",
      "지역 비교",
    ],
  },
];

// 환경 노출 항목
// [환경 지표] 오른쪽 정보 패널에서 사용할 항목 및 표시 단위입니다.
const exposureItems = [
  { label: "PM2.5", unit: "µg/m³" },
  { label: "PM10", unit: "µg/m³" },
  { label: "소음 (주간)", unit: "dB" },
  { label: "평균 기온", unit: "°C" },
  { label: "평균 습도", unit: "%" },
];


// [메뉴 동작] 선택 메뉴에 따라 활성 스타일을 갱신하도록 부모에게 알립니다.
export default function Sidebar({
  activeMenu,
  onMenuChange,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      {/* 로고 */}
      <div className="sidebar-logo">
        <div className="logo-icon">
          <svg
            width="19"
            height="19"
            viewBox="0 0 24 24"
            fill="none"
            stroke="white"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10Z" />
            <path d="M9 21v-8h6v8" />
          </svg>
        </div>

        <div className="logo-text">
          <span>Seoul Smart Life</span>
          <p className="sub-title">맞춤형 주거지역 추천</p>
        </div>
      </div>

      {/* 사이드 메뉴 */}
      <nav className="sidebar-nav" aria-label="주 메뉴">
        {menuGroups.map((group) => (
          <div className="menu-group" key={group.title}>
            <p className="menu-title">{group.title}</p>

            {group.menus.map((menu) => (
              <button
                type="button"
                key={menu}
                className={`menu-item ${
                  activeMenu === menu ? "active" : ""
                }`}
                onClick={() => onMenuChange(menu)}
                aria-current={
                  activeMenu === menu ? "page" : undefined
                }
              >
                {menu}
              </button>
            ))}
          </div>
        ))}
      </nav>

      {/* 사이드바 하단 환경 지표 */}
      <div className="sidebar-exposure">
        <h3>환경 노출 지표</h3>
      
        {exposureItems.map((item) => (
          <div className="sidebar-exposure-item" key={item.label}>
            <span>{item.label}</span>
            <span className="sidebar-exposure-value">
              -- {item.unit}
            </span>
          </div>
        ))}
      </div>
    </aside>
  );
}
